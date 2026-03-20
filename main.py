from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import sqlite3
import jwt
from datetime import datetime, timedelta, timezone
import bcrypt
import uuid

DB_FILE = 'planner_v2.db'
SECRET_KEY = "your-super-secret-production-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120

app = FastAPI(title="Pentest Planner API - PRO")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"],
                   allow_headers=["*"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                          detail="Could not validate credentials",
                                          headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None: raise credentials_exception
    except jwt.InvalidTokenError:
        raise credentials_exception

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, name, role, location FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()

    if user is None: raise credentials_exception
    return {"id": user[0], "username": user[1], "name": user[2], "role": user[3], "location": user[4]}


@app.post("/token")
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, hashed_password, role, name FROM users WHERE username = ?",
                   (form_data.username,))
    user = cursor.fetchone()
    conn.close()

    if not user or not verify_password(form_data.password, user[2]):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    access_token = create_access_token(data={"sub": user[1]})
    return {"access_token": access_token, "token_type": "bearer", "role": user[3], "name": user[4]}


class UserCreateSecure(BaseModel):
    username: str
    password: str
    name: str
    role: str
    location: str
    base_capacity: float = 1.0

class EventCreate(BaseModel):
    user_id: Optional[str] = None
    event_type: str
    location: Optional[str] = None
    start_date: str
    end_date: str

class EventUpdate(BaseModel):
    user_id: Optional[str] = None
    event_type: str
    location: Optional[str] = None
    start_date: str
    end_date: str

class TestCreate(BaseModel):
    name: str
    service_id: str
    type: str
    credits_per_week: float
    duration_weeks: int

class TestUpdate(BaseModel):
    name: str
    service_id: str
    credits_per_week: float
    duration_weeks: int
    status: Optional[str] = None

class TestSchedule(BaseModel):
    start_week: Optional[int]
    start_year: Optional[int]

class AssignmentCreate(BaseModel):
    test_id: str
    user_id: str
    week_number: int
    year: int
    allocated_credits: float


def get_quarter_weeks(q: int):
    if q == 1: return range(1, 14)
    if q == 2: return range(14, 27)
    if q == 3: return range(27, 40)
    if q == 4: return range(40, 53)
    return []


def calculate_weekly_capacity(user_id, year, week_number):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT base_capacity, location FROM users WHERE id = ?', (user_id,))
    user_data = cursor.fetchone()
    if not user_data: return 0.0
    base_cap, user_location = user_data

    cursor.execute("SELECT start_date, end_date FROM events WHERE user_id = ? OR (event_type = 'national_holiday' AND (location = ? OR location = 'Global'))", (user_id, user_location))
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


@app.post("/users/")
def create_user(u: UserCreateSecure, current_user: dict = Depends(get_current_user)):
    if current_user['role'] != 'admin': raise HTTPException(status_code=403, detail="Only Admins can create new users.")
    salt = bcrypt.gensalt()
    hashed_pw = bcrypt.hashpw(u.password.encode('utf-8'), salt).decode('utf-8')
    new_id = str(uuid.uuid4())
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO users (id, username, hashed_password, name, role, location, base_capacity) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (new_id, u.username, hashed_pw, u.name, u.role, u.location, u.base_capacity))
        conn.commit()
        conn.close()
        return {"message": f"User {u.name} created."}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already exists.")


# NEW: Delete User Endpoint
@app.delete("/users/{user_id}")
def delete_user(user_id: str, current_user: dict = Depends(get_current_user)):
    if current_user['role'] != 'admin': raise HTTPException(status_code=403, detail="Admins only.")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM assignments WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM events WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return {"message": "User deleted."}


@app.post("/events/")
def create_event(e: EventCreate, current_user: dict = Depends(get_current_user)):
    if e.event_type == 'national_holiday': e.user_id = None
    new_id = str(uuid.uuid4())
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO events (id, user_id, event_type, location, start_date, end_date) VALUES (?, ?, ?, ?, ?, ?)',
              (new_id, e.user_id, e.event_type, e.location, e.start_date, e.end_date))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.put("/events/{event_id}")
