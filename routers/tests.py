from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from typing import List
import sqlite3
import uuid
from datetime import datetime, timedelta
from database import DB_FILE
from routers.auth import get_current_user
from models import TestCreate, TestUpdate, TestSchedule, BulkTestCreate, AssignmentCreate
from websockets_manager import manager

router = APIRouter(tags=["Tests & Assignments"])


@router.post("/tests/")
def create_test(t: TestCreate, current_user: dict = Depends(get_current_user)):
    if current_user['role'] == 'read_only':
        raise HTTPException(status_code=403, detail="Read Only")

    new_id = str(uuid.uuid4())

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        'INSERT INTO tests (id, name, service_id, type, credits_per_week, duration_weeks, status) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (new_id, t.name, t.service_id, t.type, t.credits_per_week, t.duration_weeks, 'Not Planned'))

    # NEW: Link the assets and mark them as assigned!
    if t.asset_ids:
        for asset_id in t.asset_ids:
            # 1. Add to junction table
            c.execute('INSERT INTO test_assets (test_id, asset_id) VALUES (?, ?)', (new_id, asset_id))
            # 2. Mark the asset as assigned so it vanishes from the available pool
            c.execute('UPDATE assets SET is_assigned = 1 WHERE id = ?', (asset_id,))

    conn.commit()
    conn.close()
    return {"status": "ok", "id": new_id}


