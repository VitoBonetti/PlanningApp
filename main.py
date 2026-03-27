from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from routers import auth, users, assets, tests, board, setup
from websockets_manager import manager
from routers.auth import get_current_user
from secrets_manager import get_system_config
import jwt
from routers.auth import SECRET_KEY, ALGORITHM, limiter
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
import sqlite3
from database import get_db_connection, init_db
from audit_logger import init_audit_log_infrastructure

app = FastAPI(title="Pentest Planner API - PRO")

@app.on_event("startup")
def startup_event():
    init_db()
    init_audit_log_infrastructure()

ALLOWED_ORIGINS = [
    "http://localhost:5173",          # Local React dev server
    "https://erp.vitobonetti.nl"  # Dev frontend
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # to change in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.middleware("http")
async def setup_mode_interceptor(request: Request, call_next):
    # Allow traffic to the setup API, docs, and frontend
    if request.url.path.startswith("/api/system/") or not request.url.path.startswith("/api/"):
        return await call_next(request)

    # If they are trying to access standard APIs, check if the system is configured
    config = get_system_config()
    if not config:
        return JSONResponse(
            status_code=503,
            content={"detail": "SYSTEM_SETUP_REQUIRED", "message": "The system is currently in Day 0 Setup Mode."}
        )

    return await call_next(request)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Wire up all the separated routes!
app.include_router(setup.router)
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

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT session_token FROM users WHERE username = %s", (username,))
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
