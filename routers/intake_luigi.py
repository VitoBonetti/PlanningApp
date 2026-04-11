import os
import json
import datetime
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from pydantic import BaseModel
from typing import List, Optional
from google.oauth2 import id_token
from google.auth.transport import requests
from database import get_db_cursor 
from models import ExtractedAsset, LuigiIntakeResult
from routers.board import get_user_provision_internal

SA_EMAIL = os.environ.get("SA_EMAIL")

router = APIRouter(tags=["Intake Luigi"])


def verify_iam_identity(request: Request):
    iap_email_header = request.headers.get("x-goog-authenticated-user-email")

    # 1. Block requests missing the IAP header entirely
    if not iap_email_header:
        print("🚨 SECURITY ALERT: Request attempted without IAP header.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required identity header."
        )

    # 2. Extract and normalize the email
    email = iap_email_header.split(":")[-1].lower()

    # 3. Strict match against the expected Service Account
    if email != SA_EMAIL.lower():
        print(f"🚨 AUTH FAILURE: '{email}' tried to access internal AI tools.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Unauthorized identity."
        )

    return {"email": email}


#  endpoint used by luigi
@router.get("/search-asset", dependencies=[Depends(verify_iam_identity)])
def search_asset(name: str, cursor=Depends(get_db_cursor)):
    """Searches both verified assets and raw_assets simultaneously for the AI."""

    # 1. Check primary assets table
    cursor.execute("SELECT id, name FROM assets WHERE name ILIKE %s LIMIT 3", (f"%{name}%",))
    verified_results = [{"id": r[0], "name": r[1], "type": "VERIFIED"} for r in cursor.fetchall()]

    # 2. Check raw_asset table
    cursor.execute("SELECT inventory_id, name FROM raw_assets WHERE name ILIKE %s OR number ILIKE %s LIMIT 3",
                   (f"%{name}%", f"%{name}%"))
    raw_results = [{"id": r[0], "name": r[1], "type": "RAW"} for r in cursor.fetchall()]

    # Combine results
    combined = verified_results + raw_results

    if not combined:
        raise HTTPException(status_code=404, detail="Not Found.")

    return combined


@router.get("/search-market", dependencies=[Depends(verify_iam_identity)])
def search_market(query: str, cursor=Depends(get_db_cursor)):
    """Searches markets by code or name."""
    cursor.execute(
        "SELECT code, name FROM markets WHERE code ILIKE %s OR name ILIKE %s LIMIT 1", 
        (query, f"%{query}%")
    )
    result = cursor.fetchone()
    if result:
        return {"code": result[0], "name": result[1]}
    
    raise HTTPException(status_code=404, detail="Market Not Found")


@router.get("/search-contact", dependencies=[Depends(verify_iam_identity)])
def search_contact(name: str, cursor=Depends(get_db_cursor)):
    """
        Searches market_contacts by name or email, joins with assignments
        to get the actual market code from the markets table.
        """
    query = """
            SELECT m.code 
            FROM markets m
            JOIN market_contact_assignments mca ON m.id = mca.market_id
            JOIN market_contacts mc ON mca.contact_id = mc.id
            WHERE mc.name ILIKE %s OR mc.email ILIKE %s
            LIMIT 1
        """

    # We pass the formatted string to both ILIKE placeholders
    cursor.execute(query, (f"%{name}%", f"%{name}%"))
    result = cursor.fetchone()

    if result:
        return {"market_code": result[0]}

    raise HTTPException(status_code=404, detail="Contact Not Found")


@router.get("/check-tests", dependencies=[Depends(verify_iam_identity)])
def check_tests(asset_id: str, cursor=Depends(get_db_cursor)):
    """
        Checks if a specific asset has any assigned tests.
        Returns comprehensive test and service details, excluding whitebox_category.
        """
    query = """
    SELECT 
        t.id, 
        t.name, 
        s.name as service_name, 
        t.type, 
        t.credits_per_week, 
        t.duration_weeks, 
        t.start_week, 
        t.start_year, 
        t.status 
    FROM tests t
    JOIN test_assets ta ON t.id = ta.test_id
    LEFT JOIN services s ON t.service_id = s.id
    WHERE ta.asset_id = %s
    """

    cursor.execute(query, (asset_id,))
    results = cursor.fetchall()

    if results:
        return [
            {
                "test_id": r[0],
                "name": r[1],
                "service_name": r[2],  # Meaningful string for the AI instead of a UUID
                "type": r[3],
                "credits_per_week": r[4],
                "duration_weeks": r[5],
                "start_week": r[6],
                "start_year": r[7],
                "status": r[8]
            } for r in results
        ]

    return []  # Return empty list if no tests found

