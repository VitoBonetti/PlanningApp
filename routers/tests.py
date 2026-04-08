from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Request
from typing import List
import uuid
import asyncio
from datetime import datetime, timedelta
from database import get_db_connection, get_db_cursor, db_cursor_context
from routers.auth import get_current_user, require_admin, limiter
from routers.board import get_user_provision_internal
from models import TestCreate, TestUpdate, TestSchedule, BulkTestCreate, AssignmentCreate
from websockets_manager import manager
from audit_logger import log_audit_event
from services.drive_manager import background_provision_workspace, background_archive_workspace, background_relocate_workspace

router = APIRouter(tags=["Tests & Assignments"])


def sync_raw_assets_tracking(cursor, test_id: str, action: str, start_week: int = None, start_year: int = None):
    """Synchronizes the test's status directly to the master raw_assets table based on 8 specific rules."""
    
    # 1. Find the master inventory_id(s) linked to this test
    cursor.execute('''
        SELECT a.inventory_id 
        FROM assets a
        JOIN test_assets ta ON a.id = ta.asset_id
        WHERE ta.test_id = %s
    ''', (test_id,))
    assets = cursor.fetchall()
    
    if not assets:
        return
    
    # 2. Extract into a standard Python list
    inventory_ids = [a[0] for a in assets]
        
    # RULES 3 & 8: SCHEDULED or MOVED
    if action == "SCHEDULED":
        # Calculate the Quarter (Q1, Q2, Q3, Q4) based on the week number
        q = 1 if start_week <= 13 else (2 if start_week <= 26 else (3 if start_week <= 39 else 4))
        
        cursor.execute('''
            UPDATE raw_assets 
            SET quarter_planned = %s, year_planned = %s, week_planned = %s, 
                status_manual_tracking = 'Planned'
            WHERE inventory_id = ANY(%s)
        ''', (f"Q{q}", str(start_year), str(start_week), inventory_ids))

    # RULES 4, 6, & 7: UNSCHEDULED, UNABLE, or DELETED
    elif action in ["UNSCHEDULED", "UNABLE", "DELETED"]:
        cursor.execute('''
            UPDATE raw_assets 
            SET quarter_planned = NULL, year_planned = NULL, week_planned = NULL, 
                status_manual_tracking = 'Not Planned'
            WHERE inventory_id = ANY(%s)
        ''', (inventory_ids,))

    # RULE 5: COMPLETED
    elif action == "COMPLETED":
        cursor.execute('''
            UPDATE raw_assets 
            SET status_manual_tracking = 'Completed'
            WHERE inventory_id = ANY(%s)
        ''', (inventory_ids,))


def log_test_history(cursor, test_id: str, action: str, user_id: str, username: str, week_number: int = None, year: int = None):
    """Inserts a state-change record into the test_history table."""
    history_id = str(uuid.uuid4())
    cursor.execute(
        '''INSERT INTO test_history (id, test_id, action, week_number, year, changed_by_user_id, changed_by_username) 
           VALUES (%s, %s, %s, %s, %s, %s, %s)''',
        (history_id, test_id, action, week_number, year, user_id, username)
    )


