import json
import os
from pathlib import Path

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

import app.database.models as models
from app.agent.graph import build_form_graph
from app.database.database import engine, get_db
from app.services.form_utils import exchange_code_for_credentials, generate_auth_url

ROOT_DIR = Path(__file__).resolve().parent.parent
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Agentic Form Generator")

# --- ADD MIDDLEWARE ---
# This encrypts session data (like Google tokens) into a secure HTTP-only browser cookie.
# In production, change the secret_key to a secure environment variable!
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET_KEY", "super_secret_dev_key"))

# Initialize the graph once when the server starts
form_graph = build_form_graph()

# ==========================================
# FRONTEND ROUTE
# ==========================================
@app.get("/")
def serve_frontend():
    """Serves the index.html file on the same domain as the backend."""
    frontend_path = str(ROOT_DIR / "frontend" / "index.html")
    return FileResponse(frontend_path)


# ==========================================
# OAUTH 2.0 ENDPOINTS
# ==========================================

@app.get("/auth/login")
def login(request: Request):
    """Redirects the user to Google's OAuth consent screen."""
    auth_url, state, code_verifier = generate_auth_url()    
    request.session["oauth_state"] = state
    request.session["code_verifier"] = code_verifier
    
    return RedirectResponse(url=auth_url)

@app.get("/auth/callback")
def auth_callback(request: Request, code: str, state: str):
    """Catches the user when Google redirects them back to our app."""
    if state != request.session.get("oauth_state"):
        raise HTTPException(status_code=400, detail="State mismatch. Potential CSRF attack.")
    
    # Retrieve the verifier from the secure cookie
    code_verifier = request.session.get("code_verifier")    
    creds_dict = exchange_code_for_credentials(code, state, code_verifier)
    
    # Save to encrypted browser session
    request.session["google_creds"] = creds_dict
    
    return {"message": "Successfully authenticated! You can now generate forms via the chat interface."}

@app.get("/auth/logout")
def logout(request: Request):
    """Clears the user's secure session."""
    request.session.clear()
    return {"message": "Logged out successfully."}


# ==========================================
# WEBSOCKET GENERATION ENGINE
# ==========================================

@app.websocket("/ws/generate-form")
async def websocket_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
    await websocket.accept()
    
    # 1. AUTHENTICATION CHECK
    # We pull the credentials directly from their encrypted session cookie
    creds_dict = websocket.session.get("google_creds")
    if not creds_dict:
        await websocket.send_text(json.dumps({
            "error": "Unauthorized. Please authenticate first.", 
            "auth_required": True,
            "login_url": "http://localhost:8000/auth/login"
        }))
        await websocket.close()
        return

    try:
        # 2. Wait for the user to send their prompt
        data = await websocket.receive_text()
        prompt_data = json.loads(data)
        user_prompt = prompt_data.get("prompt", "")
        client_thread_id = prompt_data.get("thread_id")
        
        await websocket.send_text(json.dumps({"status": "Started processing your request..."}))
        
        # Database tracking (using a generic web user until a full user-profile scope is added)
        test_user = db.query(models.User).filter(models.User.email == "web_user@example.com").first()
        if not test_user:
            test_user = models.User(email="web_user@example.com")
            db.add(test_user)
            db.commit()
            db.refresh(test_user)

        # 3. Session Management (Create new OR Resume existing)
        if client_thread_id:
            current_session = db.query(models.FormSession).filter(models.FormSession.thread_id == client_thread_id).first()
            if not current_session:
                await websocket.send_text(json.dumps({"error": "Thread ID not found in DB."}))
                return
        else:
            current_session = models.FormSession(user_id=test_user.id)
            db.add(current_session)
            db.commit()
            db.refresh(current_session)
        
        config = {"configurable": {"thread_id": current_session.thread_id}}

        # --- PHASE 7 CREDENTIAL INJECTION ---
        # We pass the web session credentials into the LangGraph state
        initial_state = {
            "user_prompt": user_prompt,
            "retries": 0,
            "user_google_creds": creds_dict
        }

        # 4. Stream the graph's execution live
        for event in form_graph.stream(initial_state, config=config):
            for node_name, node_state in event.items():
                
                if node_name == "drafter":
                    await websocket.send_text(json.dumps({"status": "Drafting form structure..."}))
                
                elif node_name == "validator":
                    if node_state.get("error_message"):
                        await websocket.send_text(json.dumps({"status": f"Validation failed. Triggering self-correction (Attempt {node_state.get('retries', 0)})..."}))
                    else:
                        await websocket.send_text(json.dumps({"status": "Schema validated successfully!"}))
                
                elif node_name == "corrector":
                    await websocket.send_text(json.dumps({"status": "Applied corrections to the JSON..."}))
                
                elif node_name == "executor":
                    final_form = node_state["final_form"]
                    current_session.is_published = True
                    current_session.google_form_id = node_state.get("google_form_id")
                    db.commit()
                    await websocket.send_text(json.dumps({
                        "status": "Form published to Google Drive!",
                        "title": final_form.title,
                        "thread_id": current_session.thread_id
                    }))

                elif node_name == "patch_executor":
                    final_form = node_state["final_form"]
                    await websocket.send_text(json.dumps({
                        "status": "Form updated successfully via Patch Engine!",
                        "title": final_form.title,
                        "thread_id": current_session.thread_id
                    }))

    except WebSocketDisconnect:
        print("Client disconnected.")
    except Exception as e:
        await websocket.send_text(json.dumps({"error": str(e)}))
        await websocket.close()