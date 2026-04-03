import gspread
import pandas as pd
import os
import google.auth
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import requests
from datetime import datetime
import uuid

# Adjust this import to wherever your database connection logic lives!
from database import db_cursor_context 

# ==========================================
# SECTION 1: CONFIGURATION (Kept Exactly as Yours)
# ==========================================
class Config:
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    SHARED_DRIVE_ID = os.getenv('SHARED_DRIVE_ID')
    SOURCE_FOLDER_ID = os.getenv('SOURCE_FOLDER_ID')
    ARCHIVE_FOLDER_ID = os.getenv('ARCHIVE_FOLDER_ID')
    
    S1_PATTERN = "Assets_"
    S1_TAB_NAME = "Asset Attributes"

    S2_NAME_EXACT = "Pentest requests - blackbox_whitebox"
    S2_TAB_INDEX = 0
    OPENED_CUTOFF = pd.Timestamp("2025-11-30 23:59:59")
    CLOSED_CUTOFF = pd.Timestamp("2026-01-06 23:59:59")

    # Kept your Market Mapping exactly as is...
    MARKET_MAPPING = {
        "TCS": ["TCS"], "AR": ["Argentina", "Randstad Argentina"],
        "AT": ['Austria', "Randstad Austria"], "AU": ["Australia", "Randstad APAC", "Randstad AU", "Randstad Asia Pacific bv (Randstad SEA)", "Randstad ANZ"],
        "DIGITAL": ["Randstad Digital Global", "Randstad Digital Talent Center Services", "Ausy", "Torc", "Ausy Group"],
        "BE": ["Belgium", "GROUP BELGIUM"], "BR": ["Brazil", "Randstad Brazil"],
        "CA": ["Canada", "Randstad Canada"], "CH": ["Switzerland", "Randstad (Schweiz) AG (RCH)"],
        "CL": ["Chile", "Randstad Chile"], "CN": ["China", "Randstad China"],
        "CZ": ["Czech Republic", "Randstad Czech Republic"],
        "DE": ['Germany', 'Randstad Group Germany bv', 'Randstad Outsourcing Germany', 'Randstad Sourceright GmbH', 'Randstad Deutschland GmbH & Co. KG', 'Randstad Group Germany (operations)'],
        "DEGU": ["GULP", "GULP Information Services GmbH", 'Randstad Professional GmbH', "Gulp Group Germany", "GULP  Solution Services GmbH & Co. KG"],
        "DETT": ["Tempo-Team", "Tempo-Team Germany (combined entities)", "Tempo-Team Group b.v."],
        "DETW": ["Twago", "Twago (Team2Venture GmbH)"],
        "HLD": ["Randstad Holding", "Randstad Holding (Group)", "Randstad Holding (OpCo)", "Randstad Global Capability Center"],
        "GIS": ["Digital Factory", "Randstad Global IT Solutions BV", "Randstad Automotive GmbH & Co. KG", "RSH Group MarCom"],
        "DK": ["Denmark", "Randstad Denmark"],
        "ES": ["Spain", "Avanzo Learning Progress SA", "Randstad España SLU", "Randstad Empleo ETT, SAU", "Randstad Project Services SLU", "Randstad Technologies SAU", "Fundación Randstad", "Randstad Consultores y Soluciones de Recursos Humanos SLU"],
        "FR": ["France", "Randstad Group in France", "Groupe Randstad France SASU", "Randstad France SASU", "Randstad Sourceright SASU", "Select TT Appel Médical"],
        "GR": ["Greece", "Randstad Greece"], "HU": ["Hungary", "Randstad Hungary"],
        "IN": ["India", "Randstad India"], "IT": ["Italia", "Randstad Group Italia Spa", "Randstad Services", "Intempo"],
        "JP": ["Japan", "Randstad Japan"], "LU": ["Luxembourg", "Group Luxembourg"],
        "MO": ["Monster", "Monster Worldwide, Inc."], "MX": ["Mexico", "Randstad Mexico"],
        "NL": ["Nederland", "Netherlands", "Randstad Groep Nederland", "Yacht Group Nederland b.v.", "Randstad Nederland b.v."],
        "NO": ["Norway", "Randstad Norway"], "PL": ["Polska", "Poland", "Randstad Polska Sp.z o.o"],
        "PT": ["Portugal", "RANDSTAD II - PRESTAÇÃO DE SERVIÇOS, LDA.", "Randstad Portugal", "RANDSTAD II - PRESTAÇÃO DE SERVIÇOS UNIPESSOAL, LDA"],
        "RO": ["Romania", "Randstad Romania"], "ROS": ["Offshore", "Randstad Offshore Services"],
        "RS": ["RiseSmart", "Randstad Risesmart", "Risesmart France", "Risesmart China", "Mühlenhoff by Randstad Risesmart"],
        "RSR": ["Sourceright", "Randstad Sourceright", "Randstad Sourceright Global", "Randstad Sourceright EMEA", "Randstad Sourceright APAC", "Randstad Sourceright France", "Randstad Enterprise", "RSR France", "RSR Germany", "Randstad Sourceright NAM"],
        "SE": ["Sweden", "Randstad Sweden"], "TR": ["Turkey", "Randstad Turkey"],
        "UK": ["United Kingdom", "Randstad UK"], "US": ["Celerity", "United States", "Randstad US", "Randstad North America, Inc."]
    }
    MARKET_LOOKUP = {org: code for code, orgs in MARKET_MAPPING.items() for org in orgs}
    # WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbw0q988Alpc8jkiWa2wedfB3tWzXCAnMYL28zvVL9fltufKI69X0EPgZCqTaWoi5bfk/exec"

