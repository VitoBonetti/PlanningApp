from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from routers import auth, users, assets, tests, board
from websockets_manager import manager

app = FastAPI(title="Pentest Planner API - PRO")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Wire up all the separated routes!
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(assets.router)
app.include_router(tests.router)
app.include_router(board.router)

# Websocket route
@app.websocket("/ws/board")
@app.websocket("/api/ws/board")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # We keep the connection alive and listen for disconnects
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)