@router.post("/tests/")
def create_test(
    t: TestCreate, 
    request: Request, 
    background_tasks: BackgroundTasks, 
    current_user: dict = Depends(require_admin), 
    cursor = Depends(get_db_cursor)
):
    new_id = str(uuid.uuid4())
    cursor.execute(
        'INSERT INTO tests (id, name, service_id, type, credits_per_week, duration_weeks, status, whitebox_category) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
        (new_id, t.name, t.service_id, t.type, t.credits_per_week, t.duration_weeks, 'Not Planned',
         t.whitebox_category))

    # 1. STANDARD WORKFLOW: Link existing selected assets
    if t.asset_ids:
        for asset_id in t.asset_ids:
            cursor.execute('INSERT INTO test_assets (test_id, asset_id) VALUES (%s, %s)', (new_id, asset_id))
            cursor.execute('UPDATE assets SET is_assigned = TRUE WHERE id = %s', (asset_id,))
            
    # 2. PURE PROJECT WORKFLOW: No assets, no dummy records. Just the test shell.
    elif t.type == 'project':
        pass 
        
    # 3. MANUAL/ADVERSARY WORKFLOW: Generate a dummy asset automatically!
    else:
        inv_id = f"MANUAL_GEN_{uuid.uuid4().hex[:8]}"
        number = f"MANUAL_TCKT_{uuid.uuid4().hex[:4]}"
        asset_id = str(uuid.uuid4())
        asset_name = f"Manual Asset: {t.name}"
        
        cursor.execute('''
            INSERT INTO raw_assets (inventory_id, legacy_id, number, name, pentest_queue, gost_service, date_first_seen, status_manual_tracking)
            VALUES (%s, '0', %s, %s, TRUE, 'Adversary Simulation', CURRENT_DATE, 'Not Planned')
        ''', (inv_id, number, asset_name))
        
        cursor.execute('''
            INSERT INTO assets (id, inventory_id, ext_id, number, name, market, gost_service, is_assigned)
            VALUES (%s, %s, '0', %s, %s, 'Global', 'Adversary Simulation', TRUE)
        ''', (asset_id, inv_id, number, asset_name))
        
        cursor.execute('INSERT INTO test_assets (test_id, asset_id) VALUES (%s, %s)', (new_id, asset_id))

    # Logging and Background Tasks
    log_test_history(cursor, new_id, "CREATED", current_user["id"], current_user["username"])
    
    cursor.connection.commit()
    
    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')
    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_ASSETS"}')

    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="CREATE_TEST",
        resource_type="PROJECT" if t.type == 'project' else "TEST",
        resource_id=new_id,
        details=f"Created new {t.type}: {t.name}"
    )

    return {"status": "ok", "id": new_id}


# --- BACKGROUND WORKER: Bulk Test Generator ---
# THIS IS THE ONLY ONE THAT USES db_cursor_context()
def process_bulk_tests_background(asset_ids: List[str]):
    with db_cursor_context() as cursor:
        if not cursor:
            print("Background Bulk Test Failed: Could not get DB cursor.")
            return
        cursor.execute('SELECT id, name FROM services')
        services = cursor.fetchall()
        fallback_service_id = services[0][0] if services else ""
    
        for asset_id in asset_ids:
            # 1. Fetch whitebox_category from the asset!
            cursor.execute('SELECT name, gost_service, whitebox_category FROM assets WHERE id = %s', (asset_id,))
            asset = cursor.fetchone()
            if not asset: continue
    
            asset_name, gost, whitebox_cat = asset
            gost = str(gost).lower()
            matched_service_id = fallback_service_id
    
            for s_id, s_name in services:
                s_name_lower = s_name.lower()
                if ('black' in gost and 'black' in s_name_lower) or ('white' in gost and 'white' in s_name_lower) or (
                        'adversary' in gost and 'adversary' in s_name_lower) or (
                        'project' in gost and 'project' in s_name_lower):
                    matched_service_id = s_id
                    break
    
            new_test_id = str(uuid.uuid4())
    
            # 2. Insert the whitebox_cat into the tests table!
            cursor.execute(
                'INSERT INTO tests (id, name, service_id, type, credits_per_week, duration_weeks, status, whitebox_category) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                (new_test_id, asset_name, matched_service_id, 'test', 2.0, 1.0, 'Not Planned', whitebox_cat)
            )
            cursor.execute('INSERT INTO test_assets (test_id, asset_id) VALUES (%s, %s)', (new_test_id, asset_id))
            cursor.execute('UPDATE assets SET is_assigned = TRUE WHERE id = %s', (asset_id,))


# Triggers Bulk Generation ---
@router.post("/tests/bulk")
@limiter.limit("3/minute")
def bulk_create_tests(req: BulkTestCreate, request: Request, background_tasks: BackgroundTasks,
                      current_user: dict = Depends(require_admin)):

    background_tasks.add_task(process_bulk_tests_background, req.asset_ids)
    
    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')

    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="BULK_CREATE_TESTS",
        resource_type="TEST_BATCH",
        details=f"Initiated background generation of {len(req.asset_ids)} tests from assets."
    )
            
    return {"message": f"Generating {len(req.asset_ids)} tests in the background!"}