# ==========================================
# SECTION 2 & 3: GOOGLE DRIVE & DATA BLENDING
# ==========================================
class GoogleServices:
    def __init__(self):
        # Always run in Cloud mode for the backend
        creds, project = google.auth.default(scopes=Config.SCOPES)
        self.creds = creds
        self.gc = gspread.authorize(self.creds)
        self.drive_service = build('drive', 'v3', credentials=self.creds)

    def get_latest_file_id(self, name_pattern, sort_method='name'):
        query = (f"name contains '{name_pattern}' and not name contains 'zArchived_' "
                 f"and '{Config.SOURCE_FOLDER_ID}' in parents and trashed = false")
        results = self.drive_service.files().list(
            q=query, fields="files(id, name, createdTime)", supportsAllDrives=True, includeItemsFromAllDrives=True
        ).execute()
        files = results.get('files', [])
        if not files: return None
        files.sort(key=lambda x: x['createdTime'] if sort_method == 'createdTime' else x['name'], reverse=True)
        return files[0]['id']

    def read_sheet(self, sheet_id, tab_identifier):
        try:
            sh = self.gc.open_by_key(sheet_id)
            ws = sh.get_worksheet(tab_identifier) if isinstance(tab_identifier, int) else sh.worksheet(tab_identifier)
            rows = ws.get_all_values()
            if not rows: return None
            return pd.DataFrame(rows[1:], columns=rows[0])
        except Exception as e:
            print(f"Error reading {sheet_id}: {e}")
            return None

class DataProcessor:
    @staticmethod
    def process_assets(df):
        if df is None: return None
        df_clean = df[df['Status'] != 'Archived'].copy()
        if 'Managing Organization' in df_clean.columns:
            df_clean['Managing Organization'] = df_clean['Managing Organization'].astype(str).str.strip()
            df_clean['Market'] = df_clean['Managing Organization'].map(Config.MARKET_LOOKUP).fillna('UNKNOW')
        return df_clean[df_clean['Market'] != 'MO']

    @staticmethod
    def process_pentest(df):
        if df is None: return None
        df.rename(columns={"1. OneTrust Asset ID": "ID", "Stage": "Stage_RITM"}, inplace=True)
        df.columns = df.columns.str.strip()
        df['Opened_dt'] = pd.to_datetime(df['Opened'], errors='coerce')
        df['Closed_dt'] = pd.to_datetime(df['Closed'], errors='coerce')
        return df[(df['Opened_dt'] > Config.OPENED_CUTOFF) & ((df['Closed_dt'].isna()) | (df['Closed_dt'] > Config.CLOSED_CUTOFF))].copy()

    @staticmethod
    def blend_data(df_assets, df_pentest):
        df_assets['ID'] = df_assets['ID'].astype(str).str.strip()
        df_pentest['ID'] = df_pentest['ID'].astype(str).str.strip()
        merged = pd.merge(df_assets, df_pentest, on='ID', how='left')
        return merged.fillna('')

