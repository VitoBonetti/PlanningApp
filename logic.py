import sqlite3
from datetime import date, timedelta

DB_FILE = 'pentest_planner.db'


# --- 1. INSERTING DATA ---

def add_event(user_id, event_type, start_date, end_date):
    """
    Registers a holiday, side project, or national holiday.
    Dates must be in 'YYYY-MM-DD' format.
    If it's a national holiday, user_id can be None.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute('''
                   INSERT INTO events (user_id, event_type, start_date, end_date)
                   VALUES (?, ?, ?, ?)
                   ''', (user_id, event_type, start_date, end_date))

    conn.commit()
    conn.close()
    print(f"Added {event_type} from {start_date} to {end_date}.")


# --- 2. CALCULATING CAPACITY ---

def get_working_dates_for_week(year, week_number):
    """Returns a list of 'YYYY-MM-DD' strings for Monday-Friday of a given week."""
    working_dates = []
    # 1 = Monday, 5 = Friday
    for day in range(1, 6):
        # fromisocalendar is available in Python 3.8+
        current_date = date.fromisocalendar(year, week_number, day)
        working_dates.append(current_date.strftime('%Y-%m-%d'))
    return working_dates


def get_dates_in_range(start_str, end_str):
    """Generates all dates between a start and end date (inclusive)."""
    start = date.fromisoformat(start_str)
    end = date.fromisoformat(end_str)
    delta = end - start

    dates = []
    for i in range(delta.days + 1):
        day = start + timedelta(days=i)
        dates.append(day.strftime('%Y-%m-%d'))
    return dates


def calculate_weekly_capacity(user_id, year, week_number):
    """
    Calculates the actual testing credits a user has for a specific week.
    Base is 1.0. Deducts 0.2 for every day off / side project.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Get user's base capacity (default 1.0)
    cursor.execute('SELECT base_capacity, name FROM users WHERE id = ?', (user_id,))
    user_data = cursor.fetchone()
    if not user_data:
        conn.close()
        return 0.0

    base_capacity = user_data[0]
    user_name = user_data[1]

    # Get all events for this user OR national holidays
    cursor.execute('''
                   SELECT start_date, end_date
                   FROM events
                   WHERE user_id = ?
                      OR event_type = 'national_holiday'
                   ''', (user_id,))
    events = cursor.fetchall()
    conn.close()

    # Get the 5 working days for the requested week
    week_dates = get_working_dates_for_week(year, week_number)

    # Calculate how many working days overlap with an event
    days_off_this_week = 0

    for event in events:
        event_start, event_end = event
        event_dates = get_dates_in_range(event_start, event_end)

        # Check intersection between the week's working days and the event days
        for w_date in week_dates:
            if w_date in event_dates:
                days_off_this_week += 1

    # Deduct 0.2 credits for each overlapping day
    deduction = days_off_this_week * 0.2
    actual_capacity = base_capacity - deduction

    # Ensure capacity doesn't drop below 0 (e.g., overlapping national holiday + personal holiday)
    actual_capacity = max(0.0, actual_capacity)

    # Return rounded to 1 decimal place to avoid weird floating point math issues (like 0.799999)
    return round(actual_capacity, 1), user_name


# --- 3. TEST THE LOGIC ---
if __name__ == '__main__':
    # Let's say we are looking at Year 2026, Week 14 (Starting March 30, 2026)
    target_year = 2026
    target_week = 14

    # user_id 1 is "Alice (Senior)" from our init script
    user = 1

    print("--- Before Adding Holidays ---")
    cap, name = calculate_weekly_capacity(user, target_year, target_week)
    print(f"{name}'s capacity for 2026-W14 is: {cap} credits\n")

    print("--- Adding Holidays ---")
    # Alice takes Thursday and Friday off that week
    add_event(user_id=user, event_type='holiday', start_date='2026-04-02', end_date='2026-04-03')

    # A National Holiday happens on the Monday of that week (user_id=None)
    add_event(user_id=None, event_type='national_holiday', start_date='2026-03-30', end_date='2026-03-30')

    print("\n--- After Adding Holidays ---")
    cap, name = calculate_weekly_capacity(user, target_year, target_week)
    print(f"{name}'s capacity for 2026-W14 is now: {cap} credits")
    print("(Expected: 1.0 - 0.4 for personal holiday - 0.2 for national holiday = 0.4)")