@router.put("/tests/{test_id}/schedule")
def schedule_test(test_id: str, schedule: TestSchedule, background_tasks: BackgroundTasks, current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):

    # 1. Fetch test details (duration, required credits)
    cursor.execute("SELECT duration_weeks, credits_per_week FROM tests WHERE id = %s", (test_id,))
    test_row = cursor.fetchone()
    duration_weeks = int(test_row[0]) if test_row else 1
    credits_per_week = float(test_row[1]) if test_row else 0.0

    # 2. Get currently assigned users
    cursor.execute("SELECT DISTINCT user_id FROM assignments WHERE test_id = %s", (test_id,))
    assigned_users = [row[0] for row in cursor.fetchall()]

    # 3. Delete existing assignments (clearing the "ghosts" from the old week)
    cursor.execute("DELETE FROM assignments WHERE test_id = %s", (test_id,))

    # 4. Re-assign them to the NEW week with collision handling
    for user_id in assigned_users:
        user_assigned_any_week = False
        
        for offset in range(duration_weeks):
            target_week = schedule.start_week + offset
            target_year = schedule.start_year
            if target_week > 52:
                target_week -= 52
                target_year += 1

            # Check capacity in the new week
            provision = get_user_provision_internal(cursor, user_id, target_year, target_week)
            cursor.execute('''
                SELECT SUM(a.allocated_credits) FROM assignments a
                JOIN tests t ON a.test_id = t.id
                WHERE a.user_id = %s AND a.year = %s AND a.week_number = %s AND t.status != 'Unable'
            ''', (user_id, target_year, target_week))
            used = cursor.fetchone()[0] or 0.0
            
            available = max(0.0, provision - used)

            # Only assign them if they actually have room
            if available > 0:
                credits_to_assign = min(available, credits_per_week)
                cursor.execute(
                    'INSERT INTO assignments (id, test_id, user_id, week_number, year, allocated_credits) VALUES (%s, %s, %s, %s, %s, %s)',
                    (str(uuid.uuid4()), test_id, user_id, target_week, target_year, credits_to_assign)
                )
                user_assigned_any_week = True

        # If they had 0 capacity across all weeks, drop them and notify them
        if not user_assigned_any_week:
            notif_id = str(uuid.uuid4())
            cursor.execute("SELECT name FROM tests WHERE id = %s", (test_id,))
            tname_row = cursor.fetchone()
            tname = tname_row[0] if tname_row else "a test"
            cursor.execute("INSERT INTO notifications (id, user_id, message, type) VALUES (%s, %s, %s, %s)",
                           (notif_id, user_id, f"You were removed from {tname} due to a scheduling conflict.", "REMOVAL"))

    # Finally, update the test location
    cursor.execute('UPDATE tests SET start_week = %s, start_year = %s, status = %s WHERE id = %s', (schedule.start_week, schedule.start_year, "Planned", test_id))

    sync_raw_assets_tracking(cursor, test_id, "SCHEDULED", schedule.start_week, schedule.start_year)

    log_test_history(cursor, test_id, f"SCHEDULED", current_user["id"], current_user["username"], schedule.start_week, schedule.start_year)
    cursor.connection.commit()
    
    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')

    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="SCHEDULE_TEST",
        resource_type="TEST",
        resource_id=test_id,
        details=f"Scheduled test for Week {schedule.start_week}, {schedule.start_year}. Checked for collisions."
    )

    cursor.execute("""
        SELECT t.name, t.type, s.name, a.market, t.drive_folder_id 
        FROM tests t
        JOIN services s ON t.service_id = s.id
        LEFT JOIN test_assets ta ON t.id = ta.test_id
        LEFT JOIN assets a ON ta.asset_id = a.id
        WHERE t.id = %s LIMIT 1
    """, (test_id,))
    test_data = cursor.fetchone()
    
    if test_data:
        t_name, t_type, s_name, t_market, drive_id = test_data
        target_year = schedule.start_year
        
        # Only touch Drive if it's an actual test
        if t_type != 'project' and target_year:
            if not drive_id:
                # 1. First time being scheduled: Create the folder
                background_tasks.add_task(
                    background_provision_workspace,
                    test_id=test_id,
                    year=target_year,
                    service_name=s_name,
                    market=t_market,
                    test_name=t_name
                )
            else:
                # 2. Already has a folder: Relocate it to the new Year!
                background_tasks.add_task(
                    background_relocate_workspace,
                    folder_id=drive_id,
                    year=target_year,
                    service_name=s_name,
                    market=t_market,
                    test_name=t_name
                )

    return {"message": "Scheduled and assignments validated"}


