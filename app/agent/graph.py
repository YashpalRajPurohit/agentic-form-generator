# graph.py
import json
import os

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, StateGraph
from psycopg_pool import ConnectionPool
from pydantic import ValidationError

from app.agent.state import AgentState
from app.database.schemas import Form
from app.services.form_utils import get_forms_service_from_dict

# --- LOCAL IMPORTS ---
from app.services.sync_engine import generate_patch_requests, generate_routing_requests

load_dotenv()

# --- DATABASE SETUP ---
DB_URI = os.getenv("DATABASE_URL")

# 1. Define these as None globally so they don't boot up on import
pool = None
checkpointer = None

# --- LLM CONFIG ---
llm = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite", temperature=0.2)


# ==========================================
# GRAPH NODES
# ==========================================

# Node 1: The Drafter
def drafter_node(state: AgentState):
    user_prompt = state["user_prompt"]
    existing_form = state.get("final_form")
    chat_history = state.get("chat_history", [])
    schema_json = Form.model_json_schema()

    print("\n--- DRAFTING FORM ---")

    # MODE 1: PATCH MODE (Editing an existing form)
    if existing_form:
        print("Existing form detected in state. Entering PATCH mode.")
        existing_form_json = existing_form.model_dump_json(indent=2)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", 
                """You are an expert Google Forms architect and state manager. 
                The user wants to edit an existing form. You must modify the CURRENT FORM STATE JSON and output a valid updated JSON payload.

                CRITICAL INSTRUCTIONS:
                1. Output ONLY valid JSON matching the schema without markdown formatting.
                
                BRANCHING & CONDITIONAL LOGIC ("Choose Your Own Adventure"):
                2. If the user requests to skip, branch, or navigate based on answers, use the `action` and `default_action` fields.
                3. If using `go_to_section`, you MUST provide a `go_to_section_title` that EXACTLY matches the target section.
                4. Question-level branching is ONLY permitted on `multiple_choice` and `dropdown` types.
                5. A Section's `default_action` dictates navigation after the section.
                
                QUIZ & GRADING MODE:
                6. If the user asks for a "quiz", "test", "assessment", or mentions "points", set `is_quiz` to true.
                7. For quiz questions, assign a positive integer to `point_value`.
                8. For demographic/feedback questions, set `point_value` to 0.
                9. If `point_value` > 0, provide exact correct string(s) in `correct_answers`.
                
                🛑 TOPIC CHANGE GUARDRAIL 🛑
                10. You are currently editing an existing form. If the user asks to create a completely NEW form on a fundamentally DIFFERENT topic, DO NOT generate a JSON schema. 
                Instead, output a string starting with "GUARDRAIL_TRIGGERED:" followed by a friendly message advising them to click 'New chat'.
                
                🛑 CASUAL CHAT GUARDRAIL (NEW) 🛑
                11. If the user just says a generic greeting (like 'hello', 'hi', 'what's up') or makes conversational small talk completely unrelated to editing the form, DO NOT generate a JSON schema. 
                Instead, output a string starting with "CASUAL_CHAT|" followed by a friendly, brief conversational reply asking what they'd like to update in their form.
                Example: CASUAL_CHAT|Hello! I'm here to help. What would you like to update or change in your form?"""
            ),
            MessagesPlaceholder(variable_name="chat_history"),
            ("user", 
                "Schema definition: {schema}\n\nCURRENT FORM STATE:\n{existing_form_json}\n\nUser edit request: {user_prompt}"
            )
        ])
        
        chain = prompt | llm | StrOutputParser()
        response = chain.invoke({
            "schema": json.dumps(schema_json),
            "existing_form_json": existing_form_json,
            "user_prompt": user_prompt,
            "chat_history": chat_history
        })

    # MODE 2: CREATE MODE (Building a brand new form)
    else:
        print("No existing form found. Entering CREATE mode.")
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", 
                """You are an expert Google Forms architect. 
                Generate a JSON payload for a new form based exactly on the provided schema instructions.

                CRITICAL INSTRUCTIONS:
                1. Output ONLY valid JSON without markdown formatting.
                
                BRANCHING & CONDITIONAL LOGIC:
                2. If the user requests to skip, branch, or navigate based on answers, use the `action` and `default_action` fields.
                3. If using `go_to_section`, you MUST provide a `go_to_section_title` that EXACTLY matches the target section.
                4. Question-level branching is ONLY permitted on `multiple_choice` and `dropdown` types.
                5. A Section's `default_action` dictates navigation after the section.
                
                QUIZ & GRADING MODE:
                6. If the user asks for a "quiz", "test", "assessment", or mentions "points", set `is_quiz` to true.
                7. For quiz questions, assign a positive integer to `point_value`.
                8. For demographic/feedback questions, set `point_value` to 0.
                9. If `point_value` > 0, provide exact correct string(s) in `correct_answers`.
                
                🛑 CASUAL CHAT GUARDRAIL (NEW) 🛑
                10. If the user just says a generic greeting (like 'hello', 'hi', 'what's up') or makes conversational small talk completely unrelated to building a form, DO NOT generate a JSON schema. 
                Instead, output a string starting with "CASUAL_CHAT|" followed by a friendly, brief conversational reply guiding them back to form creation.
                Example: CASUAL_CHAT|Hello! I'm ready to help you build a Google Form. What kind of form would you like to create today?"""
            ),
            MessagesPlaceholder(variable_name="chat_history"),
            ("user", 
                "Schema definition: {schema}\n\nUser request: {user_prompt}"
            )
        ])

        chain = prompt | llm | StrOutputParser()
        response = chain.invoke({
            "schema": json.dumps(schema_json),
            "user_prompt": user_prompt,
            "chat_history": chat_history
        })

    clean_response = response.replace("```json", "").replace("```", "").strip()
    
    # 1. Catch the TOPIC CHANGE guardrail
    if clean_response.startswith("GUARDRAIL_TRIGGERED"):
        parts = clean_response.split(":", 1)
        custom_message = parts[1].strip() if len(parts) > 1 else "💡 It looks like you want to create a brand new form. Please click 'New chat' in the sidebar to avoid overwriting this one!"
        
        return {
            "error_message": f"GUARDRAIL|{custom_message}",
            "draft_payload": existing_form_json if existing_form else "",
            "old_form": existing_form,
            "retries": state.get("retries", 0)
        }
        
    # 2. Catch the CASUAL CHAT guardrail (NEW)
    if clean_response.startswith("CASUAL_CHAT|"):
        custom_chat_message = clean_response.split("|", 1)[1].strip()
        return {
            "error_message": f"CHAT|{custom_chat_message}",
            "draft_payload": existing_form_json if existing_form else "",
            "old_form": existing_form,
            "retries": state.get("retries", 0)
        }

    return {
        "draft_payload": clean_response,
        "old_form": existing_form,
        "retries": state.get("retries", 0)
    }


