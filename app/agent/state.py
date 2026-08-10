from typing import Optional, TypedDict

from app.database.schemas import Form


class AgentState(TypedDict):
    user_prompt: str
    draft_payload: str
    final_form: Optional[Form]
    old_form: Optional[Form]  # Stores the previous version for diffing
    google_form_id: Optional[str]
    error_message: Optional[str]
    retries: int

    user_google_creds: Optional[dict]