from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
import sqlite3
import uuid
from datetime import datetime, timedelta
from database import DB_FILE
from routers.auth import get_current_user, require_admin, require_write_access
from models import EventCreate, EventUpdate
from websockets_manager import manager
from audit_logger import log_audit_event

router = APIRouter(tags=["Board & Events"])


def get_user_provision_internal(cursor, user_id, year, week_number):
    """Calculates exactly how much capacity a user provides in a specific week,
    accounting for holidays and their start date."""
    cursor.execute('SELECT base_capacity, location, start_week FROM users WHERE id = ?', (user_id,))
    user_data = cursor.fetchone()
    if not user_data: return 0.0
    base_cap, user_location, start_week = user_data

    if start_week is None: start_week = 1
    if week_number < start_week: return 0.0

    # Fetch all relevant events (holidays, team days)
    cursor.execute("""
                   SELECT start_date, end_date
                   FROM events
                   WHERE user_id = ?
                      OR (event_type = 'national_holiday' AND (location = ? OR location = 'Global'))
                      OR event_type = 'team_day'
                   """, (user_id, user_location))
    events = cursor.fetchall()

    week_dates = []
    for day in range(1, 6):
        try:
            week_dates.append(datetime.strptime(f"{year}-W{week_number}-{day}", "%G-W%V-%u").strftime('%Y-%m-%d'))
        except ValueError: continue

    days_off = 0
    for start_str, end_str in events:
        s = datetime.strptime(start_str, "%Y-%m-%d")
        e = datetime.strptime(end_str, "%Y-%m-%d")
        event_dates = [(s + timedelta(days=i)).strftime('%Y-%m-%d') for i in range((e - s).days + 1)]
        days_off += sum(1 for w in week_dates if w in event_dates)

    return max(0.0, base_cap - (days_off * 0.2))


def get_quarter_weeks(q: int):
    if q == 1: return range(1, 14)
    if q == 2: return range(14, 27)
    if q == 3: return range(27, 40)
    if q == 4: return range(40, 53)
    return []


def calculate_weekly_capacity(user_id, year, week_number):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Calculate what the user COULD provide
    provision = get_user_provision_internal(cursor, user_id, year, week_number)

    # Check if they are already assigned to a test this week
    cursor.execute('SELECT 1 FROM assignments WHERE user_id = ? AND year = ? AND week_number = ?',
                   (user_id, year, week_number))
    is_assigned = cursor.fetchone() is not None
    conn.close()

    # If assigned, their remaining capacity for the board is 0
    if is_assigned:
        return 0.0
    return round(provision, 1)

@router.post("/events/")
def create_event(e: EventCreate, background_tasks: BackgroundTasks, current_user: dict = Depends(require_write_access)):
    # 1. PENTESTER RULES: Force their own ID, block system-wide events
    if current_user['role'] == 'pentester':
        if e.event_type in ['national_holiday', 'team_day']:
            raise HTTPException(status_code=403, detail="Only Admins can create National Holidays or Team Days.")
        e.user_id = current_user['id']  # Forcibly assign the event to themselves!

    # 2. ADMIN RULES: Format system-wide events
    if e.event_type in ['national_holiday', 'team_day']:
        e.user_id = None
    if e.event_type == 'team_day':
        e.location = 'Global'

    new_id = str(uuid.uuid4())
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO events (id, user_id, event_type, location, start_date, end_date) VALUES (?, ?, ?, ?, ?, ?)',
              (new_id, e.user_id, e.event_type, e.location, e.start_date, e.end_date))
    conn.commit()
    conn.close()
    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="CREATE_EVENT",
        resource_type="EVENT",
        details="The Holiday has been created."
    )
    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')
    return {"status": "ok"}


@router.put("/events/{event_id}")
def update_event(event_id: str, e: EventUpdate, background_tasks: BackgroundTasks,
                 current_user: dict = Depends(require_write_access)):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # 1. PENTESTER RULES: Check ownership before allowing edit
    if current_user['role'] == 'pentester':
        c.execute("SELECT user_id, event_type FROM events WHERE id = ?", (event_id,))
        row = c.fetchone()
        if not row or row[0] != current_user['id'] or row[1] in ['national_holiday', 'team_day']:
            conn.close()
            raise HTTPException(status_code=403, detail="You can only edit your own personal time off.")

        if e.event_type in ['national_holiday', 'team_day']:
            conn.close()
            raise HTTPException(status_code=403, detail="You cannot change a personal holiday to a system-wide event.")

        e.user_id = current_user['id']  # Forcibly keep the event assigned to themselves

    # 2. ADMIN RULES: Format system-wide events
    if e.event_type in ['national_holiday', 'team_day']:
        e.user_id = None
    if e.event_type == 'team_day':
        e.location = 'Global'

    c.execute('UPDATE events SET user_id=?, event_type=?, location=?, start_date=?, end_date=? WHERE id=?',
              (e.user_id, e.event_type, e.location, e.start_date, e.end_date, event_id))
    conn.commit()
    conn.close()
    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="UPDATE_EVENT",
        resource_type="EVENT",
        details="The Holiday has been Updated."
    )
    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')
    return {"message": "Holiday updated"}