@router.put("/tests/{test_id}/unschedule")
def unschedule_test(test_id: str, background_tasks: BackgroundTasks, current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):

    # fetch assigned users and test name BEFORE deleting
    cursor.execute('SELECT user_id FROM assignments WHERE test_id = %s', (test_id,))
    assigned_users = cursor.fetchall()
    
    cursor.execute("SELECT name FROM tests WHERE id = %s", (test_id,))
    test_row = cursor.fetchone()
    
    if test_row:
        # Insert removal notifications for everyone assigned
        for (user_id,) in assigned_users:
            notif_id = str(uuid.uuid4())
            cursor.execute("INSERT INTO notifications (id, user_id, message, type) VALUES (%s, %s, %s, %s)",
                           (notif_id, user_id, f"You were removed from {test_row[0]} because it was unscheduled.",
                            "REMOVAL"))
    
    # deletion
    cursor.execute('DELETE FROM assignments WHERE test_id = %s', (test_id,))
    cursor.execute('UPDATE tests SET start_week = NULL, start_year = NULL, status = %s WHERE id = %s',
                   ("Not Planned", test_id,))

    sync_raw_assets_tracking(cursor, test_id, "UNSCHEDULED")

    log_test_history(cursor, test_id, "DELETE_TEST", current_user["id"], current_user["username"])
    cursor.connection.commit()
    
    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')
    
    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="UNSCHEDULE_TEST",
        resource_type="TEST",
        resource_id=test_id,
        details="Moved test back to backlog and cleared assignments."
    )

    log_test_history(cursor, test_id, "UNSCHEDULED", current_user["id"], current_user["username"])
    
    return {"message": "Unscheduled"}


@router.delete("/tests/{test_id}")
@limiter.limit("5/minute")
def delete_test(test_id: str, request: Request, background_tasks: BackgroundTasks, current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):

    cursor.execute("SELECT name, drive_folder_id FROM tests WHERE id = %s", (test_id,))
    test_data = cursor.fetchone()
    
    if test_data and test_data[1]:
        # Rename it to [DELETED] in Drive
        background_tasks.add_task(background_archive_workspace, folder_id=test_data[1], test_name=test_data[0])

    # Find all assets attached to this test and free them!
    cursor.execute('SELECT asset_id FROM test_assets WHERE test_id = %s', (test_id,))
    linked_assets = cursor.fetchall()

    sync_raw_assets_tracking(cursor, test_id, "DELETED")
    
    for (asset_id,) in linked_assets:
        cursor.execute('UPDATE assets SET is_assigned = FALSE WHERE id = %s', (asset_id,))
    
    # Delete the links from the junction table
    cursor.execute('DELETE FROM test_assets WHERE test_id = %s', (test_id,))
    
    # Delete assignments and the test itself
    cursor.execute('DELETE FROM assignments WHERE test_id = %s', (test_id,))
    cursor.execute('DELETE FROM tests WHERE id = %s', (test_id,))
    cursor.connection.commit()

    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')
    
    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="DELETE_TEST",
        resource_type="TEST",
        resource_id=test_id,
        details=f"Permanently delete test: {test_id}"
    )

    return {"message": "Test permanently deleted and assets freed."}


