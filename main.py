import json
import uuid

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

import models
from database import engine, get_db
from graph import build_form_graph

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Agentic Form Generator")

# Initialize the graph once when the server starts
form_graph = build_form_graph()

@app.websocket("/ws/generate-form")
async def websocket_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
    await websocket.accept()
    
    try:
        # 1. Wait for the user to send their prompt over the socket
        data = await websocket.receive_text()
        prompt_data = json.loads(data)
        user_prompt = prompt_data.get("prompt", "")
        
        # --- PHASE 2 MEMORY FIX ---
        # Allow the frontend to pass an existing thread_id to resume a conversation
        client_thread_id = prompt_data.get("thread_id")
        
        await websocket.send_text(json.dumps({"status": "Started processing your request..."}))
        
        # Create a dummy user for now (until we build OAuth)
        test_user = db.query(models.User).filter(models.User.email == "test@example.com").first()
        if not test_user:
            test_user = models.User(email="test@example.com")
            db.add(test_user)
            db.commit()
            db.refresh(test_user)

        # 2. Session Management (Create new OR Resume existing)
        if client_thread_id:
            # We are patching an existing form!
            current_session = db.query(models.FormSession).filter(models.FormSession.thread_id == client_thread_id).first()
            if not current_session:
                await websocket.send_text(json.dumps({"error": "Thread ID not found in DB."}))
                return
        else:
            # We are building a brand new form!
            current_session = models.FormSession(user_id=test_user.id)
            # TEMPORARY HARDCODE FOR QUICK TESTING: 
            # Uncomment the next line if you want to test patching without changing your frontend HTML yet
            # current_session.thread_id = "static-patch-test-001"
            db.add(current_session)
            db.commit()
            db.refresh(current_session)
        
        # Pass the OFFICIAL thread_id to LangGraph
        config = {"configurable": {"thread_id": current_session.thread_id}}

        initial_state = {
            "user_prompt": user_prompt,
            "retries": 0
        }

        # 3. Stream the graph's execution live
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

                    # Update our database to mark it as published and save the Google ID
                    current_session.is_published = True
                    current_session.google_form_id = node_state.get("google_form_id")
                    db.commit()

                    await websocket.send_text(json.dumps({
                        "status": "Form published to Google Drive!",
                        "title": final_form.title,
                        "thread_id": current_session.thread_id # Send this back so the UI can remember it!
                    }))

                # --- NEW: Catch the patch_executor node ---
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


@app.post("/test-db")
def test_database_connection(db: Session = Depends(get_db)):
    new_user = models.User(email="test@example.com")
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {"message": "Database connected successfully!", "user_id": new_user.id}