# ==========================================
# SECTION 4: THE NEW DATABASE SYNC
# ==========================================
def sync_to_database(df):
    """
    This replaces update_target_sheet.
    It writes directly to PostgreSQL, updating automated fields but IGNORING manual fields.
    """
    print(f"Syncing {len(df)} records directly to PostgreSQL...")
    success_count = 0
    
    with db_cursor_context() as cursor:
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
            
            if not inv_id and not ext_id and not number: 
                continue
                
            safe_inv_id = inv_id if inv_id else f"SYS_GEN_{uuid.uuid4().hex[:8]}"
            safe_number = number if number else "UNASSIGNED"
            safe_ext_id = ext_id if ext_id else '0' # Handles the 0 vs "" issue safely

            # ON CONFLICT DO UPDATE SET block completely ignores the 13 manual fields like 'quarter_planned' and 'status_manual_tracking'
            try:
                cursor.execute('''
                    INSERT INTO raw_assets (
                        inventory_id, legacy_id, name, managing_organization, hosting_location, type, status, stage, 
                        business_critical, confidentiality_rating, integrity_rating, availability_rating, internet_facing, 
                        iaas_paas_saas, master_record, number, stage_ritm, short_description, requested_for, opened_by, 
                        company, created, name_of_application, url_of_application, estimated_date_pentest, opened, state, assignment_group, assigned_to, 
                        closed, closed_by, close_notes, service_type, market, date_first_seen, 
                        last_synced_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, NULLIF(%s, '')::int, NULLIF(%s, '')::int, NULLIF(%s, '')::int, NULLIF(%s, '')::int, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
                        NULLIF(%s, '')::timestamp, %s, %s, NULLIF(%s, '')::date, NULLIF(%s, '')::timestamp, %s, %s, %s, NULLIF(%s, '')::timestamp, %s, %s, %s, %s, 
                        COALESCE(NULLIF(%s, '')::date, CURRENT_DATE), CURRENT_TIMESTAMP
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
                        market=EXCLUDED.market, 
                        last_synced_at=CURRENT_TIMESTAMP;
                ''', (
                    safe_inv_id, safe_ext_id, get_val(['Name']), get_val(['Managing Organization']), 
                    get_val(['Hosting Location']), get_val(['Type']), get_val(['Status']), get_val(['Stage']), 
                    get_val(['Business Critical']), get_val(['Confidentiality Rating']), get_val(['Integrity Rating']), get_val(['Availability Rating']), 
                    get_val(['Internet Facing']), get_val(['IaaS, PaaS, SaaS']), get_val(['Master Record']), 
                    safe_number, get_val(['Stage_RITM']), get_val(['Short description']), 
                    get_val(['Requested for']), get_val(['Opened by']), get_val(['Company']), 
                    get_val(['Created']), get_val(['Name of the application']), get_val(['URL of the application']), 
                    get_val(['Please provide an estimated date on when you want the pentest to start']), get_val(['Opened']), get_val(['State']), get_val(['Assignment group']), 
                    get_val(['Assigned to']), get_val(['Closed']), get_val(['Closed by']), get_val(['Close notes']), 
                    get_val(['Service Type']), get_val(['Market']), get_val(['Date First Seen'])
                ))
                
                # Also ensure the lightweight `assets` table exists for the UI
                cursor.execute("INSERT INTO assets (id, inventory_id, ext_id, number, name, market, is_assigned) VALUES (%s, %s, %s, %s, %s, %s, FALSE) ON CONFLICT DO NOTHING",
                               (str(uuid.uuid4()), safe_inv_id, safe_ext_id, safe_number, get_val(['Name']), get_val(['Market'])))
                
                success_count += 1
            except Exception as e:
                print(f"Row Error on {safe_inv_id}: {e}")
                
    print(f"✅ Successfully synced {success_count} assets to the database.")

# THE MAIN TRIGGER FUNCTION
def run_import_job():
    try:
        services = GoogleServices()
        processor = DataProcessor()

        print("--- 1. Fetching Source Data from Google Drive ---")
        id_1 = services.get_latest_file_id(Config.S1_PATTERN, 'name')
        id_2 = services.get_latest_file_id(Config.S2_NAME_EXACT, 'createdTime')

        if id_1 and id_2:
            df_assets = processor.process_assets(services.read_sheet(id_1, Config.S1_TAB_NAME))
            df_pentest = processor.process_pentest(services.read_sheet(id_2, Config.S2_TAB_INDEX))
            
            if df_assets is not None and df_pentest is not None:
                print("--- 2. Blending Sources ---")
                df_fresh = processor.blend_data(df_assets, df_pentest)
                
                print("--- 3. Syncing to PostgreSQL ---")
                sync_to_database(df_fresh)
            else:
                print("Error: Failed to process dataframes.")
        else:
            print("Error: Could not find source files in Drive.")
            
    except Exception as e:
        print(f"Background Import Job Failed: {e}")