@router.put("/tests/{test_id}")
@limiter.limit("10/minute")
def update_test(test_id: str, request: Request, background_tasks: BackgroundTasks, t: TestUpdate, current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):
   
    # Fetch current Drive ID BEFORE we update anything
    cursor.execute("""
        SELECT t.drive_folder_id, t.start_year, a.market
        FROM tests t
        LEFT JOIN test_assets ta ON t.id = ta.test_id
        LEFT JOIN assets a ON ta.asset_id = a.id
        WHERE t.id = %s LIMIT 1
    """, (test_id,))
    existing_data = cursor.fetchone()
    drive_folder_id = existing_data[0] if existing_data else None
    start_year = existing_data[1] if existing_data else None
    market = existing_data[2] if existing_data else None

    # If an Admin forces the status back to 'Not Planned', we must clear it off the board!
    if t.status == 'Not Planned':
        cursor.execute('DELETE FROM assignments WHERE test_id = %s', (test_id,))
        cursor.execute('UPDATE tests SET start_week = NULL, start_year = NULL WHERE id = %s', (test_id,))
    
    # Update everything else, safely saving the new Status!
    cursor.execute('''
        UPDATE tests 
        SET name=%s, service_id=%s, credits_per_week=%s, duration_weeks=%s, 
            status=COALESCE(%s, status), whitebox_category=%s,
            drive_folder_url=COALESCE(%s, drive_folder_url)
        WHERE id=%s
    ''', (
        t.name, t.service_id, t.credits_per_week, t.duration_weeks, 
        t.status, t.whitebox_category, t.drive_folder_url, 
        test_id
    ))

    # Trigger Relocation (Move the Google Drive folder and all contents!)
    if drive_folder_id and start_year:
        # We need the NEW service name to know which folder to move it to
        cursor.execute("SELECT name FROM services WHERE id = %s", (t.service_id,))
        new_service_name = cursor.fetchone()[0]

        background_tasks.add_task(
            background_relocate_workspace,
            folder_id=drive_folder_id,
            year=start_year,
            service_name=new_service_name,
            market=market,
            test_name=t.name
        )

    cursor.connection.commit()
    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')
    
    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="UPDATE_TEST",
        resource_type="TEST",
        resource_id=test_id,
        details=f"Updated test attributes and relocated Drive folder if necessary."
    )
    
    return {"message": "Test updated successfully."}


@router.put("/tests/{test_id}/complete")
def complete_test(test_id: str, background_tasks: BackgroundTasks, current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):

    cursor.execute("UPDATE tests SET status = 'Completed' WHERE id = %s", (test_id,))

    sync_raw_assets_tracking(cursor, test_id, "COMPLETED")

    log_test_history(cursor, test_id, "COMPLETED", current_user["id"], current_user["username"])
    cursor.connection.commit()

    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')
    
    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="COMPLETE_TEST",
        resource_type="TEST",
        resource_id=test_id,
        details="Marked test as Completed."
    )
    
    return {"message": "Test marked as Completed."}


