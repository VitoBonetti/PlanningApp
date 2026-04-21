from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import traceback
from routers import (
    auth, users, assets,
    tests, board, reports,
    markets, regions,
    market_contacts, intake,
    intake_luigi, services
)
from routers.auth import require_admin, verify_iap_jwt
from websockets_manager import manager
from services.importer import run_import_job
from database import get_db_connection, init_db, db_cursor_context
from audit_logger import init_audit_log_infrastructure
import os
from contextlib import asynccontextmanager
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from services.drive_manager import DriveManager


async def scheduled_sync_job():
    # Run the heavy, synchronous Google Drive/DB sync in a separate thread 
    # so it doesn't freeze the WebSockets for everyone else!
    print("⏰ Running automated daily sync job...")
    await asyncio.to_thread(run_import_job)

    print("⏰ Running automated Drive Document scanner...")
    await asyncio.to_thread(DriveManager().run_daily_document_sync)
    
    # Give the database a second to settle, then broadcast to all connected UIs
    await asyncio.sleep(2)
    await manager.broadcast('{"action": "REFRESH_ASSETS"}')
    await manager.broadcast('{"action": "REFRESH_BOARD"}')
    print("✅ Automated daily sync complete and broadcasted.")


# Attach the Scheduler to the App Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Database Tables
    init_db()

    # Check Database Connection
    conn = get_db_connection()
    if conn:
        print("✅ System normal. Database connected.")
        conn.close()
    else:
        print("🚨 CRITICAL: Cannot reach Cloud SQL via IAM. Check Service Account permissions.")

    # nitialize BigQuery Audit Logs
    init_audit_log_infrastructure()

    # Start the clock when the server spins up
    scheduler = AsyncIOScheduler()
    
    # Schedule it for 2:00 AM every day
    # You can easily test it by changing it to (trigger='interval', minutes=5)
    scheduler.add_job(scheduled_sync_job, 'cron', hour=11, minute=0)
    # scheduler.add_job(scheduled_sync_job, 'interval', minutes=60)
    
    scheduler.start()
    print("🕰️ Internal Background Scheduler started.")
    
    yield # The app runs here
    
    # Shut down the clock cleanly when the server restarts
    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)

env_origins = os.environ.get("ALLOWED_ORIGINS")

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

# --- GLOBAL ERROR LOGGER ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # 1. Grab the exact endpoint that crashed
    path = request.url.path
    error_msg = str(exc)
    
    # 2. Log it to your BigQuery / Audit DB as the "SYSTEM" user
    try:
        from audit_logger import log_audit_event
        log_audit_event(
            user_id="SYSTEM",
            username="system@server",
            action="SYSTEM_ERROR",
            resource_type="BACKEND",
            details=f"CRASH at {path}: {error_msg}"
        )
    except Exception as log_err:
        print(f"Failed to write to audit log: {log_err}")
        
    # 3. Print the full traceback to the Google Cloud Run console for debugging
    print("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))

    # 4. Return a generic, safe message to the React UI so it doesn't crash
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred and has been logged."}
    )

# Wire up all the separated routes!
app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(assets.router, prefix="/api")
app.include_router(tests.router, prefix="/api")
app.include_router(board.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(markets.router, prefix="/api")
app.include_router(regions.router, prefix="/api")
app.include_router(market_contacts.router, prefix="/api")
app.include_router(intake.router, prefix="/api")
app.include_router(intake_luigi.router, prefix="/api")
app.include_router(services.router, prefix="/api")


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

    # Read the secure JWT header attached by Google IAP
    iap_jwt = websocket.headers.get("x-goog-iap-jwt-assertion")
    
    if not iap_jwt:
        # Fallback for local laptop testing
        if os.environ.get("ENV") == "local":
            username = os.environ.get("MASTER_ADMIN_EMAIL").lower()
        else:
            await websocket.close(code=1008, reason="Unauthorized: Missing IAP identity header")
            return
    else:
        try:
            # Extract and verify the email mathematically from the JWT
            username = verify_iap_jwt(iap_jwt)
        except ValueError as e:
            await websocket.close(code=1008, reason=f"Unauthorized: {str(e)}")
            return

    # Connect to the Websocket Manager
    await manager.connect(websocket, username)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)


@app.get("/api/system/version")
def get_system_version(current_user: dict = Depends(require_admin)):
    """Returns application version and build context from Cloud Build."""
    return {
        "commit_sha": os.environ.get("COMMIT_SHA", "local-dev"),
        "branch": os.environ.get("BRANCH_NAME", "local"),
        "build_id": os.environ.get("BUILD_ID", "untracked-local-build"),
        "repo_name": os.environ.get("REPO_NAME", "local-repo")
    }
