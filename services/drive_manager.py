import os
import google.auth
from googleapiclient.discovery import build
from database import db_cursor_context 

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

    