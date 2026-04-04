from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, BackgroundTasks, Request, Query
import pandas as pd
import io
import uuid
from database import get_db_connection, get_db_cursor, db_cursor_context
from routers.auth import get_current_user, require_admin, limiter
from audit_logger import log_audit_event
from websockets_manager import manager
import google.auth
from googleapiclient.discovery import build
from datetime import datetime
import os
from models import AssetTrackingUpdate
from services.importer import run_import_job
from typing import Optional

router = APIRouter(tags=["Assets"])


# Helpers
def parse_bool(val):
    if not val: return False
    return str(val).strip().lower() in ['yes', 'true', '1', 'y']


def parse_int(val):
    try:
        return int(float(val)) if val else None
    except ValueError:
        return None


def parse_date(val):
    if not val or str(val).strip().lower() == 'nan': 
        return None
    val = str(val).strip()
    try:
        # Matches: "2026-01-19"
        return datetime.strptime(val, "%Y-%m-%d").date()
    except ValueError:
        # Fallback just in case a timestamp accidentally snuck into a date column
        try:
            return datetime.strptime(val, "%Y-%m-%d %H:%M:%S").date()
        except ValueError:
            return None


def parse_timestamp(val):
    if not val or str(val).strip().lower() == 'nan': 
        return None
    val = str(val).strip()
    try:
        # Matches: "2025-12-11 21:53:40"
        return datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        # Fallback just in case the time is missing
        try:
            return datetime.strptime(val, "%Y-%m-%d")
        except ValueError:
            return None


# Excel Parser
import pandas as pd
import io
import uuid


