from fastapi import APIRouter, HTTPException, Depends
import sqlite3
import uuid
from datetime import datetime, timedelta
from database import DB_FILE
from routers.auth import get_current_user
from models import EventCreate, EventUpdate

router = APIRouter(tags=["Board & Events"])


def get_quarter_weeks(q: int):
    if q == 1: return range(1, 14)
    if q == 2: return range(14, 27)
    if q == 3: return range(27, 40)
    if q == 4: return range(40, 53)
    return []


def calculate_weekly_capacity(user_id, year, week_number):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT base_capacity, location, start_week FROM users WHERE id = ?', (user_id,))
    user_data = cursor.fetchone()
    if not user_data: return 0.0
    base_cap, user_location, start_week = user_data

    # Safe fallback just in case old users have NULL
    if start_week is None: start_week = 1

    # THE MAGIC LOCK: If the week we are checking is before they joined, their capacity is 0!
    if week_number < start_week:
        return 0.0

    # NEW: Added 'team_day' to the SQL query so it affects everyone!
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
        except ValueError:
            continue

    days_off = 0
    for start_str, end_str in events:
        s = datetime.strptime(start_str, "%Y-%m-%d")
        e = datetime.strptime(end_str, "%Y-%m-%d")
        event_dates = [(s + timedelta(days=i)).strftime('%Y-%m-%d') for i in range((e - s).days + 1)]
        days_off += sum(1 for w in week_dates if w in event_dates)

    cursor.execute('SELECT SUM(allocated_credits) FROM assignments WHERE user_id = ? AND year = ? AND week_number = ?',
                   (user_id, year, week_number))
    assigned_credits = cursor.fetchone()[0] or 0.0
    conn.close()

    capacity = max(0.0, base_cap - (days_off * 0.2) - assigned_credits)
    return round(capacity, 1)

@router.post("/events/")
def create_event(e: EventCreate, current_user: dict = Depends(get_current_user)):
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
    return {"status": "ok"}


@router.put("/events/{event_id}")
def update_event(event_id: str, e: EventUpdate, current_user: dict = Depends(get_current_user)):
    if e.event_type in ['national_holiday', 'team_day']:
        e.user_id = None
    if e.event_type == 'team_day':
        e.location = 'Global'
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute('UPDATE events SET user_id=?, event_type=?, location=?, start_date=?, end_date=? WHERE id=?', (e.user_id, e.event_type, e.location, e.start_date, e.end_date, event_id))
    conn.commit(); conn.close()
    return {"message": "Holiday updated"}


# Delete a holiday
@router.delete("/events/{event_id}")
def delete_event(event_id: str, current_user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute('DELETE FROM events WHERE id=?', (event_id,))
    conn.commit(); conn.close()
    return {"message": "Holiday deleted"}


@router.get("/board/{year}/Q{quarter}")
def get_quarterly_board(year: int, quarter: int, current_user: dict = Depends(get_current_user)):
    weeks = list(get_quarter_weeks(quarter))
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute('SELECT id, name, max_concurrent_per_week FROM services')
    services = [{"id": r[0], "name": r[1], "max_per_week": r[2]} for r in cursor.fetchall()]

    # Updated to fetch location and base_capacity for the reports!
    cursor.execute('SELECT id, name, role, location, base_capacity, username, start_week FROM users')
    pentesters = [{"id": r[0], "name": r[1], "role": r[2], "location": r[3], "capacity": r[4], "username": r[5],
                   "start_week": r[6]} for r in cursor.fetchall()]

    cursor.execute(
        'SELECT a.test_id, a.user_id, a.week_number, a.allocated_credits, u.name FROM assignments a JOIN users u ON a.user_id = u.id')
    assignments = [{"test_id": r[0], "user_id": r[1], "week_number": r[2], "allocated_credits": r[3], "user_name": r[4]}
                   for r in cursor.fetchall()]

    # NEW: Added 'status' to the SELECT query
    cursor.execute(
        'SELECT id, name, service_id, credits_per_week, duration_weeks, start_week, start_year, status FROM tests')
    all_tests = cursor.fetchall()

    backlog = []
    scheduled = []
    for t in all_tests:
        test_obj = {"id": t[0], "name": t[1], "service_id": t[2], "credits": t[3], "duration": t[4], "startWeek": t[5],
                    "startYear": t[6], "status": t[7]}
        if t[5] is None:
            backlog.append(test_obj)
        else:
            scheduled.append(test_obj)

    # NEW: Fetch all Events/Holidays for the reports
    cursor.execute('''
                   SELECT e.id, e.user_id, e.event_type, e.location, e.start_date, e.end_date, u.name
                   FROM events e
                            LEFT JOIN users u ON e.user_id = u.id
                   ''')
    events = [
        {"id": r[0], "user_id": r[1], "type": r[2], "location": r[3], "start": r[4], "end": r[5], "user_name": r[6]} for
        r in cursor.fetchall()]

    conn.close()

    cap_matrix = {p["id"]: {w: calculate_weekly_capacity(p["id"], year, w) for w in weeks} for p in pentesters}

    return {
        "year": year, "quarter": quarter, "weeks": weeks, "services": services,
        "pentesters": pentesters, "capacities": cap_matrix,
        "backlog": backlog, "scheduled": scheduled,
        "assignments": assignments,
        "events": events  # <-- Added to the payload!
    }


@router.delete("/system/wipe")
def wipe_system(current_user: dict = Depends(get_current_user)):
    if current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Only Admins can wipe the system.")

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
    return {"message": "Board wiped clean, all assets freed!"}





