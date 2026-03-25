from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from routers import auth, users, assets, tests, board
from websockets_manager import manager
from routers.auth import get_current_user
import jwt
from routers.auth import SECRET_KEY, ALGORITHM

app = FastAPI(title="Pentest Planner API - PRO")

ALLOWED_ORIGINS = [
    "http://localhost:5173",          # Local React dev server
    "https://mffdawybwrgvpgxdrcjc.vitobonetti.nl/"  # Production frontend
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # to change in production
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
    token = websocket.cookies.get("access_token")

    if not token:
        await websocket.close(code=1008, reason="Missing authentication token")
        return

    try:
        # Validate token
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        await websocket.close(code=1008, reason="Invalid authentication token")
        return

    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)