def process_excel_background(contents: bytes):
    with db_cursor_context() as cursor:
        if not cursor:
            print("Background Import Failed: Could not get DB cursor.")
            return
        try:
            df = pd.read_excel(io.BytesIO(contents))
            df.columns = df.columns.str.strip()
            
            if 'Pentest Queue' in df.columns:
                df = df[df['Pentest Queue'].astype(str).str.strip().str.upper() == 'YES']
            if 'Status_manual_tracking' in df.columns:
                df = df[df['Status_manual_tracking'].astype(str).str.strip() != '2027']
            
            df = df.fillna('')

            for index, row in df.iterrows():
                # Extract clean values, stripping Excel formatting artifacts
                def get_val(possible_names):
                    for col in df.columns:
                        if str(col).strip().lower() in [n.lower() for n in possible_names]:
                            val = str(row[col]).strip().lstrip("'")
                            if val and val.lower() != 'nan': return val
                    return ''

                # Specific fuzzy matcher for that long ServiceNow Date header
                def get_estimated_date():
                    for col in df.columns:
                        if 'estimated date' in str(col).lower():
                            val = str(row[col]).strip().lstrip("'")
                            if val and val.lower() != 'nan': return val
                    return ''

                # 1. Primary Keys
                inv_id = get_val(['Inventory Id'])
                ext_id = get_val(['ID'])
                number = get_val(['Number'])
                
                if not inv_id and not ext_id and not number: continue

                safe_inv_id = inv_id or f"EXCEL_{uuid.uuid4().hex[:8]}"
                safe_ext_id = ext_id or "0"
                safe_number = number or f"TCKT_{uuid.uuid4().hex[:6]}"

                # 2. Extract General Info
                name = get_val(['Name']) or 'Unknown Asset'
                managing_org = get_val(['Managing Organization'])
                hosting_loc = get_val(['Hosting Location'])
                type_val = get_val(['Type'])
                status_val = get_val(['Status'])
                stage_val = get_val(['Stage'])
                
                business_critical = get_val(['Business Critical'])
                confidentiality = get_val(['Confidentiality Rating'])
                integrity = get_val(['Integrity Rating'])
                availability = get_val(['Availability Rating'])
                
                internet_facing = get_val(['Internet Facing'])
                iaas_paas_saas = get_val(['IaaS, PaaS, SaaS', 'IaaS / PaaS / SaaS'])
                master_record = get_val(['Master Record'])
                
                # 3. ServiceNow Ticketing Info
                stage_ritm = get_val(['Stage_RITM', 'Stage RITM'])
                short_desc = get_val(['Short description'])
                requested_for = get_val(['Requested for'])
                opened_by = get_val(['Opened by'])
                company = get_val(['Company'])
                created_val = get_val(['Created'])
                app_name = get_val(['Name of the application', 'Name of Application'])
                app_url = get_val(['URL of the application', 'URL'])
                est_date = get_estimated_date()
                opened_val = get_val(['Opened'])
                state_val = get_val(['State'])
                assignment_group = get_val(['Assignment group'])
                assigned_to = get_val(['Assigned to'])
                closed_val = get_val(['Closed'])
                closed_by = get_val(['Closed by'])
                close_notes = get_val(['Close notes'])
                service_type = get_val(['Service Type'])
                
                # 4. Custom Gost/Tracking Info
                market = get_val(['Market']) or 'Global'
                gost_service = get_val(['Gost_service', 'Gost Service']) or 'Adversary / Manual'
                whitebox_category = get_val(['WhiteBox Category', 'Whitebox Category'])
                quarter_planned = get_val(['Quarter Planned', 'Quarter_Planned'])
                year_planned = get_val(['Year Planned', 'Year_Planned'])
                month_planned = get_val(['Month Planned', 'Month_Planned'])
                week_planned = get_val(['Week Planned', 'Week_Planned'])
                tested_2024 = get_val(['Tested 2024 RITM', 'Tested_2024_RITM'])
                tested_2025 = get_val(['Tested 2025 RITM', 'Tested_2025_RITM'])
                prev_2027 = get_val(['Prevision 2027', 'Prevision_2027'])
                status_manual = get_val(['Status Manual Tracking', 'Status_manual_tracking'])

                # 5. Booleans
                kpi_text = get_val(['KPI'])
                is_kpi = True if str(kpi_text).strip().lower() in ['yes', 'true', '1'] else False
                
                planned_ritm_text = get_val(['Planned with RITM', 'Planned_with_RITM'])
                planned_with_ritm = True if str(planned_ritm_text).strip().lower() in ['yes', 'true', '1'] else False
                
                confirmed_market_text = get_val(['Confirmed by Market', 'Confirmed_by_Market'])
                confirmed_by_market = True if str(confirmed_market_text).strip().lower() in ['yes', 'true', '1'] else False

                # --- UPSERT 1: THE MASTER RAW ASSETS TABLE (All 49 Fields) ---
                cursor.execute('''
                    INSERT INTO raw_assets (
                        inventory_id, legacy_id, name, managing_organization, hosting_location, type, status, stage, 
                        business_critical, confidentiality_rating, integrity_rating, availability_rating, internet_facing, 
                        iaas_paas_saas, master_record, number, stage_ritm, short_description, requested_for, opened_by, 
                        company, created, name_of_application, url_of_application, estimated_date_pentest, opened, state, 
                        assignment_group, assigned_to, closed, closed_by, close_notes, service_type, market, kpi, 
                        date_first_seen, pentest_queue, gost_service, whitebox_category, quarter_planned, year_planned, 
                        planned_with_ritm, month_planned, week_planned, tested_2024_ritm, tested_2025_ritm, prevision_2027, 
                        confirmed_by_market, status_manual_tracking
                    ) VALUES (
                        %s, COALESCE(NULLIF(%s, ''), '0')::numeric::integer, %s, %s, %s, %s, %s, %s, 
                        NULLIF(%s, '')::numeric::integer, NULLIF(%s, '')::numeric::integer, NULLIF(%s, '')::numeric::integer, NULLIF(%s, '')::numeric::integer, %s, 
                        %s, %s, %s, %s, %s, %s, %s, 
                        %s, NULLIF(%s, '')::timestamp, %s, %s, NULLIF(%s, '')::date, NULLIF(%s, '')::timestamp, %s, 
                        %s, %s, NULLIF(%s, '')::timestamp, %s, %s, %s, %s, %s, 
                        CURRENT_DATE, TRUE, %s, %s, %s, %s, 
                        %s, %s, %s, %s, %s, %s, 
                        %s, %s
                    ) ON CONFLICT (inventory_id, legacy_id, number) DO UPDATE SET 
                        name=EXCLUDED.name, managing_organization=EXCLUDED.managing_organization, hosting_location=EXCLUDED.hosting_location, 
                        type=EXCLUDED.type, status=EXCLUDED.status, stage=EXCLUDED.stage, business_critical=EXCLUDED.business_critical, 
                        confidentiality_rating=EXCLUDED.confidentiality_rating, integrity_rating=EXCLUDED.integrity_rating, 
                        availability_rating=EXCLUDED.availability_rating, internet_facing=EXCLUDED.internet_facing, 
                        iaas_paas_saas=EXCLUDED.iaas_paas_saas, master_record=EXCLUDED.master_record, stage_ritm=EXCLUDED.stage_ritm, 
                        short_description=EXCLUDED.short_description, requested_for=EXCLUDED.requested_for, opened_by=EXCLUDED.opened_by, 
                        company=EXCLUDED.company, created=EXCLUDED.created, name_of_application=EXCLUDED.name_of_application, 
                        url_of_application=EXCLUDED.url_of_application, estimated_date_pentest=EXCLUDED.estimated_date_pentest, 
                        opened=EXCLUDED.opened, state=EXCLUDED.state, assignment_group=EXCLUDED.assignment_group, 
                        assigned_to=EXCLUDED.assigned_to, closed=EXCLUDED.closed, closed_by=EXCLUDED.closed_by, 
                        close_notes=EXCLUDED.close_notes, service_type=EXCLUDED.service_type, market=EXCLUDED.market, 
                        kpi=EXCLUDED.kpi, gost_service=EXCLUDED.gost_service, whitebox_category=EXCLUDED.whitebox_category, 
                        quarter_planned=EXCLUDED.quarter_planned, year_planned=EXCLUDED.year_planned, planned_with_ritm=EXCLUDED.planned_with_ritm, 
                        month_planned=EXCLUDED.month_planned, week_planned=EXCLUDED.week_planned, tested_2024_ritm=EXCLUDED.tested_2024_ritm, 
                        tested_2025_ritm=EXCLUDED.tested_2025_ritm, prevision_2027=EXCLUDED.prevision_2027, 
                        confirmed_by_market=EXCLUDED.confirmed_by_market, status_manual_tracking=EXCLUDED.status_manual_tracking,
                        last_synced_at=CURRENT_TIMESTAMP;
                ''', (
                    safe_inv_id, safe_ext_id, name, managing_org, hosting_loc, type_val, status_val, stage_val,
                    business_critical, confidentiality, integrity, availability, internet_facing,
                    iaas_paas_saas, master_record, safe_number, stage_ritm, short_desc, requested_for, opened_by,
                    company, created_val, app_name, app_url, est_date, opened_val, state_val,
                    assignment_group, assigned_to, closed_val, closed_by, close_notes, service_type, market, is_kpi,
                    gost_service, whitebox_category, quarter_planned, year_planned,
                    planned_with_ritm, month_planned, week_planned, tested_2024, tested_2025, prev_2027,
                    confirmed_by_market, status_manual
                ))

                # --- UPSERT 2: THE LIGHTWEIGHT UI TABLE (assets) ---
                cursor.execute("SELECT id FROM assets WHERE inventory_id=%s AND ext_id=%s AND number=%s",
                               (safe_inv_id, safe_ext_id, safe_number))
                if cursor.fetchone():
                    cursor.execute(
                        "UPDATE assets SET name=%s, market=%s, gost_service=%s, business_critical=%s, kpi=%s, whitebox_category=%s WHERE inventory_id=%s AND ext_id=%s AND number=%s",
                        (name, market, gost_service, business_critical, kpi_text, whitebox_category, safe_inv_id, safe_ext_id, safe_number))
                else:
                    cursor.execute(
                        "INSERT INTO assets (id, inventory_id, ext_id, number, name, market, gost_service, is_assigned, business_critical, kpi, whitebox_category) VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, %s, %s, %s)",
                        (str(uuid.uuid4()), safe_inv_id, safe_ext_id, safe_number, name, market, gost_service, business_critical, kpi_text, whitebox_category))

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

    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')

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
def get_available_assets(current_user: dict = Depends(get_current_user), cursor = Depends(get_db_cursor)):
    if current_user['role'] == 'pentester':
        raise HTTPException(status_code=403, detail="Pentesters cannot view the asset inventory.")

    # Fetch the assets 
    cursor.execute('''
        SELECT a.id,
               a.inventory_id,
               a.ext_id,
               a.number,
               ra.name,
               ra.market,
               ra.gost_service,
               a.is_assigned,
               t.status,
               t.start_week,
               t.start_year,
               ra.business_critical,
               ra.kpi,
               ra.whitebox_category
        FROM assets a
        JOIN raw_assets ra ON a.inventory_id = ra.inventory_id AND a.number = ra.number
        LEFT JOIN test_assets ta ON a.id = ta.asset_id
        LEFT JOIN tests t ON ta.test_id = t.id
        WHERE ra.pentest_queue = TRUE 
          AND COALESCE(ra.status_manual_tracking, '') != '2027'
        ORDER BY t.start_year DESC, t.start_week DESC -- Brings the most recent test to the top
    ''')

    assets = []
    seen_ids = set() # We will use this to strictly prevent duplicate rows

    for r in cursor.fetchall():
        asset_id = r[0]
        
        # If we have already added this asset to the table, skip it!
        if asset_id in seen_ids:
            continue
            
        seen_ids.add(asset_id)

        # Handle the boolean KPI safely
        kpi_display = ''
        if r[12] is True:
            kpi_display = 'Yes'
        elif r[12] is False:
            kpi_display = 'No'

        assets.append({
            "id": asset_id, 
            "inventory_id": r[1], 
            "ext_id": r[2], 
            "number": r[3],
            "name": r[4], 
            "market": r[5], 
            "gost_service": r[6], 
            "is_assigned": bool(r[7]),
            "test_status": r[8], 
            "start_week": r[9], 
            "start_year": r[10],
            "business_critical": r[11] if r[11] is not None else '',
            "kpi": kpi_display,
            "whitebox_category": r[13] or ''
        })

    # calculate the EXACT numbers based on the deduplicated list
    total_count = len(assets)
    assigned_count = sum(1 for a in assets if a["is_assigned"])

    return {
        "assets": assets, 
        "total": total_count, 
        "assigned": assigned_count
    }


