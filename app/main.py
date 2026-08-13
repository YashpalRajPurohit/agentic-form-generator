import io
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

import pypdf
from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

import app.database.models as models
import app.database.schemas as schemas
from app.agent.graph import build_form_graph
from app.database.database import close_db, engine, get_db, init_db
from app.services.form_utils import (
    check_if_form_trashed,
    exchange_code_for_credentials,
    generate_auth_url,
    get_latest_form_schema,
)

form_graph = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global form_graph
    # This runs ONLY in the actual worker process, preventing the Uvicorn parent thread crash!
    init_db()
    form_graph = build_form_graph()
    yield
    # This cleans up the pool gracefully on shutdown
    close_db()

ROOT_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="Agentic Form Generator API", lifespan=lifespan)

# --- SESSION MIDDLEWARE ---
# Updated with cross-domain flags for Vercel/Render production
app.add_middleware(
    SessionMiddleware, 
    secret_key=os.getenv("SESSION_SECRET_KEY", "super_secret_dev_key"),
    same_site="none",   # Crucial: Allows cross-domain cookies
    https_only=True     # Crucial: Enforces secure transmission for cross-domain cookies
)

# --- CORS MIDDLEWARE ---
# This tells FastAPI to allow requests from your Next.js frontend
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000"], 
    allow_credentials=True,                  # Allows the browser to pass the session cookie
    allow_methods=["*"],                     
    allow_headers=["*"],                     
)

# Initialize the graph once when the server starts
form_graph = build_form_graph()

# This is where your future Next.js frontend will live
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# ==========================================
# AUTHENTICATION ROUTES
# ==========================================

@app.get("/auth/status")
def auth_status(request: Request):
    is_authenticated = "google_creds" in request.session
    return {"authenticated": is_authenticated}

@app.get("/auth/login")
def login(request: Request):
    auth_url, state, code_verifier = generate_auth_url()
    request.session["oauth_state"] = state
    request.session["code_verifier"] = code_verifier
    return RedirectResponse(url=auth_url)

@app.get("/auth/callback")
def auth_callback(request: Request, code: str, state: str):
    if state != request.session.get("oauth_state"):
        raise HTTPException(status_code=400, detail="State mismatch. Potential CSRF attack.")
    
    code_verifier = request.session.get("code_verifier")
    creds_dict = exchange_code_for_credentials(code, state, code_verifier)
    
    request.session["google_creds"] = creds_dict
    
    # Redirect back to the Next.js frontend instead of the FastAPI root
    return RedirectResponse(url=FRONTEND_URL)

