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
import secrets
from database import get_db_connection, init_db, db_cursor_context
from audit_logger import init_audit_log_infrastructure
import os

SYSTEM_IS_SETUP = False

app = FastAPI(title="Pentest Planner API - PRO")

@app.on_event("startup")
def startup_event():
    global SYSTEM_IS_SETUP
    config = get_system_config()

    if config:
        SYSTEM_IS_SETUP = True
    else:
        # 2. Print the token to the console loudly so the admin sees it
        open("/tmp/.setup_unlocked", "w").close()
        print("=" * 60)
        print("🚨 DAY 0 SETUP MODE DETECTED 🚨")
        print("No configuration found. The system is temporarily open for setup.")
        print("Navigate to the frontend to create the first admin.")
        print("=" * 60)

    init_db()
    init_audit_log_infrastructure()

env_origins = os.environ.get("ALLOWED_ORIGINS", "")

if env_origins:
    # PRODUCTION: Reads from docker-compose.yml
    ALLOWED_ORIGINS = [origin.strip() for origin in env_origins.split(",")]
elif os.environ.get("ENV") == "local":
    # LOCAL DEV ONLY: For when you are coding on your actual laptop
    ALLOWED_ORIGINS = [
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ]
else:
    # Fail safe
    ALLOWED_ORIGINS = []


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # to change in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


@app.middleware("http")
async def setup_mode_interceptor(request: Request, call_next):
    global SYSTEM_IS_SETUP

    if request.method == "OPTIONS":
        return await call_next(request)

    # Allow traffic to docs and frontend
    if not request.url.path.startswith("/api/"):
        return await call_next(request)

    # 3. If the system is NOT setup, lock everything down except the setup endpoint
    if not SYSTEM_IS_SETUP:
        if get_system_config() is not None:
            SYSTEM_IS_SETUP = True
        else:
            if request.url.path.startswith("/api/system/setup"):
                if not os.path.exists("/tmp/.setup_unlocked"):
                    return JSONResponse(status_code=403, content={"detail": "Setup is locked."})
                return await call_next(request)
            else:
                return JSONResponse(status_code=503, content={"detail": "SYSTEM_SETUP_REQUIRED",
                                                              "message": "System is in Day 0 Setup Mode."})


    # 4. If the system IS setup, completely block the setup endpoint!
    if request.url.path.startswith("/api/system/setup"):
        return JSONResponse(
            status_code=403,
            content={"detail": "System is already configured. Setup endpoints are disabled."}
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
    # CSRF Protection
    origin = websocket.headers.get("origin")
    if origin not in ALLOWED_ORIGINS:
        await websocket.close(code=1008, reason="Cross-Site Request Blocked")
        return

    token = websocket.cookies.get("access_token")

    if not token:
        await websocket.close(code=1008, reason="Missing authentication token")
        return

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        session_token = payload.get("session")

        with db_cursor_context() as cursor:
            if not cursor:
                await websocket.close(code=1011, reason="Database Unavailable")
                return
            cursor.execute("SELECT session_token FROM users WHERE username = %s", (username,))
            row = cursor.fetchone()

        # Kick them off the WebSocket if the session is old
        if not row or row[0] != session_token:
            await websocket.accept()  # Must accept before sending a message
            await websocket.send_text('{"event": "SESSION_EXPIRED", "message": "Logged in from another device."}')
            await websocket.close(code=1008, reason="Session Invalidated")
            return
            
    except Exception as e:
        print(f"WebSocket Auth Failed: {e}") 
        await websocket.close(code=1008, reason="Invalid authentication token")
        return

    await manager.connect(websocket, username)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