# save Endpoint

@router.post("/complete-intake", dependencies=[Depends(verify_iam_identity)])
def complete_intake(result: LuigiIntakeResult, cursor=Depends(get_db_cursor)):
    """Saves the final AI analysis back to the intake_notes table."""

    assets_json_str = json.dumps([asset.dict() for asset in result.assets])

    cursor.execute("""
        UPDATE intake_notes 
        SET status = 'REVIEW_READY', 
            ai_summary = %s,
            ai_extracted_assets = %s
        WHERE id = %s AND status != 'DISCARDED'
    """, (result.summary, assets_json_str, result.note_id))

    # check if the update actually happened
    if cursor.rowcount == 0:
        print(f"⚠️ Note {result.note_id} was already discarded or not found. Skipping Luigi update.")
    else:
        print(f"✅ Main Backend saved Luigi analysis for Note {result.note_id}")

    cursor.connection.commit()

    return {"status": "success"}


@router.get("/all-markets", dependencies=[Depends(verify_iam_identity)])
def get_all_markets(cursor=Depends(get_db_cursor)):
    """Returns all active markets so the AI doesn't have to guess country codes."""
    cursor.execute("SELECT code, name FROM markets WHERE is_active = TRUE")
    return [{"code": r[0], "name": r[1]} for r in cursor.fetchall()]


@router.get("/check-capacity", dependencies=[Depends(verify_iam_identity)])
def check_capacity(service_name: str, quarter: int, year: int, cursor=Depends(get_db_cursor)):
    """Calculates available weeks in a quarter based on service type."""

    # remove spaces from search term and database column
    search_term = f"%{service_name.lower().replace(' ', '').replace('-', '')}%"

    cursor.execute("""
        SELECT id, name, max_concurrent_per_week 
        FROM services 
        WHERE REPLACE(REPLACE(LOWER(name), ' ', ''), '-', '') LIKE %s 
        LIMIT 1
    """, (search_term,))

    service = cursor.fetchone()

    if not service:
        # This will now return cleanly to the AI so it can report the specific failure
        return {"error": f"Service matching '{service_name}' not found in DB."}

    service_id, s_name, max_concurrent = service
    is_blackbox = "blackbox" in s_name.lower().replace(" ", "")

    # 2. Calculate week boundaries for the quarter
    q_start = (quarter - 1) * 13 + 1
    q_end = quarter * 13 if quarter < 4 else 52

    available_weeks = []

    today = datetime.date.today()
    current_year, current_week, _ = today.isocalendar()

    # 3. Calculate Availability
    for w in range(q_start, q_end + 1):

        if year < current_year or (year == current_year and w <= current_week):
            continue

        if is_blackbox:
            # Blackbox Logic: Concurrency limit from services table
            cursor.execute("""
                SELECT COUNT(*) FROM tests 
                WHERE service_id = %s 
                AND status NOT IN ('Completed', 'Discarded', 'Not Planned')
                AND start_year = %s
                AND %s >= start_week AND %s < (start_week + duration_weeks)
            """, (service_id, year, w, w))
            count = cursor.fetchone()[0]

            if count < (max_concurrent or 999):
                available_weeks.append(w)
        else:
            # Whitebox/Adversary Logic: 1.0 Credit availability rule
            cursor.execute("SELECT id FROM users")
            all_users = cursor.fetchall()

            total_team_remaining = 0.0

            for (u_id,) in all_users:
                # 1. Get exact provision for this specific user (handles holidays & start dates)
                provision = get_user_provision_internal(cursor, u_id, year, w)

                # 2. Deduct tests they are already assigned to
                cursor.execute('''
                    SELECT SUM(COALESCE(a.allocated_credits, u.base_capacity)) 
                    FROM assignments a
                    JOIN tests t ON a.test_id = t.id
                    JOIN users u ON a.user_id = u.id
                    WHERE a.user_id = %s AND a.year = %s AND a.week_number = %s AND t.status != 'Unable'
                ''', (u_id, year, w))

                used = cursor.fetchone()[0] or 0.0

                # 3. Add their remaining capacity to the team's total pool
                total_team_remaining += max(0.0, round(provision - used, 1))

            # If the TEAM has strictly more than 1.0 credit left, propose it
            if total_team_remaining > 1.0:
                available_weeks.append(w)

    return {"service_identified": s_name, "available_weeks": available_weeks}