@router.post("/assets/migrate-legacy-sheet")
@limiter.limit("2/minute")
def migrate_legacy_sheet(request: Request, background_tasks: BackgroundTasks, current_user: dict = Depends(require_admin), cursor=Depends(get_db_cursor)):
    GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID')
    GOOGLE_TAB_NAME = os.getenv('GOOGLE_TAB_NAME') 

    try:
        # 1. Fetch from Google Sheets
        credentials, project = google.auth.default(scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
        service = build('sheets', 'v4', credentials=credentials)
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=GOOGLE_SHEET_ID, range=GOOGLE_TAB_NAME).execute()
        values = result.get('values', [])

        if not values:
            raise HTTPException(status_code=404, detail="No data found in the Google Sheet.")

        # 2. Convert directly to your Pandas DataFrame!
        headers = values[0]
        rows = values[1:]
        df = pd.DataFrame(rows, columns=headers)
        
        # 3. Apply your exact filtering logic to drop the 4,700 junk rows instantly
        df.columns = df.columns.str.strip()
        if 'Pentest Queue' in df.columns:
            df = df[df['Pentest Queue'].astype(str).str.strip().str.upper() == 'YES']
        if 'Status_manual_tracking' in df.columns:
            df = df[df['Status_manual_tracking'].astype(str).str.strip() != '2027']
        df = df.fillna('')

        success_count = 0

        # 4. Iterate through only the remaining ~300 valid rows
        for index, row in df.iterrows():
            def get_val(possible_names):
                for col in df.columns:
                    if str(col).strip().lower() in [n.lower() for n in possible_names]:
                        val = str(row[col]).strip()
                        if val and val.lower() != 'nan': return val
                return ''

            # Extract Primary Keys
            inv_id = get_val(['Inventory Id'])
            ext_id = get_val(['ID'])
            number = get_val(['Number'])
            
            if not inv_id and not ext_id and not number: 
                continue
                
            # Failsafe for composite primary key requirements in raw_assets
            safe_inv_id = inv_id if inv_id else f"SYS_GEN_{uuid.uuid4().hex[:8]}"
            safe_number = number if number else "UNASSIGNED"
            safe_ext_id = parse_int(ext_id) or 0

            # ---------------------------------------------------------
            # TABLE 1: UPSERT INTO RAW_ASSETS
            # ---------------------------------------------------------
            cursor.execute('''
                INSERT INTO raw_assets (
                    inventory_id, legacy_id, name, managing_organization, hosting_location, type, status, stage, 
                    business_critical, confidentiality_rating, integrity_rating, availability_rating, internet_facing, 
                    iaas_paas_saas, master_record, number, stage_ritm, short_description, requested_for, opened_by, 
                    company, created, name_of_application, url_of_application, estimated_date_pentest, opened, state, assignment_group, assigned_to, 
                    closed, closed_by, close_notes, service_type, market, kpi, date_first_seen, pentest_queue, gost_service, 
                    whitebox_category, quarter_planned, year_planned, planned_with_ritm, month_planned, week_planned, 
                    tested_2024_ritm, tested_2025_ritm, prevision_2027, confirmed_by_market, status_manual_tracking,
                    last_synced_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
                ) ON CONFLICT (inventory_id, legacy_id, number) DO UPDATE SET 
                    name=EXCLUDED.name, managing_organization=EXCLUDED.managing_organization,
                    hosting_location=EXCLUDED.hosting_location, type=EXCLUDED.type, status=EXCLUDED.status, stage=EXCLUDED.stage,
                    business_critical=EXCLUDED.business_critical, confidentiality_rating=EXCLUDED.confidentiality_rating,
                    integrity_rating=EXCLUDED.integrity_rating, availability_rating=EXCLUDED.availability_rating,
                    internet_facing=EXCLUDED.internet_facing, iaas_paas_saas=EXCLUDED.iaas_paas_saas, master_record=EXCLUDED.master_record,
                    stage_ritm=EXCLUDED.stage_ritm, short_description=EXCLUDED.short_description,
                    requested_for=EXCLUDED.requested_for, opened_by=EXCLUDED.opened_by, company=EXCLUDED.company, created=EXCLUDED.created,
                    name_of_application=EXCLUDED.name_of_application, url_of_application=EXCLUDED.url_of_application, estimated_date_pentest=EXCLUDED.estimated_date_pentest, 
                    opened=EXCLUDED.opened, state=EXCLUDED.state, assignment_group=EXCLUDED.assignment_group, assigned_to=EXCLUDED.assigned_to,
                    closed=EXCLUDED.closed, closed_by=EXCLUDED.closed_by, close_notes=EXCLUDED.close_notes, service_type=EXCLUDED.service_type,
                    market=EXCLUDED.market, kpi=EXCLUDED.kpi, date_first_seen=EXCLUDED.date_first_seen, pentest_queue=EXCLUDED.pentest_queue, gost_service=EXCLUDED.gost_service,
                    whitebox_category=EXCLUDED.whitebox_category, quarter_planned=EXCLUDED.quarter_planned, year_planned=EXCLUDED.year_planned,
                    planned_with_ritm=EXCLUDED.planned_with_ritm, month_planned=EXCLUDED.month_planned, week_planned=EXCLUDED.week_planned,
                    tested_2024_ritm=EXCLUDED.tested_2024_ritm, tested_2025_ritm=EXCLUDED.tested_2025_ritm, prevision_2027=EXCLUDED.prevision_2027,
                    confirmed_by_market=EXCLUDED.confirmed_by_market, status_manual_tracking=EXCLUDED.status_manual_tracking,
                    last_synced_at=CURRENT_TIMESTAMP;
            ''', (
                safe_inv_id, safe_ext_id, get_val(['Name']), get_val(['Managing Organization']), 
                get_val(['Hosting Location']), get_val(['Type']), get_val(['Status']), get_val(['Stage']), 
                parse_int(get_val(['Business Critical'])), parse_int(get_val(['Confidentiality Rating'])), 
                parse_int(get_val(['Integrity Rating'])), parse_int(get_val(['Availability Rating'])), 
                get_val(['Internet Facing']), get_val(['IaaS, PaaS, SaaS']), get_val(['Master Record']), 
                safe_number, get_val(['Stage_RITM']), get_val(['Short description']), 
                get_val(['Requested for']), get_val(['Opened by']), get_val(['Company']), 
                parse_timestamp(get_val(['Created'])), get_val(['Name of the application']), 
                get_val(['URL of the application']), parse_date(get_val(['Please provide an estimated date on when you want the pentest to start'])),
                parse_timestamp(get_val(['Opened'])), get_val(['State']), get_val(['Assignment group']), 
                get_val(['Assigned to']), parse_timestamp(get_val(['Closed'])), get_val(['Closed by']), 
                get_val(['Close notes']), get_val(['Service Type']), get_val(['Market']), 
                parse_bool(get_val(['KPI'])), parse_date(get_val(['Date First Seen'])),
                parse_bool(get_val(['Pentest Queue'])), get_val(['Gost_service']), 
                get_val(['WhiteBox Category']), get_val(['Quarter Planned']), get_val(['Year Planned']), 
                parse_bool(get_val(['Planned with RITM'])), get_val(['Month_Planned']), get_val(['Week_Planned']), 
                get_val(['Tested 2024 (RITM)']), get_val(['Tested 2025 (RITM)']), get_val(['2027 Prevision']), 
                parse_bool(get_val(['Confirmed by market'])), get_val(['Status_manual_tracking'])
            ))

            # ---------------------------------------------------------
            # TABLE 2: YOUR ORIGINAL PLANNER ASSETS LOGIC
            # ---------------------------------------------------------
            name = get_val(['Name']) or 'Unknown Asset'
            market = get_val(['Market']) or 'Global'
            gost_service = get_val(['Gost_service']) or 'Unknown'
            business_critical = get_val(['Business Critical']) or ''
            kpi = get_val(['KPI']) or ''
            whitebox_category = get_val(['WhiteBox Category']) or ''

            # FIXED: Now using safe_inv_id, safe_ext_id, and safe_number to ensure the UI JOIN works!
            cursor.execute("SELECT id FROM assets WHERE inventory_id=%s AND ext_id=%s AND number=%s",
                           (safe_inv_id, safe_ext_id, safe_number))
            if cursor.fetchone():
                cursor.execute(
                    "UPDATE assets SET name=%s, market=%s, gost_service=%s, business_critical=%s, kpi=%s, whitebox_category=%s WHERE inventory_id=%s AND ext_id=%s AND number=%s",
                    (name, market, gost_service, business_critical, kpi, whitebox_category, safe_inv_id, safe_ext_id, safe_number))
            else:
                cursor.execute(
                    "INSERT INTO assets (id, inventory_id, ext_id, number, name, market, gost_service, is_assigned, business_critical, kpi, whitebox_category) VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, %s, %s, %s)",
                    (str(uuid.uuid4()), safe_inv_id, safe_ext_id, safe_number, name, market, gost_service, business_critical, kpi, whitebox_category))

            success_count += 1

        background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')
        
        background_tasks.add_task(
            log_audit_event,
            user_id=current_user["id"],
            username=current_user["username"],
            action="SYNC_LEGACY_SHEET",
            resource_type="ASSET_INVENTORY",
            details=f"Synced {success_count} filtered assets from Legacy Sheet to raw tables."
        )

        return {"message": f"Successfully migrated {success_count} assets from Legacy Sheet!"}

    except Exception as e:
        print(f"Drive Sync Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to sync from Drive: {str(e)}")