def update_event(event_id: str, e: EventUpdate, current_user: dict = Depends(get_current_user)):
    if e.event_type == 'national_holiday': e.user_id = None
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute('UPDATE events SET user_id=?, event_type=?, location=?, start_date=?, end_date=? WHERE id=?', (e.user_id, e.event_type, e.location, e.start_date, e.end_date, event_id))
    conn.commit(); conn.close()
    return {"message": "Holiday updated"}


# NEW: Delete a holiday
@app.delete("/events/{event_id}")
def delete_event(event_id: str, current_user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute('DELETE FROM events WHERE id=?', (event_id,))
    conn.commit(); conn.close()
    return {"message": "Holiday deleted"}

@app.post("/tests/")
def create_test(t: TestCreate, current_user: dict = Depends(get_current_user)):
    new_id = str(uuid.uuid4())
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO tests (id, name, service_id, type, credits_per_week, duration_weeks) VALUES (?, ?, ?, ?, ?, ?)',
              (new_id, t.name, t.service_id, t.type, t.credits_per_week, t.duration_weeks))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.put("/tests/{test_id}/schedule")
def schedule_test(test_id: str, schedule: TestSchedule, current_user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE tests SET start_week = ?, start_year = ?, status = "Planned" WHERE id = ?',
                   (schedule.start_week, schedule.start_year, test_id))
    conn.commit()
    conn.close()
    return {"message": "Scheduled"}


@app.put("/tests/{test_id}/unschedule")
def unschedule_test(test_id: str, current_user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM assignments WHERE test_id = ?', (test_id,))
    cursor.execute('UPDATE tests SET start_week = NULL, start_year = NULL, status = "Not Planned" WHERE id = ?',
                   (test_id,))
    conn.commit()
    conn.close()
    return {"message": "Unscheduled"}


@app.delete("/tests/{test_id}")
def delete_test(test_id: str, current_user: dict = Depends(get_current_user)):
    if current_user['role'] not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Only Admins/Managers can delete tests.")
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    # Must delete assignments first due to relational links!
    cursor.execute('DELETE FROM assignments WHERE test_id = ?', (test_id,))
    cursor.execute('DELETE FROM tests WHERE id = ?', (test_id,))
    conn.commit(); conn.close()
    return {"message": "Test permanently deleted."}


@app.put("/tests/{test_id}")
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


@app.put("/tests/{test_id}/complete")
def complete_test(test_id: str, current_user: dict = Depends(get_current_user)):
    if current_user['role'] not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Only Admins/Managers can complete tests.")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE tests SET status = 'Completed' WHERE id = ?", (test_id,))
    conn.commit()
    conn.close()
    return {"message": "Test marked as Completed."}

@app.post("/assignments/")
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


@app.delete("/assignments/{test_id}/{user_id}")
def remove_assignment(test_id: str, user_id: str, current_user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM assignments WHERE test_id = ? AND user_id = ?', (test_id, user_id))
    conn.commit()
    conn.close()
    return {"message": "Unassigned"}


@app.get("/board/{year}/Q{quarter}")
def get_quarterly_board(year: int, quarter: int, current_user: dict = Depends(get_current_user)):
    weeks = list(get_quarter_weeks(quarter))
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute('SELECT id, name, max_concurrent_per_week FROM services')
    services = [{"id": r[0], "name": r[1], "max_per_week": r[2]} for r in cursor.fetchall()]

    # Updated to fetch location and base_capacity for the reports!
    cursor.execute('SELECT id, name, role, location, base_capacity FROM users')
    pentesters = [{"id": r[0], "name": r[1], "role": r[2], "location": r[3], "capacity": r[4]} for r in
                  cursor.fetchall()]

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


@app.delete("/system/wipe")
def wipe_system(current_user: dict = Depends(get_current_user)):
    if current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Only Admins can wipe the system.")
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    cursor.execute('DELETE FROM assignments')
    cursor.execute('DELETE FROM tests')
    cursor.execute('DELETE FROM events') # Clears all holidays
    conn.commit(); conn.close()
    return {"message": "Board wiped clean!"}
