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
    Returns a JSON string containing comprehensive test details: test name, service name, type, credits per week, duration, planned start week/year, and status.
    Use this enriched data to write a highly detailed "Mentioned Test Details" paragraph in your summary.
    """
    url = f"{MAIN_BACKEND_URL}/api/check-tests"
    headers = {"Authorization": f"Bearer {get_iam_token()}"}
    res = requests.get(url, params={"asset_id": asset_id}, headers=headers)
    return res.text if res.status_code == 200 else "No active tests found for this asset."

def get_all_valid_markets() -> str:
    """Returns the full list of all active markets and their codes. Use this to find unconventional markets."""
    url = f"{MAIN_BACKEND_URL}/api/all-markets"
    headers = {"Authorization": f"Bearer {get_iam_token()}"}
    res = requests.get(url, headers=headers)
    return res.text if res.status_code == 200 else "[]"


def check_service_capacity(service_name: str, quarter: int, year: int) -> str:
    """
    Checks the planning system for available weeks.
    Args:
        service_name: The requested service (e.g., "Blackbox", "Whitebox").
        quarter: integer 1, 2, 3, or 4.
        year: integer year (e.g., 2026).
    Returns: JSON with available weeks for that service in that quarter.
    """
    url = f"{MAIN_BACKEND_URL}/api/check-capacity"
    headers = {"Authorization": f"Bearer {get_iam_token()}"}
    res = requests.get(url, params={"service_name": service_name, "quarter": quarter, "year": year}, headers=headers)
    return res.text if res.status_code == 200 else "Could not check capacity."

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
        
        ai_tools = [search_asset, search_market, search_market_by_contact, check_asset_tests, get_all_valid_markets, check_service_capacity]
        model = genai.GenerativeModel('gemini-2.5-pro', tools=ai_tools)

        # 3. The System Prompt
        sys_prompt = """
        You are a highly intelligent Cybersecurity Operations agent. Your job is to extract pentest request data, cross-reference it with the database, and proactively propose planning schedules.

        CRITICAL RULES & LOGIC FLOW:
        1. Context & Asset Extraction: Identify SENDER, ASSETS (including RITMs), and TEST DETAILS. Use `search_asset` which can match names OR RITM numbers.

        2. Market Mapping: Do NOT assume market codes based on standard geography. ALWAYS call `get_all_valid_markets` to see the exact valid markets available in the system, and map the text to one of those options.

        3. Proactive Capacity Planning (Agent Proposal):
           - If the text mentions a target timeframe (e.g., Q2 2026, Q3 2026) AND a service (Whitebox, Blackbox, Adversary Simulation), you MUST call `check_service_capacity`.
           - Pass the service string, the quarter (1-4), and the year to the tool.
           - Use the tool's result to write a distinct 'Agent Proposal' paragraph in your summary.
             * Example A: "Agent Proposal: For the Blackbox test in Q3 2026, there is enough space to plan the test (available in more than 4 weeks)."
             * Example B: "Agent Proposal: For the Whitebox test in Q2 2026, possible space is available in weeks 16, 17, and 21."
             * Example C: "Agent Proposal: For the Whitebox test in Q2 2026, there is currently no capacity available."

        4. Dynamic Confidence Scoring (Reflects your certainty that this is the target asset):
           - 85-100: Exact match in VERIFIED assets, OR the text is extremely clear and you successfully verified the Market.
           - 70-84: Fuzzy match in VERIFIED DB, OR it is clearly an asset but the Market is missing.
           - 40-69: Match found ONLY in RAW assets, OR you are guessing based on vague context.
           - 0-39: Very vague mention, highly unsure if it is actually an in-scope asset.

        5. ABSOLUTE STOP CONDITION: If a tool returns "Not Found", YOU MUST NOT call that tool again. Accept the null result.

        Return ONLY a raw JSON object with this exact structure (no markdown tags). Use \\n\\n in the summary for paragraph breaks:
        {
          "summary": "Paragraph 1: Sender & Context.\\n\\nParagraph 2: Assets & Markets.\\n\\nParagraph 3: Existing Test Details.\\n\\nParagraph 4: Agent Proposal (Capacity availability based on your checks).",
          "assets": [
             {
               "asset_id": "verified-uuid-from-db-or-null",
               "name_mentioned": "name exactly as written in the text",
               "market": "verified-market-code-or-null",
               "confidence": <integer>,
               "active_tests": [
                   { "name": "Name", "service_name": "Service", "start_week": 14, "start_year": 2024 }
               ] 
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