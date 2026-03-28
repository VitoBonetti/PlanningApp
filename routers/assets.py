from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, BackgroundTasks, Request
import pandas as pd
import io
import uuid
from database import get_db_connection
from routers.auth import get_current_user, require_admin, limiter
from audit_logger import log_audit_event

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

        conn = get_db_connection()
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

            # --- NEW DATA COLUMNS ---
            business_critical = get_val(['Business Critical']) or ''
            kpi = get_val(['KPI']) or ''
            whitebox_category = get_val(['WhiteBox Category']) or ''

            cursor.execute("SELECT id FROM assets WHERE inventory_id=%s AND ext_id=%s AND number=%s",
                           (inv_id, ext_id, number))
            if cursor.fetchone():
                # UPDATE existing record with fresh Excel data
                cursor.execute(
                    "UPDATE assets SET name=%s, market=%s, gost_service=%s, business_critical=%s, kpi=%s, whitebox_category=%s WHERE inventory_id=%s AND ext_id=%s AND number=%s",
                    (name, market, gost_service, business_critical, kpi, whitebox_category, inv_id, ext_id, number))
            else:
                # INSERT new record
                cursor.execute(
                    "INSERT INTO assets (id, inventory_id, ext_id, number, name, market, gost_service, is_assigned, business_critical, kpi, whitebox_category) VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, %s, %s, %s)",
                    (str(uuid.uuid4()), inv_id, ext_id, number, name, market, gost_service, business_critical, kpi,
                     whitebox_category))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Background Import Failed: {e}")


@router.post("/assets/import")
@limiter.limit("3/minute")
async def import_assets(request: Request, background_tasks: BackgroundTasks, file: UploadFile = File(...),
                        current_user: dict = Depends(require_admin)):

    contents = await file.read()

    # block files larger than 5MB
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum allowed size is 5MB.")

    # magic Number Validation (File Signature)
    # .xls (OLE2) signature: D0 CF 11 E0 A1 B1 1A E1
    # .xlsx (ZIP) signature: 50 4B 03 04
    XLS_MAGIC = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
    XLSX_MAGIC = b'\x50\x4b\x03\x04'

    is_valid_signature = contents.startswith(XLS_MAGIC) or contents.startswith(XLSX_MAGIC)

    if not is_valid_signature:
        raise HTTPException(
            status_code=400,
            detail="Security Alert: Invalid file signature. This is not a genuine Excel file."
        )

    # fallback Extension Check
    if not file.filename.endswith(('.xls', '.xlsx')):
        raise HTTPException(status_code=400, detail="Invalid extension. Please use .xls or .xlsx")

    background_tasks.add_task(process_excel_background, contents)
    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="IMPORT_ASSETS",
        resource_type="ASSET_BATCH",
        details=f"Initiated background import of asset file: {file.filename}"
    )
    return {"message": "Excel file received! Importing in the background."}


@router.get("/assets/")
def get_available_assets(current_user: dict = Depends(get_current_user)):
    if current_user['role'] == 'pentester':
        raise HTTPException(status_code=403, detail="Pentesters cannot view the asset inventory.")
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM assets")
    total = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM assets WHERE is_assigned")
    assigned = cursor.fetchone()[0] or 0

    # Fetch the new columns from the DB
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
                          t.start_year,
                          a.business_critical,
                          a.kpi,
                          a.whitebox_category
                   FROM assets a
                            LEFT JOIN test_assets ta ON a.id = ta.asset_id
                            LEFT JOIN tests t ON ta.test_id = t.id
                   ''')

    assets = []
    for r in cursor.fetchall():
        assets.append({
            "id": r[0], "inventory_id": r[1], "ext_id": r[2], "number": r[3],
            "name": r[4], "market": r[5], "gost_service": r[6], "is_assigned": bool(r[7]),
            "test_status": r[8], "start_week": r[9], "start_year": r[10],
            "business_critical": r[11] or '',
            "kpi": r[12] or '',
            "whitebox_category": r[13] or ''
        })

    conn.close()
    return {"assets": assets, "total": total, "assigned": assigned}
