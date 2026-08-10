# test_ws.py
import asyncio
import websockets
import json

async def test_generation():
    uri = "ws://localhost:8000/ws/generate-form"
    async with websockets.connect(uri) as websocket:
        
        # Send the prompt
        payload = {"prompt": "Create a 3-question survey about a local gym's new swimming pool."}
        await websocket.send(json.dumps(payload))
        
        # Listen for the live updates
        while True:
            try:
                response = await websocket.recv()
                data = json.loads(response)
                print(f"Server Update: {data}")
                
                if "published" in data.get("status", "").lower():
                    break
            except websockets.ConnectionClosed:
                break

if __name__ == "__main__":
    asyncio.run(test_generation())