import os
import google.auth
from googleapiclient.discovery import build
from database import db_cursor_context 
import uuid
from datetime import datetime


class DriveManager:
    def __init__(self):
        # Exact same native auth pattern as importer.py
        scopes = ["https://www.googleapis.com/auth/drive"]
        creds, project = google.auth.default(scopes=scopes)
        self.drive_service = build('drive', 'v3', credentials=creds)
        self.source_folder_id = os.getenv('SOURCE_FOLDER_ID')

    def find_folder(self, name: str, parent_id: str):
        """Searches for a specific folder inside a parent."""
        query = f"name='{name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = self.drive_service.files().list(
            q=query, fields="files(id, name, webViewLink)", supportsAllDrives=True, includeItemsFromAllDrives=True
        ).execute()
        items = results.get('files', [])
        return items[0] if items else None

    def create_folder(self, name: str, parent_id: str):
        """Creates a new folder inside a parent."""
        file_metadata = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }
        return self.drive_service.files().create(
            body=file_metadata, fields='id, webViewLink', supportsAllDrives=True
        ).execute()

    def get_or_create_folder(self, name: str, parent_id: str):
        folder = self.find_folder(name, parent_id)
        return folder if folder else self.create_folder(name, parent_id)

    def provision_test_workspace(self, test_id: str, year: int, service_name: str, market: str, test_name: str):
        try:
            # 1. Find "Reports" folder inside SOURCE_FOLDER_ID
            reports_folder = self.get_or_create_folder("Reports", self.source_folder_id)
            
            # 2. Year folder
            year_folder = self.get_or_create_folder(str(year), reports_folder['id'])
            
            # 3. Map the Service Name to the specific Drive Folder string
            service_lower = (service_name or "").lower()
            if "white" in service_lower: clean_service = "White"
            elif "black" in service_lower: clean_service = "Black"
            elif "adversary" in service_lower: clean_service = "Adversary Simulation"
            else: clean_service = "Other"
            
            service_folder = self.get_or_create_folder(clean_service, year_folder['id'])
            
            # 4. Market folder (fallback to 'General' if no market is assigned)
            safe_market = market if market else "General"
            market_folder = self.get_or_create_folder(safe_market, service_folder['id'])
            
            # 5. Create the actual Test folder
            test_folder = self.get_or_create_folder(test_name, market_folder['id'])
            
            # 6. Save back to the database
            with db_cursor_context() as cursor:
                cursor.execute(
                    "UPDATE tests SET drive_folder_id = %s, drive_folder_url = %s WHERE id = %s",
                    (test_folder['id'], test_folder['webViewLink'], test_id)
                )
            print(f"Successfully provisioned Drive folder for test: {test_name}")
                
        except Exception as e:
            print(f"Failed to provision Drive workspace: {e}")

    def archive_test_workspace(self, folder_id: str, test_name: str):
        try:
            body = {'name': f"[DELETED] - {test_name}"}
            self.drive_service.files().update(
                fileId=folder_id, body=body, supportsAllDrives=True
            ).execute()
            print(f"Archived Drive folder {folder_id}")
        except Exception as e:
            print(f"Failed to archive Drive workspace: {e}")


# Helper functions for FastAPI BackgroundTasks
def background_provision_workspace(test_id, year, service_name, market, test_name):
    DriveManager().provision_test_workspace(test_id, year, service_name, market, test_name)


def background_archive_workspace(folder_id, test_name):
    DriveManager().archive_test_workspace(folder_id, test_name)


def scan_folder_for_files(self, folder_id: str):
        """Fetches all files (ignoring sub-folders) inside a specific Drive folder."""
        # Query: Inside this folder, NOT trashed, and NOT a folder itself
        query = f"'{folder_id}' in parents and trashed=false and mimeType != 'application/vnd.google-apps.folder'"
        try:
            results = self.drive_service.files().list(
                q=query, 
                fields="files(id, name, mimeType, webViewLink, modifiedTime)", 
                supportsAllDrives=True, 
                includeItemsFromAllDrives=True
            ).execute()
            return results.get('files', [])
        except Exception as e:
            print(f"Error scanning folder {folder_id}: {e}")
            return []


def run_daily_document_sync(self):
    """Finds all provisioned test folders and indexes their files into the database."""
    print("Starting Daily Drive Document Sync...")
    
    with db_cursor_context() as cursor:
        # 1. Get all tests that have a Google Drive folder
        cursor.execute("SELECT id, drive_folder_id FROM tests WHERE drive_folder_id IS NOT NULL")
        tests_with_folders = cursor.fetchall()
        
        success_count = 0
        
        for test_id, folder_id in tests_with_folders:
            files = self.scan_folder_for_files(folder_id)
            
            for f in files:
                # Convert Google's ISO time string to standard timestamp
                mod_time = datetime.strptime(f['modifiedTime'], "%Y-%m-%dT%H:%M:%S.%fZ") if 'modifiedTime' in f else datetime.now()
                
                # 2. UPSERT into the database
                cursor.execute('''
                    INSERT INTO test_documents (id, test_id, drive_file_id, file_name, mime_type, file_url, last_modified, synced_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (drive_file_id) 
                    DO UPDATE SET 
                        file_name = EXCLUDED.file_name,
                        file_url = EXCLUDED.file_url,
                        last_modified = EXCLUDED.last_modified,
                        synced_at = CURRENT_TIMESTAMP
                ''', (
                    str(uuid.uuid4()), test_id, f['id'], f['name'], 
                    f.get('mimeType', 'unknown'), f.get('webViewLink', ''), mod_time
                ))
                success_count += 1
        
        # Optional: Delete records in the DB if they were removed from Google Drive
        # (By deleting rows where synced_at is older than the start of this sync job)
        
        print(f"✅ Document Sync Complete. Indexed/Updated {success_count} files.")