# Node 2: The Validator
def validator_node(state: AgentState):
    draft = state["draft_payload"]
    old_form = state.get("old_form")  # Grab the previous form version from state

    try: 
        clean_json = draft.replace("```json", "").replace("```", "").strip()
        draft_dict = json.loads(clean_json)

        # Pydantic validation
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


# Node 4: The Create Executor
def executor_node(state: AgentState):
    validated_form = state["final_form"]

    print("\n--- TRANSLATING & EXECUTING ---")
    print("Authenticating with Google OAuth via Web Session...")
    creds_dict = state["user_google_creds"] 
    forms_service = get_forms_service_from_dict(creds_dict)
    
    form_manifest = {
        "info": {
            "title": validated_form.title,
            "documentTitle": f"{validated_form.title} (AI Generated)",
        }
    }

    print("Creating blank form shell...")
    created_form = forms_service.forms().create(body=form_manifest).execute()
    form_id = created_form["formId"]
    
    # Send empty old_form to trigger a pure top-down rebuild
    print("Executing sync operations to build form...")
    requests = generate_patch_requests(None, validated_form)
    
    response = forms_service.forms().batchUpdate(
        formId=form_id,
        body={"requests": requests}
    ).execute()
    
    replies = response.get("replies", [])
    create_replies = [r["createItem"]["itemId"] for r in replies if "createItem" in r]
    
    reply_idx = 0
    for i, section in enumerate(validated_form.sections):
        if i != 0:
            section.item_id = create_replies[reply_idx]
            reply_idx += 1
        else:
            section.item_id = None # CLEAR FAKE UUID TO PREVENT API CRASHES
            
        for q in section.questions:
            q.item_id = create_replies[reply_idx]
            reply_idx += 1

    print("Checking for branching and routing rules...")
    routing_requests = generate_routing_requests(validated_form)
    
    if routing_requests:
        print(f"Applying {len(routing_requests)} routing rules...")
        forms_service.forms().batchUpdate(
            formId=form_id,
            body={"requests": routing_requests}
        ).execute()

    warnings = []
    for section in validated_form.sections[:-1]:
        action_val = section.default_action.value if hasattr(section.default_action, 'value') else section.default_action
        if action_val == "submit":
            warnings.append(f"'{section.title}'")

    if warnings:
        sections_str = ", ".join(warnings)
        print(f"\n⚠️ MANUAL ACTION REQUIRED: Google Forms API does not support programmatic section-level submits.")
        print(f"Please open the form and manually set the dropdown at the bottom of {sections_str} to 'Submit form'.\n")

    print("\n=========================================")
    print("✅ SUCCESS! FORM COMPLETELY GENERATED")
    print(f"Live URL: {created_form['responderUri']}")
    print("=========================================\n")

    return {
        "final_form": validated_form,
        "google_form_id": form_id
    }

