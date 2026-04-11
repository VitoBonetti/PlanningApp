import os
import base64
import json
import requests
from fastapi import FastAPI, Request, HTTPException
from google.cloud import storage, secretmanager
import google.generativeai as genai
import google.auth.transport.requests
import google.oauth2.id_token

app = FastAPI()

# --- Configuration ---
PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
BUCKET_NAME = os.environ.get("INTAKE_BUCKET_NAME")
GEMINI_KEY_NAME = os.environ.get("GEMINI_KEY_NAME")
MAIN_BACKEND_URL = os.environ.get("MAIN_BACKEND_URL")
IAP_CLIENT_ID = os.environ.get("IAP_CLIENT_ID")

# --- Security: Fetch API Key ---
def get_gemini_key():
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{PROJECT_ID}/secrets/{GEMINI_KEY_NAME}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

# --- Security: Dynamic IAM Token for Backend ---
def get_iam_token():
    """Fetches a dynamic OIDC token to authenticate with the main backend."""
    req = google.auth.transport.requests.Request()
    return google.oauth2.id_token.fetch_id_token(req, IAP_CLIENT_ID)


# AI Tools
def search_asset(asset_name: str) -> str:
    """
    Searches the database for an asset by name. 
    Use this when you identify a software, app, or system that needs testing.
    Returns a JSON string of matches with their UUIDs, or 'Not Found'.
    """
    url = f"{MAIN_BACKEND_URL}/api/search-asset"
    headers = {"Authorization": f"Bearer {get_iam_token()}"}
    res = requests.get(url, params={"name": asset_name}, headers=headers)
    return res.text if res.status_code == 200 else "Not Found."


def search_market(market_query: str) -> str:
    """
    Looks up a market by its country code (e.g., 'US', 'FR') or name.
    Returns the exact market code if found.
    """
    url = f"{MAIN_BACKEND_URL}/api/search-market"
    headers = {"Authorization": f"Bearer {get_iam_token()}"}
    res = requests.get(url, params={"query": market_query}, headers=headers)
    return res.text if res.status_code == 200 else "Market Not Found."


def search_market_by_contact(person_name: str) -> str:
    """
    Searches the market_contact table by a person's name or email.
    Use this if no market is mentioned, but a specific contact person is.
    Returns the market code associated with this person.
    """
    url = f"{MAIN_BACKEND_URL}/api/search-contact"
    headers = {"Authorization": f"Bearer {get_iam_token()}"}
    res = requests.get(url, params={"name": person_name}, headers=headers)
    return res.text if res.status_code == 200 else "Contact Not Found."


def check_asset_tests(asset_id: str) -> str:
    """
    Checks if a specific asset_id already has active tests assigned to it.
    Use this to verify if the asset is already being tested.
    """
    url = f"{MAIN_BACKEND_URL}/api/check-tests"
    headers = {"Authorization": f"Bearer {get_iam_token()}"}
    res = requests.get(url, params={"asset_id": asset_id}, headers=headers)
    return res.text if res.status_code == 200 else "No active tests found for this asset."

# main logic trigger

@app.post("/")
async def pubsub_trigger(request: Request):
    envelope = await request.json()
    if not envelope or "message" not in envelope:
        raise HTTPException(status_code=400, detail="Invalid Pub/Sub format")
    
    data = json.loads(base64.b64decode(envelope["message"]["data"]).decode("utf-8"))
    note_id = data.get("note_id")
    file_path = data.get("file_path")
    source_type = data.get("source_type")

    print(f"🕵️ Sherlock waking up as an Agent for note: {note_id}")

    try:
        # 1. Get File
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)
        file_bytes = bucket.blob(file_path).download_as_bytes()
        
        # 2. Setup Gemini 1.5 Pro with Tools
        genai.configure(api_key=get_gemini_key())
        
        ai_tools = [search_asset, search_market, search_market_by_contact, check_asset_tests]
        model = genai.GenerativeModel('gemini-2.5-pro', tools=ai_tools)

        # 3. The System Prompt
        sys_prompt = """
        You are a highly intelligent Cybersecurity Operations agent. Your job is to extract pentest request data.

        CRITICAL RULES:
        1. Context matters. Differentiate between the sender of a message, the receiver, and the actual software/assets to be tested. Do NOT search the database for the receiver's name.
        2. A request might mention MULTIPLE assets. Search for all of them.
        3. Use your tools to verify Asset UUIDs and Market Codes. If a tool returns "Not Found", leave the UUID as null. Do not hallucinate UUIDs.
        4. ABSOLUTE STOP CONDITION: If a tool returns "Not Found.", YOU MUST NOT call that tool again for the same asset or market. Accept the null result immediately and proceed. Do NOT retry variations of the search.

        Return ONLY a raw JSON object with this exact structure (no markdown tags):
        {
          "summary": "1-sentence summary",
          "assets": [
             {
               "asset_id": "verified-uuid-from-db-or-null",
               "name_mentioned": "name from text",
               "market": "verified-market-code-or-null",
               "confidence": 85
             }
          ]
        }
        """

        # 4. Start the Agentic Chat Session
        chat = model.start_chat(enable_automatic_function_calling=True)

        if source_type == 'TEXT':
            response = chat.send_message([sys_prompt, file_bytes.decode('utf-8')])
        else:
            mime = "application/pdf" if file_path.endswith(".pdf") else "image/png"
            response = chat.send_message([sys_prompt, {"mime_type": mime, "data": file_bytes}])

        # 5. Parse the final JSON response
        raw_text = response.text.strip()
        print(f"Raw AI Output: {raw_text}") # Helpful for debugging later!
        
        # Strip out any markdown blocks by finding the true start and end of the JSON
        start_idx = raw_text.find('{')
        end_idx = raw_text.rfind('}')
        
        if start_idx != -1 and end_idx != -1:
            clean_json_string = raw_text[start_idx:end_idx + 1]
        else:
            clean_json_string = raw_text # Fallback
            
        ai_data = json.loads(clean_json_string)
        
        # 6. Save to DB (VIA HTTP REQUEST TO MAIN BACKEND!)
        payload = {
            "note_id": note_id,
            "summary": ai_data.get("summary", "Analysis complete."),
            "assets": ai_data.get("assets", [])
        }
        
        url = f"{MAIN_BACKEND_URL}/api/complete-intake"
        headers = {"Authorization": f"Bearer {get_iam_token()}"}
        save_res = requests.post(url, json=payload, headers=headers)
        
        # Throw an error if the backend rejected the save
        save_res.raise_for_status()

        print(f"✅ Sherlock Agent successfully resolved and saved note: {note_id}")
        return {"status": "success"}

    except Exception as e:
        print(f"🚨 Sherlock error: {e}")
        return {"status": "error", "detail": str(e)}