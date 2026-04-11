import os
import json
from fastapi import APIRouter, Depends, HTTPException, Header, Request
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

    if iap_email_header:
        # IAP format is usually "accounts.google.com:email@address.com"
        email = iap_email_header.split(":")[-1].lower()

        # SA_EMAIL is your SA_EMAIL environment variable
        if email != SA_EMAIL.lower():
            print(f"🚨 DEBUG IAP MISMATCH: IAP sent '{email}', but backend expected '{SA_EMAIL.lower()}'")
            raise HTTPException(status_code=403, detail=f"Unauthorized IAP Account: {email}")
        return {"email": email}


#  The Search Endpoints (Used by Gemini Tools)

@router.get("/search-asset", dependencies=[Depends(verify_iam_identity)])
def search_asset(name: str, cursor=Depends(get_db_cursor)):
    """Searches assets and raw_asset tables."""
    # 1. Check primary assets table
    cursor.execute("SELECT id, name FROM assets WHERE name ILIKE %s LIMIT 5", (f"%{name}%",))
    results = cursor.fetchall()
    
    # 2. Fallback to raw_asset table if not found
    if not results:
        cursor.execute("SELECT id, name FROM raw_asset WHERE name ILIKE %s LIMIT 5", (f"%{name}%",))
        results = cursor.fetchall()
        
    if not results:
        raise HTTPException(status_code=404, detail="Not Found")
        
    # pg8000 returns tuples, we map them to a list of dicts
    return [{"id": r[0], "name": r[1]} for r in results]

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
    """Searches market_contact by name or email."""
    cursor.execute(
        "SELECT market_code FROM market_contact WHERE name ILIKE %s OR email ILIKE %s LIMIT 1", 
        (f"%{name}%", f"%{name}%")
    )
    result = cursor.fetchone()
    if result:
        return {"market_code": result[0]}
    
    raise HTTPException(status_code=404, detail="Contact Not Found")

@router.get("/check-tests", dependencies=[Depends(verify_iam_identity)])
def check_tests(asset_id: str, cursor=Depends(get_db_cursor)):
    """Checks test_assets for active tests."""
    cursor.execute("SELECT test_id, status FROM test_assets WHERE asset_id = %s", (asset_id,))
    results = cursor.fetchall()
    if results:
         return [{"test_id": r[0], "status": r[1]} for r in results]
         
    return [] # Return empty list if no tests found

# ==========================================
# 2. The Final Save Endpoint
# ==========================================

@router.post("/complete-intake", dependencies=[Depends(verify_iam_identity)])
def complete_intake(result: LuigiIntakeResult, cursor=Depends(get_db_cursor)):
    """Saves the final AI analysis back to the intake_notes table."""
    
    # We convert the Pydantic models to dictionaries, then to a JSON string 
    # so PostgreSQL can save it properly into the JSONB column.
    assets_json_str = json.dumps([asset.dict() for asset in result.assets])
    
    cursor.execute("""
        UPDATE intake_notes 
        SET status = 'REVIEW_READY', 
            ai_summary = %s,
            ai_extracted_assets = %s
        WHERE id = %s
    """, (result.summary, assets_json_str, result.note_id))
    
    print(f"✅ Main Backend saved Luigi analysis for Note {result.note_id}")
    return {"status": "success"}
