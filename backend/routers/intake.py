import os
import uuid
import io
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, BackgroundTasks, Response
from pydantic import BaseModel
from google.cloud import storage, pubsub_v1
import json
from PIL import Image
from database import get_db_cursor
from routers.auth import require_admin

router = APIRouter(tags=["Intake"])

# --- GCP Configuration ---
PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "local-dev")
BUCKET_NAME = os.environ.get("INTAKE_BUCKET_NAME", f"{PROJECT_ID}-intake-artifacts")
TOPIC_ID = os.environ.get("INTAKE_TOPIC_ID", "trigger-ai-intake")

# --- Security: Magic Numbers ---
ALLOWED_MAGIC_NUMBERS = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"%PDF-": "application/pdf",
    b"PK\x03\x04": "application/vnd.openxmlformats-officedocument", # DOCX, XLSX, PPTX
}

def verify_and_clean_file(raw_bytes: bytes, filename: str) -> tuple[bytes, str]:
    """Checks the magic number and strips EXIF metadata from images in-memory."""
    
    # 1. Magic Number Check
    header = raw_bytes[:8]
    detected_type = None
    for magic, mime in ALLOWED_MAGIC_NUMBERS.items():
        if header.startswith(magic):
            detected_type = mime
            break
            
    if not detected_type:
        raise HTTPException(status_code=400, detail="Invalid file signature. Only real PNGs, JPEGs, and PDFs are allowed.")

    # 2. PDF Check (No image sanitization needed for PDF)
    if detected_type == "application/pdf":
        return raw_bytes, "PDF"

    # 3. Image Sanitization (Strip EXIF, GPS, hidden payloads)
    try:
        img = Image.open(io.BytesIO(raw_bytes))
        
        # Create a brand new image carrying ONLY the pixel data
        data = list(img.getdata())
        image_without_exif = Image.new(img.mode, img.size)
        image_without_exif.putdata(data)
        
        # Save it to a new byte stream
        clean_io = io.BytesIO()
        img_format = "PNG" if detected_type == "image/png" else "JPEG"
        image_without_exif.save(clean_io, format=img_format)
        
        return clean_io.getvalue(), "IMAGE"
    except Exception as e:
        print(f"Image sanitization failed: {e}")
        raise HTTPException(status_code=400, detail="Corrupted image file.")


@router.post("/intake/")
async def submit_intake_note(
    file: UploadFile = File(None),
    text_content: str = Form(None),
    current_user: dict = Depends(require_admin),
    cursor = Depends(get_db_cursor)
):
    """Receives an uploaded file or pasted text, sanitizes it, and queues it for the AI."""
    if not file and not text_content:
        raise HTTPException(status_code=400, detail="Must provide either a file or text content.")

    note_id = str(uuid.uuid4())
    source_type = "TEXT"
    file_path = f"intake/{note_id}.txt"
    original_filename = "pasted_text.txt"
    final_bytes = b""

    # --- Process Input ---
    if file:
        raw_bytes = await file.read()
        final_bytes, source_type = verify_and_clean_file(raw_bytes, file.filename)
        # Extract safe extension from our internal detection
        ext = ".png" if source_type == "IMAGE" and file.filename.lower().endswith("png") else \
              ".jpg" if source_type == "IMAGE" else ".pdf"
        file_path = f"intake/{note_id}{ext}"
        original_filename = file.filename
    else:
        # It's pasted text. We save it directly as a .txt file
        final_bytes = text_content.encode("utf-8")

    # --- 1. Upload to GCP Storage Bucket ---
    try:
        if os.environ.get("ENV") != "local":
            storage_client = storage.Client()
            bucket = storage_client.bucket(BUCKET_NAME)
            blob = bucket.blob(file_path)
            blob.upload_from_string(final_bytes)
            print(f"✅ Uploaded secure artifact to GCS: {file_path}")
        else:
            print(f"⚠️ [LOCAL DEV] Bypassed GCS upload for {file_path}")
    except Exception as e:
        print(f"GCS Upload Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to store the secure artifact.")

    # --- 2. Save Tracking Row in Database ---
    try:
        cursor.execute("""
            INSERT INTO intake_notes (id, status, file_path, original_filename, source_type, uploaded_by, ai_raw_text)
            VALUES (%s, 'PENDING', %s, %s, %s, %s, %s)
        """, (note_id, file_path, original_filename, source_type, current_user['username'], text_content if text_content else None))
    except Exception as e:
        print(f"Database Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to register intake note.")

    cursor.connection.commit()

    # --- 3. Wake up Sherlock (Pub/Sub Trigger) ---
    try:
        if os.environ.get("ENV") != "local":
            publisher = pubsub_v1.PublisherClient()
            topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)
            
            message_json = json.dumps({"note_id": note_id, "file_path": file_path, "source_type": source_type})
            message_bytes = message_json.encode("utf-8")
            
            publish_future = publisher.publish(topic_path, data=message_bytes)
            publish_future.result() # Wait for acknowledgment
            print(f"🔔 Pub/Sub trigger sent to Sherlock for {note_id}")
    except Exception as e:
        print(f"Pub/Sub Error: {e}")
        # We don't fail the request if the trigger fails, the file is safely in the DB/Bucket
        # A chron job or manual retry could pick it up later

    return {
        "message": "Note secured and queued for AI analysis.",
        "note_id": note_id,
        "status": "PENDING"
    }


