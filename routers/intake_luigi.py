import os
import json
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from pydantic import BaseModel
from typing import List, Optional
from google.oauth2 import id_token
from google.auth.transport import requests
from database import get_db_cursor 
from models import ExtractedAsset, LuigiIntakeResult

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
    cursor.execute("SELECT inventory_id, name FROM raw_assets WHERE name ILIKE %s LIMIT 3", (f"%{name}%",))
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
    Checks if a specific asset has any assigned tests by joining
    the test_assets mapping table with the main tests table.
    """
    query = """
        SELECT t.id, t.status 
        FROM tests t
        JOIN test_assets ta ON t.id = ta.test_id
        WHERE ta.asset_id = %s
    """

    cursor.execute(query, (asset_id,))
    results = cursor.fetchall()

    if results:
        return [{"test_id": r[0], "status": r[1]} for r in results]

    return []  # Return empty list if no tests found

# ==========================================
# 2. The Final Save Endpoint
# ==========================================

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
