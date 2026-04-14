from fastapi import WebSocket
from typing import List
from typing import Dict


class ConnectionManager:
    def __init__(self):
        # dictionary mapping the WebSocket object to the username
        self.active_connections: Dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, username: str):
        # await websocket.accept()
        self.active_connections[websocket] = username
        # broadcast that the user joined
        await self.broadcast(f'{{"action": "USER_JOINED", "username": "{username}"}}')

    async def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            username = self.active_connections.pop(websocket)
            # Broadcast that the user left!
            await self.broadcast(f'{{"action": "USER_LEFT", "username": "{username}"}}')

    async def broadcast(self, message: str):
        # if a change happens, send a message to all connected browsers
        for connection in list(self.active_connections.keys()):
            try:
                await connection.send_text(message)
            except:
                pass

# make a single, global instance of the manager
manager = ConnectionManager()