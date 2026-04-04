from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from routers import auth, users, assets, tests, board
from websockets_manager import manager
from services.importer import run_import_job
from database import get_db_connection, init_db, db_cursor_context
from audit_logger import init_audit_log_infrastructure
import os
from contextlib import asynccontextmanager
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler


async def scheduled_sync_job():
    print("⏰ Running automated daily sync job...")
    
    # Run the heavy, synchronous Google Drive/DB sync in a separate thread 
    # so it doesn't freeze the WebSockets for everyone else!
    await asyncio.to_thread(run_import_job)
    
    # Give the database a second to settle, then broadcast to all connected UIs
    await asyncio.sleep(2)
    await manager.broadcast('{"action": "REFRESH_ASSETS"}')
    await manager.broadcast('{"action": "REFRESH_BOARD"}')
    print("✅ Automated daily sync complete and broadcasted.")


# --- 2. Attach the Scheduler to the App Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the clock when the server spins up
    scheduler = AsyncIOScheduler()
    
    # Schedule it for 2:00 AM every day
    # You can easily test it by changing it to (trigger='interval', minutes=5)
    # scheduler.add_job(scheduled_sync_job, 'cron', hour=2, minute=0)
    scheduler.add_job(scheduled_sync_job, 'interval', minutes=2)
    
    scheduler.start()
    print("🕰️ Internal Background Scheduler started.")
    
    yield # The app runs here
    
    # Shut down the clock cleanly when the server restarts
    scheduler.shutdown()


app = FastAPI()


@app.on_event("startup")
def startup_event():
    # 1. Initialize Database Tables
    init_db()

    # 2. Check Database Connection
    conn = get_db_connection()
    if conn:
        print("✅ System normal. Database connected.")
        conn.close()
    else:
        print("🚨 CRITICAL: Cannot reach Cloud SQL via IAM. Check Service Account permissions.")

    # 3. Initialize BigQuery Audit Logs
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

# Wire up all the separated routes!
app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(assets.router, prefix="/api")
app.include_router(tests.router, prefix="/api")
app.include_router(board.router, prefix="/api")


# Websocket route
@app.websocket("/ws/board")
@app.websocket("/api/ws/board")
async def websocket_endpoint(websocket: WebSocket):
    # CSRF Protection
    origin = websocket.headers.get("origin")
    if origin not in ALLOWED_ORIGINS:
        await websocket.close(code=1008, reason="Cross-Site Request Blocked")
        return

    # Accept the connection first
    await websocket.accept()

    # Read the secure header attached by Google IAP during the WebSocket upgrade
    iap_header = websocket.headers.get("x-goog-authenticated-user-email")
    
    if not iap_header:
        # Fallback for local laptop testing
        username = os.environ.get("MASTER_ADMIN_EMAIL", "admin@yourcompany.com").lower()
    else:
        # Extract the email from the IAP header
        username = iap_header.split(":")[-1].lower()

    # Connect to the Websocket Manager
    await manager.connect(websocket, username)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