@app.get("/auth/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url=FRONTEND_URL)


# ==========================================
# REST API
# ==========================================

@app.get("/api/threads", response_model=List[schemas.ThreadResponse])
def get_user_threads(request: Request, db: Session = Depends(get_db)):
    """Fetch all form generation threads for the logged-in user."""
    creds = request.session.get("google_creds")
    
    if not creds or not creds.get("email"):
        raise HTTPException(status_code=401, detail="Not authenticated or email missing from session")
    
    user_email = creds.get("email")
    user = db.query(models.User).filter(models.User.email == user_email).first()
    
    if not user:
        return []

    threads = db.query(models.Thread).filter(models.Thread.user_id == user.id).order_by(models.Thread.updated_at.desc()).all()
    return threads


@app.get("/api/threads/{thread_id}/messages", response_model=List[schemas.MessageResponse])
def get_thread_messages(thread_id: str, request: Request, db: Session = Depends(get_db)):
    """Fetch all messages for a specific thread to load chat history."""
    creds = request.session.get("google_creds")
    if not creds or not creds.get("email"):
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = db.query(models.User).filter(models.User.email == creds.get("email")).first()
    if not user:
        return []

    # Ensure the thread actually belongs to this specific user!
    thread = db.query(models.Thread).filter(
        models.Thread.thread_id == thread_id,
        models.Thread.user_id == user.id  
    ).first()
    
    if not thread:
        return [] # Return empty if the thread doesn't exist OR doesn't belong to them

    messages = db.query(models.Message).filter(models.Message.thread_id == thread.id).order_by(models.Message.created_at.asc()).all()
    return messages


@app.delete("/api/threads/{thread_id}")
def delete_thread(thread_id: str, request: Request, db: Session = Depends(get_db)):
    """Deletes a thread and all its associated messages."""
    creds = request.session.get("google_creds")
    if not creds or not creds.get("email"):
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = db.query(models.User).filter(models.User.email == creds.get("email")).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Ensure they only delete their own threads!
    thread = db.query(models.Thread).filter(
        models.Thread.thread_id == thread_id,
        models.Thread.user_id == user.id
    ).first()
    
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found or unauthorized")

    db.delete(thread)
    db.commit()
    
    return {"status": "success", "message": "Thread deleted"}


@app.post("/api/upload")
async def upload_document(request: Request, file: UploadFile = File(...)):
    """Extracts text from uploaded documents to use as context for the AI."""
    if "google_creds" not in request.session:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    extracted_text = ""
    
    try:
        content = await file.read()
        
        if file.filename.lower().endswith(".pdf"):
            pdf_reader = pypdf.PdfReader(io.BytesIO(content))
            for page in pdf_reader.pages:
                extracted_text += page.extract_text() + "\n"
                
        elif file.filename.lower().endswith(".txt"):
            extracted_text = content.decode("utf-8")
            
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type. Please upload a PDF or TXT.")
            
        return {
            "filename": file.filename,
            "extracted_text": extracted_text.strip()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")
    

# ==========================================
# WEBSOCKET GENERATION ENGINE
# ==========================================

@app.websocket("/ws/generate-form")
async def websocket_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
    await websocket.accept()
    
    creds_dict = websocket.session.get("google_creds")
    
    # ⚡ FIX 1: Strictly check for the dictionary AND the email inside it
    if not creds_dict or not creds_dict.get("email"):
        await websocket.send_text(json.dumps({
            "error": "Unauthorized or email missing. Please authenticate first.", 
            "auth_required": True
        }))
        await websocket.close()
        return

    try:
        data = await websocket.receive_text()
        prompt_data = json.loads(data)
        
        base_prompt = prompt_data.get("prompt", "")
        client_thread_id = prompt_data.get("thread_id")
        document_context = prompt_data.get("document_context", "")
        
        display_prompt = base_prompt
        if document_context:
            if base_prompt:
                display_prompt = f"{base_prompt}\n\n[📎 Document Attached]"
            else:
                display_prompt = "[📎 Document Attached]"

        # B. Create the massive context version for the LangGraph Agent
        if document_context:
            agent_prompt = f"Source Document Context:\n{document_context}\n\nUser Request: {base_prompt}"
        else:
            agent_prompt = base_prompt
        
        # Database tracking 
        # ⚡ FIX 2: Safely grab the guaranteed email (No more fallbacks!)
        user_email = creds_dict.get("email")
        
        test_user = db.query(models.User).filter(models.User.email == user_email).first()
        if not test_user:
            test_user = models.User(email=user_email)
            db.add(test_user)
            db.commit()
            db.refresh(test_user)

        # --- Session Management & History Retrieval ---
        
        # 1. Resolve or Create the Thread FIRST
        if client_thread_id:
            current_thread = db.query(models.Thread).filter(models.Thread.thread_id == client_thread_id).first()
            if not current_thread:
                await websocket.send_text(json.dumps({"error": "Thread ID not found in DB."}))
                return
        else:
            current_thread = models.Thread(user_id=test_user.id, title=display_prompt[:40] + "...")
            db.add(current_thread)
            db.commit()
            db.refresh(current_thread)

        # 2. Build the Chat History
        chat_history = []

        # A. Context Injection: If editing, provide the live form structure
        if current_thread.google_form_id:
            # Pass the user's credentials to fetch the live form safely
            current_form_json = get_latest_form_schema(current_thread.google_form_id, creds_dict) 
            
            system_instruction = f"""You are editing an existing Google Form. 
            Here is the EXACT current structure of the live form:
            {current_form_json}
            
            Do not lose or overwrite existing questions unless the user explicitly asks you to.
            Only generate the patch operations needed to make the requested changes."""
            
            from langchain_core.messages import SystemMessage
            chat_history.append(SystemMessage(content=system_instruction))

        # B. Sliding Window: Fetch only the last 6 messages (if thread already existed)
        if client_thread_id:
            past_messages = (
                db.query(models.Message)
                .filter(models.Message.thread_id == current_thread.id)
                .order_by(models.Message.created_at.desc()) # Grab newest first
                .limit(6) # Sliding window: only remember the last 6 interactions!
                .all()
            )
            
            past_messages.reverse() # Flip them back to chronological order
            
            # Convert DB messages to LangChain message formats
            for msg in past_messages:
                if msg.role == "user":
                    chat_history.append(HumanMessage(content=msg.content))
                elif msg.role == "ai":
                    chat_history.append(AIMessage(content=msg.content))
                    
        # 3. Log CURRENT User Message 
        # (Saved AFTER fetching history so it doesn't duplicate in the LLM's context window)
        user_msg = models.Message(thread_id=current_thread.id, role="user", content=display_prompt)
        db.add(user_msg)
        db.commit()
        
        # --- GOOGLE DRIVE BIN CHECK ---
        # If this thread already has an associated form, verify it still exists!
        if current_thread.google_form_id:
            is_trashed = check_if_form_trashed(current_thread.google_form_id, creds_dict)
            
            if is_trashed:
                error_msg = "This form has been moved to the bin or permanently deleted in Google Drive. Please click '+' to start a new form."
                
                # 1. Save the error to the database so it shows up if they reload the page
                ai_msg = models.Message(thread_id=current_thread.id, role="ai", content=f"❌ {error_msg}")
                db.add(ai_msg)
                db.commit()
                
                # 2. Instantly push the error to the live React UI
                await websocket.send_text(json.dumps({
                    "status": "error",
                    "error": error_msg
                }))
                
                # 3. Halt the function! Do not pass go, do not trigger LangGraph.
                return 
        # -----------------------------------

        config = {"configurable": {"thread_id": current_thread.thread_id}}

        initial_state = {
            "user_prompt": agent_prompt, 
            "chat_history": chat_history,
            "retries": 0,
            "user_google_creds": creds_dict
        }

        # Stream the graph's execution live
        for event in form_graph.stream(initial_state, config=config):
            for node_name, node_state in event.items():
                
                if node_name == "drafter":
                    # --- Check if the Guardrail was triggered ---
                    error_state = node_state.get("error_message", "")
                    
                    # --- Parse the dynamic Guardrail message ---
                    if error_state and error_state.startswith("GUARDRAIL|"):
                        # Extract the AI's custom, natural message
                        guardrail_msg = error_state.split("|", 1)[1]
                        
                        # Save to database as a normal AI message
                        ai_msg = models.Message(thread_id=current_thread.id, role="ai", content=guardrail_msg)
                        db.add(ai_msg)
                        db.commit()
                        
                        # Push to React UI as an 'info' message
                        await websocket.send_text(json.dumps({
                            "status": "info",
                            "message": guardrail_msg,
                            "thread_id": current_thread.thread_id
                        }))
                        # 3. HALT execution
                        return
                    
                    # --- Check for Casual Chat Guardrail ---
                    elif error_state and error_state.startswith("CHAT|"):
                        chat_msg = error_state.split("|", 1)[1]
                        
                        # Save the friendly reply to the database
                        ai_msg = models.Message(thread_id=current_thread.id, role="ai", content=chat_msg)
                        db.add(ai_msg)
                        db.commit()
                        
                        # Push to UI using the 'info' status so it renders as a normal message
                        await websocket.send_text(json.dumps({
                            "status": "info",
                            "message": chat_msg,
                            "thread_id": current_thread.thread_id
                        }))
                        # Halt execution so it doesn't trigger the rest of the form builder
                        return
                    
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
                    form_id = node_state.get("google_form_id")
                    
                    current_thread.is_published = True
                    current_thread.google_form_id = form_id
                    
                    # 1. Save as a JSON string so the frontend can parse the ID later
                    ai_content = json.dumps({
                        "text": f"✅ Form Published: {final_form.title}",
                        "form_id": form_id
                    })
                    ai_msg = models.Message(thread_id=current_thread.id, role="ai", content=ai_content)
                    db.add(ai_msg)
                    db.commit()
                    
                    # 2. Send the form_id in the live WebSocket stream
                    await websocket.send_text(json.dumps({
                        "status": "complete",
                        "title": final_form.title,
                        "thread_id": current_thread.thread_id,
                        "form_id": form_id
                    }))

                elif node_name == "patch_executor":
                    final_form = node_state["final_form"]
                    form_id = current_thread.google_form_id
                    
                    ai_content = json.dumps({
                        "text": f"✅ Form Updated: {final_form.title}",
                        "form_id": form_id
                    })
                    ai_msg = models.Message(thread_id=current_thread.id, role="ai", content=ai_content)
                    db.add(ai_msg)
                    db.commit()
                    
                    await websocket.send_text(json.dumps({
                        "status": "complete",
                        "title": final_form.title,
                        "thread_id": current_thread.thread_id,
                        "form_id": form_id
                    }))

    except WebSocketDisconnect:
        print("Client disconnected.")
    except Exception as e:
        await websocket.send_text(json.dumps({"error": str(e)}))
        await websocket.close()