@router.get("/intake/")
def get_intake_queue(current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):
    """Fetches the active intake queue for the Admin Inbox."""
    cursor.execute("""
        SELECT id, created_at, status, file_path, original_filename, source_type, uploaded_by, 
               ai_raw_text, ai_summary, ai_extracted_assets
        FROM intake_notes 
        WHERE status IN ('PENDING', 'REVIEW_READY', 'ARCHIVED')
        ORDER BY created_at DESC
    """)

    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


# --- Helper Function for Background Deletion ---
def delete_gcs_blob(file_path: str):
    if os.environ.get("ENV") == "local" or not file_path:
        return
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(file_path)
        if blob.exists():
            blob.delete()
            print(f"🗑️ Cleaned up discarded artifact from GCS: {file_path}")
    except Exception as e:
        print(f"🚨 Failed to delete {file_path} from GCS: {e}")


@router.put("/intake/{note_id}/archive")
def archive_intake_note(
        note_id: str,
        current_user: dict = Depends(require_admin),
        cursor=Depends(get_db_cursor)
):
    """Moves a note out of the active inbox and marks who archived it."""

    # We append the user's name to the ai_summary or a dedicated notes field
    # to keep track of who archived it without needing a complex DB migration today.
    archive_stamp = f"\n\n[Archived by {current_user['name']}]"

    cursor.execute("""
        UPDATE intake_notes 
        SET status = 'ARCHIVED',
            ai_summary = COALESCE(ai_summary, '') || %s
        WHERE id = %s RETURNING id
    """, (archive_stamp, note_id))

    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Note not found")

    cursor.connection.commit()
    return {"message": "Note archived successfully"}


@router.delete("/intake/{note_id}")
def discard_intake_note(
        note_id: str,
        background_tasks: BackgroundTasks,
        current_user: dict = Depends(require_admin),
        cursor=Depends(get_db_cursor)
):
    """Marks a note as discarded and permanently deletes the file from the GCS bucket."""

    # 1. Get the file path before we discard it
    cursor.execute("SELECT file_path FROM intake_notes WHERE id = %s", (note_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Note not found")

    file_path = row[0]

    # 2. Mark as discarded in DB
    cursor.execute("UPDATE intake_notes SET status = 'DISCARDED' WHERE id = %s RETURNING id", (note_id,))
    cursor.connection.commit()

    # 3. Trigger GCS deletion in the background so the UI stays fast
    background_tasks.add_task(delete_gcs_blob, file_path)

    return {"message": "Note discarded successfully and bucket cleanup queued."}


@router.get("/intake/file/{note_id}")
def get_intake_file(note_id: str, current_user: dict = Depends(require_admin), cursor=Depends(get_db_cursor)):
    """Fetches the raw file bytes from GCS so the frontend can preview it."""

    cursor.execute("SELECT file_path, source_type FROM intake_notes WHERE id = %s", (note_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Note not found")

    file_path, source_type = row[0], row[1]

    if source_type == 'TEXT' or not file_path:
        raise HTTPException(status_code=400, detail="This note does not have a downloadable file attached.")

    if os.environ.get("ENV") == "local":
        raise HTTPException(status_code=501, detail="File previews not available in local dev without GCS.")

    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(file_path)

        if not blob.exists():
            raise HTTPException(status_code=404, detail="File physically missing from bucket.")

        file_bytes = blob.download_as_bytes()

        # Determine the correct MIME type for the browser
        mime_type = "application/octet-stream"
        if file_path.lower().endswith(".pdf"):
            mime_type = "application/pdf"
        elif file_path.lower().endswith(".png"):
            mime_type = "image/png"
        elif file_path.lower().endswith(".jpg") or file_path.lower().endswith(".jpeg"):
            mime_type = "image/jpeg"

        return Response(content=file_bytes, media_type=mime_type)

    except Exception as e:
        print(f"GCS Download Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve file from bucket.")