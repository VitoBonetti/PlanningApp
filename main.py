from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from routers import auth, users, assets, tests, board
from websockets_manager import manager
from routers.auth import get_current_user
import jwt
from routers.auth import SECRET_KEY, ALGORITHM, limiter
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
import sqlite3
from database import DB_FILE, init_db
from audit_logger import init_audit_log_infrastructure

app = FastAPI(title="Pentest Planner API - PRO")

@app.on_event("startup")
def startup_event():
    init_db()
    init_audit_log_infrastructure()

ALLOWED_ORIGINS = [
    "http://localhost:5173",          # Local React dev server
    "https://mffdawybwrgvpgxdrcjc.vitobonetti.nl"  # Dev frontend
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # to change in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        session_token = payload.get("session")

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT session_token FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        conn.close()

        # Kick them off the WebSocket if the session is old
        if not row or row[0] != session_token:
            raise Exception("Session Invalidated")
            
    except Exception as e:
        print(f"WebSocket Auth Failed: {e}") 
        await websocket.close(code=1008, reason="Invalid authentication token")
        return

    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