@router.post("/assets/sync-drive")
@limiter.limit("5/minute")
def sync_assets_from_drive(
    request: Request, 
    background_tasks: BackgroundTasks, 
    current_user: dict = Depends(require_admin)
):
    # Start the importer in the background
    background_tasks.add_task(run_import_job)

    # Tell the React UI to refresh itself automatically
    background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_ASSETS"}')
    
    background_tasks.add_task(
        log_audit_event,
        user_id=current_user["id"],
        username=current_user["username"],
        action="GOOGLE_DRIVE_SYNC",
        resource_type="ASSET_INVENTORY",
        details="Triggered the background Google Drive importer."
    )

    return {"message": "Google Drive Sync started in the background! The table will update automatically when finished."}


@router.get("/assets/raw")
def get_raw_assets(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    search: Optional[str] = None,
    market: Optional[str] = None,
    kpi_only: Optional[bool] = None,        
    pentest_queue_only: Optional[bool] = None,
    current_user: dict = Depends(get_current_user), 
    cursor=Depends(get_db_cursor)
):
    # Security Check
    if current_user.get("role") == "pentester":
        raise HTTPException(status_code=403, detail="Not authorized to view raw corporate data.")

    try:
        offset = (page - 1) * limit
        params = []
        where_clauses = []

        # Dynamic Filtering
        if search:
            where_clauses.append("(name ILIKE %s OR inventory_id ILIKE %s OR number ILIKE %s)")
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
        if market:
            where_clauses.append("market ILIKE %s")
            params.append(f"%{market}%")

        if kpi_only:
            where_clauses.append("kpi = TRUE")
        if pentest_queue_only:
            where_clauses.append("pentest_queue = TRUE")

        where_str = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        # 1. Get the total count for the frontend pagination math
        count_query = f"SELECT COUNT(*) FROM raw_assets {where_str}"
        cursor.execute(count_query, tuple(params))
        total_items = cursor.fetchone()[0]

        # 2. Get the specific page of data
        data_query = f"SELECT * FROM raw_assets {where_str} ORDER BY name ASC LIMIT %s OFFSET %s"
        cursor.execute(data_query, tuple(params + [limit, offset]))
        
        columns = [col[0] for col in cursor.description]
        raw_assets = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        # Return the payload in a paginated wrapper!
        return {
            "data": raw_assets,
            "pagination": {
                "total": total_items,
                "page": page,
                "limit": limit,
                "pages": (total_items + limit - 1) // limit
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/assets/history")
def get_asset_test_history(
    inventory_id: str, 
    number: str, 
    current_user: dict = Depends(get_current_user), 
    cursor=Depends(get_db_cursor)
):
    if current_user.get("role") == "pentester":
        raise HTTPException(status_code=403, detail="Not authorized.")

    try:
        # Safely joining without ext_id/legacy_id to avoid the 0 vs "" mismatch!
        cursor.execute("""
            SELECT t.id, t.name, t.type, t.status, t.start_week, t.start_year, t.credits_per_week, t.duration_weeks
            FROM tests t
            JOIN test_assets ta ON t.id = ta.test_id
            JOIN assets a ON ta.asset_id = a.id
            WHERE a.inventory_id = %s AND a.number = %s
            ORDER BY t.start_year DESC, t.start_week DESC
        """, (inventory_id, number))
        
        columns = [col[0] for col in cursor.description]
        history = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        return history
    except Exception as e:
        print(f"History Fetch Error: {e}")
        return []


@router.put("/assets/tracking")
def update_asset_tracking(
    inventory_id: str, 
    number: str, 
    data: AssetTrackingUpdate, 
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_admin),
    cursor=Depends(get_db_cursor)
):
    try:
        # update the massive raw_assets table with all manual fields (Single Source of Truth)
        cursor.execute("""
            UPDATE raw_assets SET
                pentest_queue = %s,
                gost_service = %s,
                whitebox_category = %s,
                quarter_planned = %s,
                year_planned = %s,
                planned_with_ritm = %s,
                month_planned = %s,
                week_planned = %s,
                tested_2024_ritm = %s,
                tested_2025_ritm = %s,
                prevision_2027 = %s,
                confirmed_by_market = %s,
                status_manual_tracking = %s
            WHERE inventory_id = %s AND number = %s
        """, (
            data.pentest_queue, data.gost_service, data.whitebox_category,
            data.quarter_planned, data.year_planned, data.planned_with_ritm,
            data.month_planned, data.week_planned, data.tested_2024_ritm,
            data.tested_2025_ritm, data.prevision_2027, data.confirmed_by_market,
            data.status_manual_tracking, inventory_id, number
        ))

        # B. Also update the lean `assets` table just to prevent any UI edge cases
        cursor.execute("""
            UPDATE assets SET 
                gost_service = %s, 
                whitebox_category = %s 
            WHERE inventory_id = %s AND number = %s
        """, (data.gost_service, data.whitebox_category, inventory_id, number))

        
        # C. Broadcast changes to React and log the audit event safely in the background
        background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_ASSETS"}')

        background_tasks.add_task(
            log_audit_event,
            user_id=current_user["id"],
            username=current_user["username"],
            action="UPDATE_ASSET_TRACKING",
            resource_type="ASSET",
            details=f"Updated manual tracking fields for {inventory_id} / {number}"
        )

        return {"message": "Tracking updated successfully"}

    except Exception as e:
        print(f"Update Tracking Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Fetch Last Sync Date
@router.get("/assets/last-sync")
def get_last_sync(cursor=Depends(get_db_cursor)):
    try:
        cursor.execute("SELECT MAX(last_synced_at) FROM raw_assets")
        result = cursor.fetchone()[0]
        if result:
            # Format it nicely for the frontend (e.g., "YYYY-MM-DD HH:MM:SS")
            formatted_date = result.strftime("%Y-%m-%d %H:%M:%S")
            return {"last_sync": formatted_date}
        return {"last_sync": "Never"}
    except Exception as e:
        print(f"Error fetching last sync: {e}")
        return {"last_sync": "Unknown"}


@router.post("/assets/manual")
def create_manual_asset(
    payload: dict, 
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_admin),
    cursor=Depends(get_db_cursor)
):
    try:
        # Automated Fields
        inv_id = f"MANUAL_{uuid.uuid4().hex[:8]}"
        number = payload.get('number') or f"TCKT_{uuid.uuid4().hex[:6]}"
        
        # Helper to convert empty strings to None for strict Postgres columns (Integers, Dates, Timestamps)
        def clean_val(val):
            return None if val == "" else val

        # 1. Insert into Master Table (raw_assets) handling all 49 insertable fields
        cursor.execute('''
            INSERT INTO raw_assets (
                inventory_id, legacy_id, name, managing_organization, hosting_location, type, status, stage, 
                business_critical, confidentiality_rating, integrity_rating, availability_rating, internet_facing, 
                iaas_paas_saas, master_record, number, stage_ritm, short_description, requested_for, opened_by, 
                company, created, name_of_application, url_of_application, estimated_date_pentest, opened, state, 
                assignment_group, assigned_to, closed, closed_by, close_notes, service_type, market, kpi, 
                date_first_seen, pentest_queue, gost_service, whitebox_category, quarter_planned, year_planned, 
                planned_with_ritm, month_planned, week_planned, tested_2024_ritm, tested_2025_ritm, prevision_2027, 
                confirmed_by_market, status_manual_tracking
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, 
                %s, %s, %s, %s, %s, 
                %s, %s, %s, %s, %s, %s, %s, 
                %s, %s, %s, %s, %s, %s, %s, 
                %s, %s, %s, %s, %s, %s, %s, %s, 
                CURRENT_DATE, %s, %s, %s, %s, %s, 
                %s, %s, %s, %s, %s, %s, 
                %s, %s
            )
        ''', (
            inv_id, clean_val(payload.get('legacy_id') or 0), payload.get('name', 'New Manual Asset'), 
            payload.get('managing_organization'), payload.get('hosting_location'), payload.get('type'), 
            payload.get('status'), payload.get('stage'), clean_val(payload.get('business_critical')), 
            clean_val(payload.get('confidentiality_rating')), clean_val(payload.get('integrity_rating')), 
            clean_val(payload.get('availability_rating')), payload.get('internet_facing'), 
            payload.get('iaas_paas_saas'), payload.get('master_record'), number, payload.get('stage_ritm'), 
            payload.get('short_description'), payload.get('requested_for'), payload.get('opened_by'), 
            payload.get('company'), clean_val(payload.get('created')), payload.get('name_of_application'), 
            payload.get('url_of_application'), clean_val(payload.get('estimated_date_pentest')), 
            clean_val(payload.get('opened')), payload.get('state'), payload.get('assignment_group'), 
            payload.get('assigned_to'), clean_val(payload.get('closed')), payload.get('closed_by'), 
            payload.get('close_notes'), payload.get('service_type'), payload.get('market', 'Global'), 
            payload.get('kpi', False), payload.get('pentest_queue', True), 
            payload.get('gost_service', 'Adversary / Manual'), payload.get('whitebox_category'), 
            payload.get('quarter_planned'), payload.get('year_planned'), payload.get('planned_with_ritm', False), 
            payload.get('month_planned'), payload.get('week_planned'), payload.get('tested_2024_ritm'), 
            payload.get('tested_2025_ritm'), payload.get('prevision_2027'), payload.get('confirmed_by_market', False), 
            payload.get('status_manual_tracking', 'Not Planned')
        ))

        # 2. Conditional Insert into UI Table (assets) based on your Golden Rules
        if payload.get('pentest_queue', True) is True and payload.get('status_manual_tracking') != '2027':
            cursor.execute('''
                INSERT INTO assets (
                    id, inventory_id, ext_id, number, name, market, gost_service, whitebox_category, is_assigned
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FALSE)
            ''', (
                str(uuid.uuid4()), inv_id, str(payload.get('legacy_id', 0)), number, 
                payload.get('name', 'New Manual Asset'), payload.get('market', 'Global'), 
                payload.get('gost_service', 'Adversary / Manual'), payload.get('whitebox_category', '')
            ))

        background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_ASSETS"}')
        return {"message": "Asset created successfully!"}

    except Exception as e:
        print(f"Manual Creation Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/assets/raw")
def delete_raw_asset(
    inventory_id: str, 
    number: str, 
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_admin),
    cursor=Depends(get_db_cursor)
):
    try:
        # 1. Find the internal UI asset ID linked to this Master Record
        cursor.execute("SELECT id FROM assets WHERE inventory_id = %s AND number = %s", (inventory_id, number))
        asset_row = cursor.fetchone()

        if asset_row:
            ui_asset_id = asset_row[0]
            
            
            # Find any tests that were linked to this specific asset
            cursor.execute("SELECT test_id FROM test_assets WHERE asset_id = %s", (ui_asset_id,))
            linked_tests = cursor.fetchall()
            
            # Annihilate the tests, their team assignments, and their history
            for (test_id,) in linked_tests:
                cursor.execute("DELETE FROM assignments WHERE test_id = %s", (test_id,))
                cursor.execute("DELETE FROM test_history WHERE test_id = %s", (test_id,))
                cursor.execute("DELETE FROM test_assets WHERE test_id = %s", (test_id,))
                cursor.execute("DELETE FROM tests WHERE id = %s", (test_id,))
            

            # 3. Delete the asset from the UI Planner board
            cursor.execute("DELETE FROM assets WHERE id = %s", (ui_asset_id,))

        # 4. Delete the Master Record completely
        cursor.execute("DELETE FROM raw_assets WHERE inventory_id = %s AND number = %s", (inventory_id, number))

        cursor.connection.commit()

        # Broadcast the deletion so every user's screen updates instantly
        background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_ASSETS"}')
        background_tasks.add_task(manager.broadcast, '{"action": "REFRESH_BOARD"}')

        background_tasks.add_task(
            log_audit_event,
            user_id=current_user["id"],
            username=current_user["username"],
            action="DELETE_ASSET",
            resource_type="ASSET",
            details=f"Permanently deleted asset and severed all test links: {inventory_id} / {number}"
        )

        return {"message": "Asset completely purged from the system."}

    except Exception as e:
        print(f"Delete Asset Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

        
# Temp function to bring back to live the Adv Sim test.
# @router.post("/assets/resurrect-ghosts")
# def resurrect_ghost_assets(cursor=Depends(get_db_cursor)):
#     # This finds all assets that are missing from raw_assets and copies them over!
#     cursor.execute('''
#         INSERT INTO raw_assets (inventory_id, legacy_id, number, name, market, gost_service, pentest_queue)
#         SELECT a.inventory_id, COALESCE(NULLIF(a.ext_id, ''), '0')::integer, a.number, a.name, a.market, a.gost_service, TRUE
#         FROM assets a
#         LEFT JOIN raw_assets ra ON a.inventory_id = ra.inventory_id AND a.number = ra.number
#         WHERE ra.inventory_id IS NULL;
#     ''')
#     return {"message": "Ghost assets resurrected!"}