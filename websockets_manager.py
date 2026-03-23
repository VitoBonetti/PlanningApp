from fastapi import WebSocket
from typing import List

class ConnectionManager:
    def __init__(self):
        # list that holds the active connection for every user looking at the app
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        # if a change happens, send a message to all connected browser
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                pass

# make a single, global instance of the manager
manager = ConnectionManager()