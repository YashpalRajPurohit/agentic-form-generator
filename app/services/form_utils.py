import json
import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from app.database.schemas import Form, QuestionType

ROOT_DIR = Path(__file__).resolve().parent.parent.parent

# 1. Tells OAuthLib to ignore the "Scope has changed" warnings
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
# 2. Allows OAuthLib to work over regular HTTP (localhost) instead of requiring HTTPS
if "localhost" in os.getenv("GOOGLE_REDIRECT_URI", "localhost"):
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    
# --- OAUTH CONFIGURATION ---
SCOPES = [
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/drive.file"
]

CLIENT_SECRETS_FILE = os.getenv(
    "GOOGLE_CLIENT_SECRETS_FILE", 
    str(ROOT_DIR / "credentials" / "web_client_secret.json")
)

REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback")


# ==========================================
# WEB OAUTH 2.0 FLOW HELPERS
# ==========================================

def get_google_email(creds_dict: dict):
    """Fetches the user's real email directly from Google."""
    try:
        creds = Credentials(**creds_dict)
        service = build('oauth2', 'v2', credentials=creds)
        user_info = service.userinfo().get().execute()
        return user_info.get("email")
    except Exception as e:
        print(f"Failed to fetch user email: {e}")
        return None

def get_auth_flow() -> Flow:
    """Configures the OAuth flow using Web Application client secrets."""
    return Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )


def generate_auth_url() -> tuple[str, str, str]:
    """Generates the Google OAuth consent URL, a state token, and a PKCE code verifier."""
    flow = get_auth_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent" 
    )
    # Extract the secretly generated PKCE verifier so we can save it!
    return auth_url, state, getattr(flow, 'code_verifier', None)


def exchange_code_for_credentials(code: str, state: str, code_verifier: str) -> dict:
    """Exchanges Google's callback code for a credentials dictionary."""
    # We must explicitly rebuild the flow with the EXACT state from the session
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=state,
        redirect_uri=REDIRECT_URI
    )
    
    # Inject the PKCE verifier back into the flow
    if code_verifier:
        flow.code_verifier = code_verifier
        
    flow.fetch_token(code=code)
    creds = flow.credentials

    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes
    }

def get_forms_service_from_dict(creds_dict: dict):
    """Rebuilds the Google Forms API client service dynamically from stored session credentials."""
    creds = Credentials(**creds_dict)
    return build("forms", "v1", credentials=creds)


# ==========================================
# SCHEMA TO GOOGLE API TRANSLATOR
# ==========================================

def translate_to_google_api(form_data: Form) -> list[dict]:
    """Translates the Pydantic Form object into Google Forms batchUpdate requests."""
    requests = []
    index = 0

    for i, section in enumerate(form_data.sections):
        # 1. Add a Page Break / Section Header if it's not the first section
        if i != 0:
            requests.append({
                "createItem": {
                    "item": {
                        "title": section.title,
                        "description": section.description or "",
                        "pageBreakItem": {}
                    },
                    "location": {"index": index}
                }
            })
            index += 1

        # 2. Iterate through questions in this section
        for q in section.questions:
            item = {
                "title": q.title,
                "questionItem": {
                    "question": {
                        "required": q.required
                    }
                }
            }

            question_payload = item["questionItem"]["question"]

            # Map Question Types
            if q.type == QuestionType.SHORT_TEXT:
                question_payload["textQuestion"] = {"paragraph": False}

            elif q.type == QuestionType.LONG_TEXT:
                question_payload["textQuestion"] = {"paragraph": True}

            elif q.type in [QuestionType.MULTIPLE_CHOICE, QuestionType.CHECKBOXES, QuestionType.DROPDOWN]:
                choices = []
                for opt in (q.options or []):
                    if isinstance(opt, str):
                        choices.append({"value": opt})
                    else:
                        choices.append({"value": getattr(opt, "label", str(opt))})

                if q.type == QuestionType.MULTIPLE_CHOICE:
                    g_type = "RADIO"
                elif q.type == QuestionType.CHECKBOXES:
                    g_type = "CHECKBOX"
                else:
                    g_type = "DROP_DOWN"

                question_payload["choiceQuestion"] = {
                    "type": g_type,
                    "options": choices
                }

            requests.append({
                "createItem": {
                    "item": item,
                    "location": {"index": index}
                }
            })
            index += 1

    return requests


def check_if_form_trashed(form_id: str, creds_dict: dict) -> bool:
    """Checks Google Drive to see if the form is in the bin or permanently deleted."""
    creds = Credentials(**creds_dict)
    
    drive_service = build("drive", "v3", credentials=creds)
    
    try:
        # Requesting ONLY the 'trashed' boolean field to keep the API call blazing fast
        file_meta = drive_service.files().get(fileId=form_id, fields="trashed").execute()
        return file_meta.get("trashed", False)
    except Exception:
        # If we get an HttpError (like a 404 Not Found), the form is permanently deleted
        return True


def get_latest_form_schema(form_id: str, creds_dict: dict) -> str:
    """Fetches the live JSON blueprint of a Google Form."""
    try:
        credentials = Credentials(**creds_dict)
        service = build('forms', 'v1', credentials=credentials)
        
        # Make a simple GET request to grab the live form structure
        form_data = service.forms().get(formId=form_id).execute()
        
        # Return it as a nicely formatted JSON string for the LLM to read
        return json.dumps(form_data, indent=2)
    except Exception as e:
        print(f"Failed to fetch live form: {e}")
        return "{}" # Return empty JSON if it fails so the app doesn't crash