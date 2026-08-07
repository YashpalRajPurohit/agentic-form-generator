import json
import os
from typing import Optional, TypedDict

from dotenv import load_dotenv

load_dotenv()

from googleapiclient.discovery import build
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph
from pydantic import ValidationError

from form_utils import authenticate_user, translate_to_google_api
from schemas import Form


class AgentState(TypedDict):
    user_prompt: str
    draft_payload: str
    final_form: Optional[Form]
    error_message: Optional[str]
    retries: int


# Node 1: The Drafter
llm = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite", temperature=0.2)

def drafter_node(state: AgentState):
    prompt = ChatPromptTemplate.from_messages([
        ("system", 
            """Your are an expert form architect. 
            Generate a JSON payload for a form based exactly on the provided schema instructions.
            Output ONLY valid JSON without markdown formatting."""
        ),
        ("user", 
            "Schema definition: {schema}\n\nUser request: {user_prompt}"
        )
        ])

    schema_json = Form.model_json_schema()

    chain = prompt | llm | StrOutputParser()
    response = chain.invoke({
        "schema": json.dumps(schema_json),
        "user_prompt": state["user_prompt"]
    })

    return {
        "draft_payload": response,
        "retries": state.get("retries", 0)
    }

# Node 2: The Validator (The Bouncer)
def validator_node(state: AgentState):
    draft = state["draft_payload"]

    try: 
        clean_json = draft.replace("```json", "").replace("```", "").strip()
        draft_dict = json.loads(clean_json)

        # Pydantic validation happens right here
        parsed_form = Form(**draft_dict)

        return {"final_form": parsed_form, "error_message": None}

    except (json.JSONDecodeError, ValidationError) as e:
        return {"error_message": str(e)}

# Node 3: The Corrector
def corrector_node(state: AgentState):
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a JSON debugging assistant. You previously generated a JSON payload that failed validation. Fix the JSON so it perfectly matches the schema requirements. Output ONLY valid JSON."),
        ("user", "Original request: {user_prompt}\n\nFailed JSON: {failed_json}\n\nValidation Error: {error_message}\n\nSchema: {schema}")
    ])

    schema_json = Form.model_json_schema()

    chain = prompt | llm | StrOutputParser()
    response = chain.invoke({
        "user_prompt": state["user_prompt"],
        "failed_json": state["draft_payload"],
        "error_message": state["error_message"],
        "schema": json.dumps(schema_json)
    })

    return {
        "draft_payload": response,
        "retries": state["retries"] + 1
    }


# The Conditonal Edge (The Router)
def route_validation(state: AgentState):
    if state["retries"] >= 3:
        return "end_failure"

    # If Pydantic caught an error, route to the corrector
    if state.get("error_message"):
        return "corrector"

    # If the error message is None, the schema perfectly matched!
    return "execution"


# Compile the Graph
def build_form_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("drafter", drafter_node)
    workflow.add_node("validator", validator_node)
    workflow.add_node("corrector", corrector_node)
    workflow.add_node("executor", executor_node)

    workflow.set_entry_point("drafter")
    workflow.add_edge("drafter", "validator")

    workflow.add_conditional_edges(
        "validator",
        route_validation,
        {
            "corrector": "corrector",
            "execution": "executor",
            "end_failure": END
        }
    )

    workflow.add_edge("corrector", "validator")
    workflow.add_edge("executor", END)

    return workflow.compile()


def executor_node(state: AgentState):
    validated_form = state["final_form"]

    print("\n--- TRANSLATING & EXECUTING ---")
    print("Translating Pydantic schema to Google API format...")
    google_requests = translate_to_google_api(validated_form)

    if validated_form.description:
        google_requests.insert(0, {
            "updateFormInfo": {
                "info": {
                    "description": validated_form.description
                },
                "updateMask": "description" # Tells Google exactly which field to overwrite
            }
        })

    print("Authenticating with Google OAuth...")
    creds = authenticate_user()
    forms_service = build("forms", "v1", credentials=creds)
    
    # Step A: Create the blank form shell using the AI's generated title
    form_manifest = {
        "info": {
            "title": validated_form.title,
            "documentTitle": f"{validated_form.title} (AI Generated)",
        }
    }

    print("Creating blank form shell...")
    created_form = forms_service.forms().create(body=form_manifest).execute()
    form_id = created_form["formId"]
    
    # Step B: Inject all the translated questions using batchUpdate
    print(f"Injecting {len(google_requests)} items via batchUpdate...")
    forms_service.forms().batchUpdate(
        formId=form_id,
        body={"requests": google_requests}
    ).execute()
    
    print("\n=========================================")
    print("✅ SUCCESS! FORM COMPLETELY GENERATED")
    print(f"Live URL: {created_form['responderUri']}")
    print("=========================================\n")
    
    return state


