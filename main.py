import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from graph import build_form_graph

app = FastAPI(title="Agentic Form Generator")

# Initialize the graph once when the server starts
form_graph = build_form_graph()

@app.websocket("/ws/generate-form")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    try:
        # 1. Wait for the user to send their prompt over the socket
        data = await websocket.receive_text()
        prompt_data = json.loads(data)
        user_prompt = prompt_data.get("prompt", "")
        
        await websocket.send_text(json.dumps({"status": "Started processing your request..."}))

        initial_state = {
            "user_prompt": user_prompt,
            "retries": 0
        }

        # 2. Stream the graph's execution live
        # graph.stream() yields a dictionary every time a node finishes
        for event in form_graph.stream(initial_state):
            # Find out which node just finished
            for node_name, node_state in event.items():
                
                # Send a friendly status update based on the active node
                if node_name == "drafter":
                    await websocket.send_text(json.dumps({"status": "Drafting initial form structure..."}))
                
                elif node_name == "validator":
                    if node_state.get("error_message"):
                        await websocket.send_text(json.dumps({"status": f"Validation failed. Triggering self-correction (Attempt {node_state['retries']})..."}))
                    else:
                        await websocket.send_text(json.dumps({"status": "Schema validated successfully!"}))
                
                elif node_name == "corrector":
                    await websocket.send_text(json.dumps({"status": "Applied corrections to the JSON..."}))
                
                elif node_name == "executor":
                    # Send the final Google Form URL back to the client
                    final_form = node_state["final_form"]
                    await websocket.send_text(json.dumps({
                        "status": "Form published to Google Drive!",
                        "title": final_form.title,
                        # If you want to return the actual URL, you'll need to update your executor_node 
                        # to save the URL to the AgentState so you can access it here.
                    }))

    except WebSocketDisconnect:
        print("Client disconnected.")
    except Exception as e:
        await websocket.send_text(json.dumps({"error": str(e)}))
        await websocket.close()