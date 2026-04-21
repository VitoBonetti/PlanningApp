from fastapi import APIRouter, Depends, BackgroundTasks
from backend.database import get_db_cursor, db_cursor_context
from backend.routers.auth import get_current_user, require_admin
from backend.services.drive_manager import DriveManager

router = APIRouter(tags=["Reports & Documents"])

@router.get("/reports/directory")
def get_reports_directory(current_user: dict = Depends(get_current_user), cursor = Depends(get_db_cursor)):
    # This query flattens everything so the frontend React table is incredibly fast to sort/filter
    cursor.execute('''
        SELECT 
            d.id, d.file_name, d.file_url, d.mime_type, d.last_modified,
            t.name as test_name, t.start_year, 
            s.name as service_name, 
            a.name as asset_name, a.market
        FROM test_documents d
        JOIN tests t ON d.test_id = t.id
        JOIN services s ON t.service_id = s.id
        LEFT JOIN test_assets ta ON t.id = ta.test_id
        LEFT JOIN assets a ON ta.asset_id = a.id
        ORDER BY d.last_modified DESC
    ''')
    
    rows = cursor.fetchall()
    documents = []
    
    for r in rows:
        documents.append({
            "id": r[0],
            "file_name": r[1],
            "file_url": r[2],
            "mime_type": r[3],
            "last_modified": r[4],
            "test_name": r[5],
            "year": r[6],
            "service": r[7],
            "asset_name": r[8] or 'N/A (Project)',
            "market": r[9] or 'N/A'
        })
        
    return {"documents": documents}


@router.post("/reports/sync")
def trigger_manual_document_sync(background_tasks: BackgroundTasks, current_user: dict = Depends(require_admin)):
    """Manually triggers the Drive folder scan in the background."""
    # The require_admin dependency already protects this route!
    background_tasks.add_task(DriveManager().run_daily_document_sync)
    return {"message": "Drive document sync initiated in the background."}


@router.post("/reports/cleanup-orphans")
def trigger_orphan_cleanup(background_tasks: BackgroundTasks, current_user: dict = Depends(require_admin)):
    """Deletes files from the DB that haven't been seen by the scanner in the last 24 hours."""
    
    def cleanup_task():
        with db_cursor_context() as cursor:
            # Delete any document that wasn't 'touched' by the scanner in the last 24 hours
            cursor.execute("DELETE FROM test_documents WHERE synced_at < NOW() - INTERVAL '1 day'")
            deleted_count = cursor.rowcount
            print(f"🧹 Orphan Cleanup: Removed {deleted_count} deleted Drive files from database.")

    background_tasks.add_task(cleanup_task)
    return {"message": "Orphan cleanup initiated in the background."}