# Node 5: The Patch Executor
def patch_executor_node(state: AgentState):
    old_form = state["old_form"]
    new_form = state["final_form"]
    form_id = state["google_form_id"]

    print("\n--- SYNCHRONIZING FORM STATE ---")
    requests = generate_patch_requests(old_form, new_form)
    
    if not requests:
        return state

    print(f"Executing {len(requests)} sync operations in 1 batch update...")

    creds_dict = state["user_google_creds"] 
    forms_service = get_forms_service_from_dict(creds_dict)
    
    response = forms_service.forms().batchUpdate(
        formId=form_id,
        body={"requests": requests}
    ).execute()
    
    replies = response.get("replies", [])
    create_replies = [r["createItem"]["itemId"] for r in replies if "createItem" in r]
    
    reply_idx = 0
    for i, section in enumerate(new_form.sections):
        if i != 0:
            section.item_id = create_replies[reply_idx]
            reply_idx += 1
        else:
            section.item_id = None # CLEAR FAKE UUID TO PREVENT API CRASHES
            
        for q in section.questions:
            q.item_id = create_replies[reply_idx]
            reply_idx += 1

    print("Checking for branching and routing rules...")
    routing_requests = generate_routing_requests(new_form)
    
    if routing_requests:
        print(f"Applying {len(routing_requests)} routing rules...")
        forms_service.forms().batchUpdate(
            formId=form_id,
            body={"requests": routing_requests}
        ).execute()

    warnings = []
    for section in new_form.sections[:-1]:
        action_val = section.default_action.value if hasattr(section.default_action, 'value') else section.default_action
        if action_val == "submit":
            warnings.append(f"'{section.title}'")

    if warnings:
        sections_str = ", ".join(warnings)
        print(f"\n⚠️ MANUAL ACTION REQUIRED: Google Forms API does not support programmatic section-level submits.")
        print(f"Please open the form and manually set the dropdown at the bottom of {sections_str} to 'Submit form'.\n")

    print("✅ SUCCESS! FORM SYNCHRONIZED PERFECTLY.")
    return {"final_form": new_form}

# ==========================================
# GRAPH ROUTING & COMPILATION
# ==========================================

def route_validation(state: AgentState):
    if state["retries"] >= 3:
        return "end_failure"
    if state.get("error_message"):
        return "corrector"
    return "execution"


def build_form_graph():
    global pool, checkpointer
    
    # 2. Initialize the connection pool ONLY when the worker process calls this function
    if pool is None:
        pool = ConnectionPool(
            conninfo=DB_URI, 
            max_size=10, 
            max_idle=120, 
            kwargs={"autocommit": True}
        )
        checkpointer = PostgresSaver(pool)
        checkpointer.setup()

    workflow = StateGraph(AgentState)

    workflow.add_node("drafter", drafter_node)
    workflow.add_node("validator", validator_node)
    workflow.add_node("corrector", corrector_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("patch_executor", patch_executor_node)

    workflow.set_entry_point("drafter")
    workflow.add_edge("drafter", "validator")

    # Smart Routing Wrapper
    def advanced_routing(state: AgentState):
        base_decision = route_validation(state)
        
        if base_decision != "execution":
            return base_decision
            
        if state.get("google_form_id"):
            return "patch_executor"
        else:
            return "executor"

    workflow.add_conditional_edges(
        "validator",
        advanced_routing,
        {
            "corrector": "corrector",
            "executor": "executor",
            "patch_executor": "patch_executor",
            "end_failure": END
        }
    )

    workflow.add_edge("corrector", "validator")
    workflow.add_edge("executor", END)
    workflow.add_edge("patch_executor", END)
    
    return workflow.compile(checkpointer=checkpointer)