@router.post("/tests/{test_id}/duplicate")
def duplicate_test(test_id: str, background_tasks: BackgroundTasks, current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):

    # 1. Fetch the original test
    cursor.execute('SELECT name, service_id, type, credits_per_week, duration_weeks FROM tests WHERE id = %s',
                   (test_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Test not found.")
    
    name, service_id, t_type, credits, duration = row
    new_test_id = str(uuid.uuid4())
    
    # 2. Insert the clone into the Backlog (Adding " (Copy)" so you can tell them apart easily)
    cursor.execute(
        'INSERT INTO tests (id, name, service_id, type, credits_per_week, duration_weeks, status) VALUES (%s, %s, %s, %s, %s, %s, %s)',
        (new_test_id, f"{name}", service_id, t_type, credits, duration, 'Not Planned')
    )
    
    # 3. Clone the asset links too!
    cursor.execute('SELECT asset_id FROM test_assets WHERE test_id = %s', (test_id,))
    assets = cursor.fetchall()
    for (asset_id,) in assets:
        cursor.execute('INSERT INTO test_assets (test_id, asset_id) VALUES (%s, %s)', (new_test_id, asset_id))
    
    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')
    
    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="DUPLICATE_TEST",
        resource_type="TEST",
        resource_id=new_test_id,  # Use the ID of the newly created clone
        details=f"Duplicated test from original ID: {test_id}"
    )
    
    return {"message": "Project duplicated to the Backlog!"}


@router.put("/tests/{test_id}/unable")
def mark_test_unable(test_id: str, background_tasks: BackgroundTasks, current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):
    # 1. Fetch the original test details
    cursor.execute('SELECT name, service_id, type, credits_per_week, duration_weeks, start_week, start_year, whitebox_category FROM tests WHERE id = %s', (test_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Test not found.")
    
    name, service_id, t_type, credits, duration, start_week, start_year, whitebox_cat = row

    # 2. Create the "Tombstone" Clone to stay permanently on the board
    tombstone_id = str(uuid.uuid4())
    cursor.execute(
        'INSERT INTO tests (id, name, service_id, type, credits_per_week, duration_weeks, start_week, start_year, status, whitebox_category) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
        (tombstone_id, name, service_id, t_type, credits, duration, start_week, start_year, 'Unable', whitebox_cat)
    )

    # 3. Move the burned assignments to the Tombstone (shows who wasted their time)
    cursor.execute('UPDATE assignments SET test_id = %s WHERE test_id = %s', (tombstone_id, test_id))

    # 4. Clone the asset relationships to the Tombstone so the historical record is accurate
    cursor.execute('SELECT asset_id FROM test_assets WHERE test_id = %s', (test_id,))
    assets = cursor.fetchall()
    for (asset_id,) in assets:
        cursor.execute('INSERT INTO test_assets (test_id, asset_id) VALUES (%s, %s)', (tombstone_id, asset_id))

    # 5. Send the ORIGINAL test back to the Backlog! (Preserves the exact UUID)
    cursor.execute("UPDATE tests SET start_week = NULL, start_year = NULL, status = 'Not Planned' WHERE id = %s", (test_id,))

    sync_raw_assets_tracking(cursor, test_id, "UNABLE")

    # 6. Log the state changes in our new history table!
    log_test_history(cursor, test_id, "MARKED_UNABLE (Returned to Backlog)", current_user["id"], current_user["username"])
    log_test_history(cursor, tombstone_id, "TOMBSTONE_CREATED_ON_BOARD", current_user["id"], current_user["username"], start_week, start_year)

    cursor.connection.commit()

    # 7. Instant UI Refresh FIRST!
    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')
    
    # 8. Silent Audit Log
    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="MARK_UNABLE",
        resource_type="TEST",
        resource_id=test_id,
        details=f"Marked '{name}' as Unable. Tombstone left on board, original returned to backlog."
    )
    
    return {"message": "Test marked as Unable. Original preserved in backlog."}


@router.get("/tests/{test_id}/history")
def get_test_history(test_id: str, current_user: dict = Depends(get_current_user), cursor = Depends(get_db_cursor)):
    """Retrieves the state-change timeline for a specific test."""
    cursor.execute('''
        SELECT action, week_number, year, changed_by_username, timestamp
        FROM test_history
        WHERE test_id = %s
        ORDER BY timestamp DESC
    ''', (test_id,))
    
    rows = cursor.fetchall()
    return [
        {
            "action": r[0],
            "week_number": r[1],
            "year": r[2],
            "username": r[3],
            "timestamp": r[4]
        } for r in rows
    ]
    

@router.put("/tests/{test_id}/revert_complete")
def revert_test_complete(test_id: str, background_tasks: BackgroundTasks, current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):
    """Reverts a 'Completed' test back to 'Planned'."""
    cursor.execute("UPDATE tests SET status = 'Planned' WHERE id = %s", (test_id,))
    
    log_test_history(cursor, test_id, "REVERTED_COMPLETION", current_user["id"], current_user["username"])
    cursor.connection.commit()

    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')
    return {"message": "Test reverted to Planned."}


@router.put("/tests/{tombstone_id}/revert_unable")
def revert_test_unable(tombstone_id: str, background_tasks: BackgroundTasks, current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):
    """Destroys the Tombstone and puts the original Backlog test back on the board."""
    # 1. Get the tombstone's data
    cursor.execute('SELECT name, service_id, start_week, start_year FROM tests WHERE id = %s', (tombstone_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Tombstone not found.")
    name, service_id, start_week, start_year = row

    # 2. Find the Original test waiting in the backlog
    cursor.execute("SELECT id FROM tests WHERE name = %s AND service_id = %s AND status = 'Not Planned' LIMIT 1", (name, service_id))
    original = cursor.fetchone()

    if original:
        original_id = original[0]
        # Move assignments back to the original test
        cursor.execute('UPDATE assignments SET test_id = %s WHERE test_id = %s', (original_id, tombstone_id))
        # Schedule the original test again
        cursor.execute("UPDATE tests SET start_week = %s, start_year = %s, status = 'Scheduled' WHERE id = %s", (start_week, start_year, original_id))
        log_test_history(cursor, original_id, "REVERTED_UNABLE", current_user["id"], current_user["username"])

    # 3. Destroy the Tombstone's child records FIRST!
    cursor.execute('DELETE FROM test_assets WHERE test_id = %s', (tombstone_id,))
    
    # 4. Now it is safe to delete the Tombstone itself
    cursor.execute('DELETE FROM tests WHERE id = %s', (tombstone_id,))

    cursor.connection.commit()

    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')
    return {"message": "Unable status reverted."}


@router.post("/assignments/")
def create_assignment(assign: AssignmentCreate, background_tasks: BackgroundTasks, current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):

    # Prevent double booking for this week, EXCLUDING 'Unable' tests!
    cursor.execute('''
        SELECT a.id FROM assignments a
        JOIN tests t ON a.test_id = t.id
        WHERE a.user_id = %s AND a.week_number = %s AND a.year = %s AND a.test_id = %s AND t.status != 'Unable'
    ''', (assign.user_id, assign.week_number, assign.year, assign.test_id))
    if cursor.fetchone():
        raise HTTPException(status_code=400, detail="This pentester is already assigned to this test for this week!")

    provision = get_user_provision_internal(cursor, assign.user_id, assign.year, assign.week_number)
    
    cursor.execute('''
        SELECT SUM(a.allocated_credits) FROM assignments a
        JOIN tests t ON a.test_id = t.id
        WHERE a.user_id = %s AND a.year = %s AND a.week_number = %s AND t.status != 'Unable'
    ''', (assign.user_id, assign.year, assign.week_number))
    used = cursor.fetchone()[0] or 0.0
    
    available = max(0.0, provision - used)
    
    # Reject if capacity is 0 or less!
    if available <= 0:
        raise HTTPException(status_code=400, detail=f"Cannot assign: Pentester has 0 capacity remaining in Week {assign.week_number}.")
    
    # Assign either the required credits, or whatever capacity they have left
    credits_to_assign = min(available, assign.allocated_credits)
    
    new_id = str(uuid.uuid4())
    cursor.execute(
        'INSERT INTO assignments (id, test_id, user_id, week_number, year, allocated_credits) VALUES (%s, %s, %s, %s, %s, %s)',
        (new_id, assign.test_id, assign.user_id, assign.week_number, assign.year, credits_to_assign))
    
    cursor.execute("SELECT name FROM tests WHERE id = %s", (assign.test_id,))
    test_row = cursor.fetchone()
    if test_row:
        notif_id = str(uuid.uuid4())
        cursor.execute("INSERT INTO notifications (id, user_id, message, type) VALUES (%s, %s, %s, %s)",
                       (notif_id, assign.user_id, f"You were assigned to {test_row[0]} for Week {assign.week_number}.", "ASSIGNMENT"))

    cursor.connection.commit()
    
    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')

    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="ASSIGN_PENTESTER",
        resource_type="ASSIGNMENT",
        resource_id=assign.test_id,
        details=f"Assigned user {assign.user_id} to test for Week {assign.week_number}."
    )
    
    return {"message": "Assigned"}


@router.delete("/assignments/{test_id}/{user_id}")
@limiter.limit("5/minute")
def remove_assignment(test_id: str, user_id: str, request: Request, background_tasks: BackgroundTasks, current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):

    cursor.execute("SELECT name FROM tests WHERE id = %s", (test_id,))
    test_row = cursor.fetchone()
    if test_row:
        notif_id = str(uuid.uuid4())
        cursor.execute("INSERT INTO notifications (id, user_id, message, type) VALUES (%s, %s, %s, %s)",
                       (notif_id, user_id, f"You were removed from {test_row[0]}.", "REMOVAL"))
    cursor.execute('DELETE FROM assignments WHERE test_id = %s AND user_id = %s', (test_id, user_id))
    cursor.connection.commit()
    
    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')

    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="REMOVE_ASSIGNMENT",
        resource_type="ASSIGNMENT",
        resource_id=test_id,
        details=f"Removed user {user_id} from test."
    )
    
    return {"message": "Unassigned"}