# --- BACKGROUND WORKER: Bulk Test Generator ---
def process_bulk_tests_background(asset_ids: List[str]):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    cursor = conn.cursor()

    # 1. Get all services so we can auto-match White/Black box
    cursor.execute('SELECT id, name FROM services')
    services = cursor.fetchall()
    fallback_service_id = services[0][0] if services else ""

    for asset_id in asset_ids:
        # Get the asset details
        cursor.execute('SELECT name, gost_service FROM assets WHERE id = ?', (asset_id,))
        asset = cursor.fetchone()
        if not asset: continue

        asset_name, gost = asset
        gost = str(gost).lower()

        # Auto-match the service lane
        matched_service_id = fallback_service_id
        for s_id, s_name in services:
            s_name_lower = s_name.lower()

            # Check for our 4 core lane keywords
            if ('black' in gost and 'black' in s_name_lower) or \
                    ('white' in gost and 'white' in s_name_lower) or \
                    ('adversary' in gost and 'adversary' in s_name_lower) or \
                    ('project' in gost and 'project' in s_name_lower):
                matched_service_id = s_id
                break

        new_test_id = str(uuid.uuid4())

        # Create Test (Defaults: 2.0 credits, 1.0 weeks)
        cursor.execute(
            'INSERT INTO tests (id, name, service_id, type, credits_per_week, duration_weeks, status) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (new_test_id, asset_name, matched_service_id, 'test', 2.0, 1.0, 'Not Planned'))

        # Link Asset and mark assigned
        cursor.execute('INSERT INTO test_assets (test_id, asset_id) VALUES (?, ?)', (new_test_id, asset_id))
        cursor.execute('UPDATE assets SET is_assigned = 1 WHERE id = ?', (asset_id,))

    conn.commit()
    conn.close()


# Triggers Bulk Generation ---
@router.post("/tests/bulk")
def bulk_create_tests(req: BulkTestCreate, background_tasks: BackgroundTasks,
                      current_user: dict = Depends(get_current_user)):
    if current_user['role'] == 'read_only': raise HTTPException(status_code=403, detail="Read Only")

    background_tasks.add_task(process_bulk_tests_background, req.asset_ids)
    return {"message": f"Generating {len(req.asset_ids)} tests in the background!"}

@router.put("/tests/{test_id}/schedule")
def schedule_test(test_id: str, schedule: TestSchedule, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE tests SET start_week = ?, start_year = ?, status = "Planned" WHERE id = ?', (schedule.start_week, schedule.start_year, test_id))
    conn.commit()
    conn.close()

    # THE MAGIC: Tell everyone else to refresh their screen!
    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')

    return {"message": "Scheduled"}


@router.put("/tests/{test_id}/unschedule")
def unschedule_test(test_id: str, current_user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM assignments WHERE test_id = ?', (test_id,))
    cursor.execute('UPDATE tests SET start_week = NULL, start_year = NULL, status = "Not Planned" WHERE id = ?',
                   (test_id,))
    conn.commit()
    conn.close()
    return {"message": "Unscheduled"}


@router.delete("/tests/{test_id}")
def delete_test(test_id: str, current_user: dict = Depends(get_current_user)):
    if current_user['role'] not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Only Admins/Managers can delete tests.")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # 1. NEW: Find all assets attached to this test and free them!
    cursor.execute('SELECT asset_id FROM test_assets WHERE test_id = ?', (test_id,))
    linked_assets = cursor.fetchall()

    for (asset_id,) in linked_assets:
        cursor.execute('UPDATE assets SET is_assigned = 0 WHERE id = ?', (asset_id,))

    # 2. NEW: Delete the links from the junction table
    cursor.execute('DELETE FROM test_assets WHERE test_id = ?', (test_id,))

    # 3. ORIGINAL: Delete assignments and the test itself
    cursor.execute('DELETE FROM assignments WHERE test_id = ?', (test_id,))
    cursor.execute('DELETE FROM tests WHERE id = ?', (test_id,))

    conn.commit()
    conn.close()
    return {"message": "Test permanently deleted and assets freed."}


@router.put("/tests/{test_id}")
def update_test(test_id: str, t: TestUpdate, current_user: dict = Depends(get_current_user)):
    if current_user['role'] not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Only Admins/Managers can edit tests.")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # If an Admin forces the status back to 'Not Planned', we must clear it off the board!
    if t.status == 'Not Planned':
        cursor.execute('DELETE FROM assignments WHERE test_id = ?', (test_id,))
        cursor.execute('UPDATE tests SET start_week = NULL, start_year = NULL WHERE id = ?', (test_id,))

    # Update everything else, safely saving the new Status!
    cursor.execute('''
                   UPDATE tests
                   SET name             = ?,
                       service_id       = ?,
                       credits_per_week = ?,
                       duration_weeks   = ?,
                       status           = COALESCE(?, status)
                   WHERE id = ?
                   ''', (t.name, t.service_id, t.credits_per_week, t.duration_weeks, t.status, test_id))
    conn.commit()
    conn.close()
    return {"message": "Test updated successfully."}


@router.put("/tests/{test_id}/complete")
def complete_test(test_id: str, current_user: dict = Depends(get_current_user)):
    if current_user['role'] not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Only Admins/Managers can complete tests.")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE tests SET status = 'Completed' WHERE id = ?", (test_id,))
    conn.commit()
    conn.close()
    return {"message": "Test marked as Completed."}


@router.post("/tests/{test_id}/duplicate")
def duplicate_test(test_id: str, current_user: dict = Depends(get_current_user)):
    if current_user['role'] not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Not authorized.")

    conn = sqlite3.connect(DB_FILE, timeout=10)
    cursor = conn.cursor()

    # 1. Fetch the original test
    cursor.execute('SELECT name, service_id, type, credits_per_week, duration_weeks FROM tests WHERE id = ?',
                   (test_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Test not found.")

    name, service_id, t_type, credits, duration = row
    new_test_id = str(uuid.uuid4())

    # 2. Insert the clone into the Backlog (Adding " (Copy)" so you can tell them apart easily)
    cursor.execute(
        'INSERT INTO tests (id, name, service_id, type, credits_per_week, duration_weeks, status) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (new_test_id, f"{name}", service_id, t_type, credits, duration, 'Not Planned')
    )

    # 3. Clone the asset links too!
    cursor.execute('SELECT asset_id FROM test_assets WHERE test_id = ?', (test_id,))
    assets = cursor.fetchall()
    for (asset_id,) in assets:
        cursor.execute('INSERT INTO test_assets (test_id, asset_id) VALUES (?, ?)', (new_test_id, asset_id))

    conn.commit()
    conn.close()
    return {"message": "Project duplicated to the Backlog!"}


@router.post("/assignments/")
def create_assignment(assign: AssignmentCreate, current_user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # NEW RULE: Prevent double booking for this week!
    cursor.execute('SELECT id FROM assignments WHERE user_id = ? AND week_number = ? AND year = ?',
                   (assign.user_id, assign.week_number, assign.year))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="This pentester is already assigned to a test this week!")

    # NEW RULE: Calculate actual capacity to assign (base minus holidays)
    cursor.execute('SELECT base_capacity, location FROM users WHERE id = ?', (assign.user_id,))
    base_cap, user_location = cursor.fetchone()
    cursor.execute(
        "SELECT start_date, end_date FROM events WHERE user_id = ? OR "
        "(event_type = 'national_holiday' AND (location = ? OR location = 'Global'))",
        (assign.user_id, user_location)
    )
    events = cursor.fetchall()

    week_dates = []
    for day in range(1, 6):
        try:
            week_dates.append(
                datetime.strptime(f"{assign.year}-W{assign.week_number}-{day}", "%G-W%V-%u").strftime('%Y-%m-%d'))
        except ValueError:
            continue

    days_off = 0
    for s_str, e_str in events:
        s = datetime.strptime(s_str, "%Y-%m-%d");
        e = datetime.strptime(e_str, "%Y-%m-%d")
        event_dates = [(s + timedelta(days=i)).strftime('%Y-%m-%d') for i in range((e - s).days + 1)]
        days_off += sum(1 for w in week_dates if w in event_dates)

    # The actual capacity they bring to the test this week
    actual_provided = max(0.0, base_cap - (days_off * 0.2))

    # NEW IRON-CLAD LOCK: Reject if capacity is 0 or less!
    if actual_provided <= 0:
        conn.close()
        raise HTTPException(status_code=400,
                            detail=f"Cannot assign: Pentester is on holiday/has 0 capacity in Week {assign.week_number}.")

    new_id = str(uuid.uuid4())
    cursor.execute(
        'INSERT INTO assignments (id, test_id, user_id, week_number, year, allocated_credits) VALUES (?, ?, ?, ?, ?, ?)',
        (new_id, assign.test_id, assign.user_id, assign.week_number, assign.year, actual_provided))
    conn.commit()
    conn.close()
    return {"message": "Assigned"}


@router.delete("/assignments/{test_id}/{user_id}")
def remove_assignment(test_id: str, user_id: str, current_user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM assignments WHERE test_id = ? AND user_id = ?', (test_id, user_id))
    conn.commit()
    conn.close()
    return {"message": "Unassigned"}