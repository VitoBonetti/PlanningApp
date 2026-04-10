import os
import base64
import json
from fastapi import FastAPI, Request, HTTPException
from google.cloud import storage
from google.cloud.sql.connector import Connector, IPTypes
import pg8000
import sqlalchemy

app = FastAPI()

# --- Configuration ---
PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
LOCATION = os.environ.get("LOCATION")
INSTANCE_NAME = os.environ.get("DB_INSTANCE_NAME")
DB_NAME = os.environ.get("POSTGRES_DB")
DB_USER = os.environ.get("IAM_SA_EMAIL")
BUCKET_NAME = os.environ.get("INTAKE_BUCKET_NAME")

# --- Database Connection ---
def get_db_connection():
    connector = Connector()
    conn = connector.connect(
        f"{PROJECT_ID}:{LOCATION}:{INSTANCE_NAME}",
        "pg8000",
        user=DB_USER,
        db=DB_NAME,
        enable_iam_auth=True,
        ip_type=IPTypes.PRIVATE
    )
    return conn

@app.post("/")
async def pubsub_trigger(request: Request):
    """This endpoint is called automatically by Google Pub/Sub."""
    envelope = await request.json()

    # 1. Validate the Pub/Sub payload
    if not envelope or "message" not in envelope:
        raise HTTPException(status_code=400, detail="Invalid Pub/Sub message format")
    
    pubsub_message = envelope["message"]
    
    if "data" not in pubsub_message:
        raise HTTPException(status_code=400, detail="No data in Pub/Sub message")

    # 2. Decode the Base64 message sent by your main backend
    data_json = base64.b64decode(pubsub_message["data"]).decode("utf-8")
    data = json.loads(data_json)
    
    note_id = data.get("note_id")
    file_path = data.get("file_path")
    source_type = data.get("source_type")

    print(f"🕵️ Sherlock woke up! Processing note: {note_id}")

    try:
        # 3. Download the file from the Google Cloud Storage bucket
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(file_path)
        
        # Download the file into memory
        file_bytes = blob.download_as_bytes()
        
        # ==========================================
        # 🧠 AI LOGIC GOES HERE (Placeholder for now)
        # ==========================================
        # If source_type == 'TEXT': pass file_bytes.decode('utf-8') to LLM
        # If source_type == 'IMAGE': pass file_bytes to Vision AI / OCR
        
        mock_summary = "Admin uploaded a document requesting a test."
        mock_asset_guess = "00000000-0000-0000-0000-000000000000" # Dummy UUID
        mock_market = "US"
        mock_confidence = 85
        # ==========================================

        # 4. Update the Database so the Admin sees it in the Inbox
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE intake_notes 
            SET status = 'REVIEW_READY', 
                ai_summary = %s,
                ai_best_guess_asset_id = %s,
                ai_best_guess_market = %s,
                ai_confidence = %s
            WHERE id = %s
        """, (mock_summary, mock_asset_guess, mock_market, mock_confidence, note_id))
        
        conn.commit()
        cursor.close()
        conn.close()

        print(f"✅ Successfully processed {note_id}. Going back to sleep.")
        return {"status": "success"}

    except Exception as e:
        print(f"🚨 Sherlock encountered an error: {e}")
        # Return a 200 even on error so Pub/Sub doesn't infinitely retry a broken file
        return {"status": "error", "detail": str(e)}