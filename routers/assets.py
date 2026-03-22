from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, BackgroundTasks
import pandas as pd
import io
import sqlite3
import uuid
from typing import List
from database import DB_FILE
from routers.auth import get_current_user

router = APIRouter(tags=["Assets"])

# Excel Parser
def process_excel_background(contents: bytes):
    try:
        df = pd.read_excel(io.BytesIO(contents))
        df.columns = df.columns.str.strip()
        if 'Pentest Queue' in df.columns:
            df = df[df['Pentest Queue'].astype(str).str.strip().str.upper() == 'YES']
        if 'Status_manual_tracking' in df.columns:
            df = df[df['Status_manual_tracking'].astype(str).str.strip() != '2027']
        df = df.fillna('')

        conn = sqlite3.connect(DB_FILE, timeout=10)  # Added timeout for safety
        cursor = conn.cursor()

        for index, row in df.iterrows():
            def get_val(possible_names):
                for col in df.columns:
                    if str(col).strip().lower() in [n.lower() for n in possible_names]:
                        val = str(row[col]).strip()
                        if val and val.lower() != 'nan': return val
                return ''

            inv_id = get_val(['Inventory Id'])
            ext_id = get_val(['ID'])
            number = get_val(['Number'])
            if not inv_id and not ext_id and not number: continue

            name = get_val(['Name']) or 'Unknown Asset'
            market = get_val(['Market']) or 'Global'
            gost_service = get_val(['Gost_service']) or 'Unknown'

            cursor.execute("SELECT id FROM assets WHERE inventory_id=? AND ext_id=? AND number=?",
                           (inv_id, ext_id, number))
            if cursor.fetchone():
                cursor.execute(
                    "UPDATE assets SET name=?, market=?, gost_service=? WHERE inventory_id=? AND ext_id=? AND number=?",
                    (name, market, gost_service, inv_id, ext_id, number))
            else:
                cursor.execute(
                    "INSERT INTO assets (id, inventory_id, ext_id, number, name, market, gost_service, is_assigned) VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
                    (str(uuid.uuid4()), inv_id, ext_id, number, name, market, gost_service))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Background Import Failed: {e}")


#  Receives file and triggers worker
@router.post("/assets/import")
async def import_assets(background_tasks: BackgroundTasks, file: UploadFile = File(...),
                        current_user: dict = Depends(get_current_user)):
    if current_user['role'] not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Only Admins/Managers can import assets.")

    contents = await file.read()  # Read file into memory NOW before the connection closes
    background_tasks.add_task(process_excel_background, contents)  # Hand bytes to worker
    return {"message": "Excel file received! Importing in the background."}


@router.get("/assets/")
def get_available_assets(current_user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Get the stats!
    cursor.execute("SELECT COUNT(*) FROM assets")
    total = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM assets WHERE is_assigned = 1")
    assigned = cursor.fetchone()[0] or 0

    # NEW: Get ALL assets and join with tests to see exactly when they are planned!
    cursor.execute('''
                   SELECT a.id,
                          a.inventory_id,
                          a.ext_id,
                          a.number,
                          a.name,
                          a.market,
                          a.gost_service,
                          a.is_assigned,
                          t.status,
                          t.start_week,
                          t.start_year
                   FROM assets a
                            LEFT JOIN test_assets ta ON a.id = ta.asset_id
                            LEFT JOIN tests t ON ta.test_id = t.id
                   ''')

    assets = []
    for r in cursor.fetchall():
        assets.append({
            "id": r[0], "inventory_id": r[1], "ext_id": r[2], "number": r[3],
            "name": r[4], "market": r[5], "gost_service": r[6], "is_assigned": bool(r[7]),
            "test_status": r[8], "start_week": r[9], "start_year": r[10]
        })

    conn.close()
    return {"assets": assets, "total": total, "assigned": assigned}