@router.delete("/events/{event_id}")
def delete_event(event_id: str, background_tasks: BackgroundTasks, current_user: dict = Depends(require_write_access)):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # 1. PENTESTER RULES: Check ownership before allowing delete
    if current_user['role'] == 'pentester':
        c.execute("SELECT user_id, event_type FROM events WHERE id = ?", (event_id,))
        row = c.fetchone()
        if not row or row[0] != current_user['id'] or row[1] in ['national_holiday', 'team_day']:
            conn.close()
            raise HTTPException(status_code=403, detail="You can only delete your own personal time off.")

    c.execute('DELETE FROM events WHERE id=?', (event_id,))
    conn.commit()
    conn.close()
    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="DELETE_EVENT",
        resource_type="EVENT",
        details="The Holiday has been deleted."
    )
    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')
    return {"message": "Holiday deleted"}

@router.get("/board/{year}/Q{quarter}")
def get_quarterly_board(year: int, quarter: int, current_user: dict = Depends(get_current_user)):
    weeks = list(get_quarter_weeks(quarter))
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute('SELECT id, name, max_concurrent_per_week FROM services')
    services = [{"id": r[0], "name": r[1], "max_per_week": r[2]} for r in cursor.fetchall()]

    cursor.execute('SELECT id, name, role, location, base_capacity, username, start_week FROM users')
    pentesters = [{"id": r[0], "name": r[1], "role": r[2], "location": r[3], "capacity": r[4], "username": r[5],
                   "start_week": r[6]} for r in cursor.fetchall()]

    # FIX: We fetch the assignments but ignore the static 'allocated_credits' column,
    # recalculating it on-the-fly based on current holidays.
    cursor.execute(
        'SELECT a.test_id, a.user_id, a.week_number, u.name FROM assignments a JOIN users u ON a.user_id = u.id')
    raw_assignments = cursor.fetchall()

    assignments = []
    for r in raw_assignments:
        test_id, user_id, week_number, user_name = r
        dynamic_credits = get_user_provision_internal(cursor, user_id, year, week_number)
        assignments.append({
            "test_id": test_id,
            "user_id": user_id,
            "week_number": week_number,
            "allocated_credits": dynamic_credits,
            "user_name": user_name
        })

    cursor.execute('''
                   SELECT id,
                          name,
                          service_id,
                          credits_per_week,
                          duration_weeks,
                          start_week,
                          start_year,
                          status,
                          whitebox_category,
                          type,
                          (SELECT COUNT(*) FROM test_assets WHERE test_id = tests.id)
                   FROM tests
                   ''')
    all_tests = cursor.fetchall()

    backlog = []
    scheduled = []
    for t in all_tests:
        test_obj = {"id": t[0], "name": t[1], "service_id": t[2], "credits": t[3], "duration": t[4], "startWeek": t[5],
                    "startYear": t[6], "status": t[7], "whitebox_category": t[8], "type": t[9], "asset_count": t[10]}
        if t[5] is None:
            backlog.append(test_obj)
        else:
            scheduled.append(test_obj)

    cursor.execute('''
                   SELECT e.id, e.user_id, e.event_type, e.location, e.start_date, e.end_date, u.name
                   FROM events e
                            LEFT JOIN users u ON e.user_id = u.id
                   ''')
    events = [
        {"id": r[0], "user_id": r[1], "type": r[2], "location": r[3], "start": r[4], "end": r[5], "user_name": r[6]} for
        r in cursor.fetchall()]

    # Matrix for column availability indicators
    cap_matrix = {p["id"]: {w: calculate_weekly_capacity(p["id"], year, w) for w in weeks} for p in pentesters}

    conn.close()

    return {
        "year": year, "quarter": quarter, "weeks": weeks, "services": services,
        "pentesters": pentesters, "capacities": cap_matrix,
        "backlog": backlog, "scheduled": scheduled,
        "assignments": assignments,
        "events": events
    }


@router.delete("/system/wipe")
def wipe_system(background_tasks: BackgroundTasks, current_user: dict = Depends(require_admin)):

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM assignments')
    cursor.execute('DELETE FROM tests')
    cursor.execute('DELETE FROM events')  # Clears all holidays

    # NEW: Free up all assets and clear the link table!
    cursor.execute('DELETE FROM assets')
    cursor.execute('DELETE FROM test_assets')

    conn.commit()
    conn.close()
    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="SYSTEM_WIPE",
        resource_type="SYSTEM",
        details="Triggered full database wipe (Tests, Assignments, Events cleared)."
    )
    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')
    return {"message": "Board wiped clean, all assets freed!"}





