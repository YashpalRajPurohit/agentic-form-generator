import os 
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from schemas import Form, QuestionType

SCOPES = [
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/drive"
]

def authenticate_user():
    creds = None
    # The file token.json stores the user's access and refresh tokens.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'oauth_client_credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
    return creds

def translate_to_google_api(form_data: Form) -> list[dict]:
    """Translates the Pydantic Form object into Google Forms batchUpdate requests."""
    requests = []
    index = 0  # Google requires us to specify the exact index where each item is placed
    
    for i, section in enumerate(form_data.sections):
        # 1. Add a Text Item to act as the Section Header ONLY if it's not the first section
        if i != 0:
            requests.append({
                "createItem": {
                    "item": {
                        "title": section.title,
                        "description": section.description or "",
                        "pageBreakItem": {}  # A read-only text block in the form
                    },
                    "location": {"index": index}
                }
            })
            index += 1

        # 2. Iterate through the questions in this section
        for q in section.questions:
            # Build the base question item
            item = {
                "title": q.title,
                "questionItem": {
                    "question": {
                        "required": q.required
                    }
                }
            }
            
            # Create a pointer to the nested question payload for easier assignment
            question_payload = item["questionItem"]["question"]

            # 3. Map our Enums to Google's specific payload structures
            if q.type == QuestionType.SHORT_TEXT:
                question_payload["textQuestion"] = {"paragraph": False}
                
            elif q.type == QuestionType.LONG_TEXT:
                question_payload["textQuestion"] = {"paragraph": True}
                
            elif q.type in [QuestionType.MULTIPLE_CHOICE, QuestionType.CHECKBOXES, QuestionType.DROPDOWN]:
                choices = [{"value": opt} if isinstance(opt, str) else {"value": getattr(opt, 'label', str(opt))} for opt in (q.options or [])]
                
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

            # 4. Wrap the built item in the createItem command and add to the list
            requests.append({
                "createItem": {
                    "item": item,
                    "location": {"index": index}
                }
            })
            index += 1
            
    return requests


# def test_google_apis():
#     print("Starting authentication flow...")
#     creds = authenticate_user()

#     # Build the Forms servic
#     forms_service = build('forms', 'v1', credentials=creds)

#     form_manifest = {
#             "info": {
#                 "title": "API Connection Test",
#                 "documentTitle": "Prototype Blank Form"
#             }
#         }
        
#     print("Creating form in your Google Drive...")
#     result = forms_service.forms().create(body=form_manifest).execute()
#     form_id = result["formId"]

#     print(f"Success! Form ID: {form_id}")
#     print(f"\n\nresult info: {result}\n\n")
#     print(f"Live Form URL (to fill out): {result['responderUri']}")
#     print("Check your personal Google Drive—the form is already there!")

# if __name__ == "__main__":
#     test_google_apis()