import uuid

from app.database.schemas import Form, Question, QuestionType, Section


def flatten_form(form: Form) -> list[dict]:
    flat_items = []
    for i, section in enumerate(form.sections):
        if not section.item_id:
            section.item_id = uuid.uuid4().hex[:8]
        if i != 0:
            flat_items.append({"type": "page_break", "content": section})
        for q in section.questions:
            if not q.item_id:
                q.item_id = uuid.uuid4().hex[:8]
            flat_items.append({"type": "question", "content": q})
    return flat_items

def generate_patch_requests(old_form: Form, new_form: Form) -> list[dict]:
    requests = []

    # Safely handle descriptions for brand new forms (old_form = None)
    old_desc = getattr(old_form, "description", "") if old_form else ""
    new_desc = getattr(new_form, "description", "") if new_form else ""
    
    if old_desc != new_desc and new_desc:
        requests.append({
            "updateFormInfo": {
                "info": {"description": new_desc},
                "updateMask": "description"
            }
        })

    # --- Quiz Mode Toggle ---
    old_quiz = getattr(old_form, "is_quiz", False) if old_form else False
    new_quiz = getattr(new_form, "is_quiz", False) if new_form else False
    
    # Send the quiz toggle request if the state changed, or if it's a brand new form that is a quiz
    if old_quiz != new_quiz or (not old_form and new_quiz):
        requests.append({
            "updateSettings": {
                "settings": {
                    "quizSettings": {
                        "isQuiz": new_quiz
                    }
                },
                "updateMask": "quizSettings.isQuiz"
            }
        })

    old_flat = flatten_form(old_form) if old_form else []
    new_flat = flatten_form(new_form)

    # 1. WIPE THE SLATE CLEAN
    for i in range(len(old_flat) - 1, -1, -1):
        requests.append({
            "deleteItem": {
                "location": {"index": i}
            }
        })

    # 2. REBUILD PASS (No routing yet!)
    for i, new_item in enumerate(new_flat):
        if new_item["type"] == "question":
            google_item = translate_question_to_google(new_item["content"], section_title_to_id={}, with_routing=False)
        else:
            google_item = translate_section_to_google(new_item["content"])
            
        requests.append({
            "createItem": {
                "item": google_item,
                "location": {"index": i}
            }
        })

    return requests

def generate_routing_requests(form: Form) -> list[dict]:
    requests = []
    section_title_to_id = {}
    for section in form.sections:
        if section.item_id:
            section_title_to_id[section.title.strip().lower()] = section.item_id

    flat_items = flatten_form(form)
    for i, item in enumerate(flat_items):
        if item["type"] == "question":
            q = item["content"]
            has_routing = False
            for opt in (q.options or []):
                action_val = getattr(opt.action, 'value', getattr(opt, 'action', 'continue'))
                if action_val in ["submit", "go_to_section"]:
                    has_routing = True
                    break

            if has_routing and q.item_id:
                google_item = translate_question_to_google(q, section_title_to_id, with_routing=True)
                google_item["itemId"] = q.item_id
                requests.append({
                    "updateItem": {
                        "item": google_item,
                        "location": {"index": i},
                        "updateMask": "questionItem.question.choiceQuestion"
                    }
                })
    return requests

# --- TRANSLATION HELPERS ---

def translate_section_to_google(s: Section) -> dict:
    return {
        "title": s.title,
        "description": s.description or "",
        "pageBreakItem": {}
    }

def translate_question_to_google(q: Question, section_title_to_id: dict, with_routing: bool = False) -> dict:
    item = {
        "title": q.title,
        "questionItem": {"question": {"required": q.required}}
    }
    question_payload = item["questionItem"]["question"]

    # 1. Pre-process choices to build an Auto-Healer map
    choice_objects = []
    label_map = {} # Maps both 'label' and 'value' to the final Google display label
    
    for opt in (q.options or []):
        choice = {}
        if isinstance(opt, dict):
            display_label = opt.get("label", str(opt))
            sys_value = opt.get("value", "")
            action_raw = opt.get("action")
            target_title = opt.get("go_to_section_title")
        else:
            display_label = getattr(opt, "label", str(opt))
            sys_value = getattr(opt, "value", "")
            action_raw = getattr(opt, "action", None)
            target_title = getattr(opt, "go_to_section_title", None)

        # Map both the label and value to the display_label so we can heal LLM mistakes
        label_map[display_label] = display_label
        if sys_value:
            label_map[sys_value] = display_label

        choice["value"] = display_label

        # --- ROUTING LOGIC ---
        if hasattr(action_raw, "value"):
            action_val = action_raw.value
        elif action_raw:
            action_val = str(action_raw)
        else:
            action_val = "continue"
            
        if with_routing and q.type in [QuestionType.MULTIPLE_CHOICE, QuestionType.DROPDOWN]:
            if action_val == "submit":
                choice["goToAction"] = "SUBMIT_FORM"
            elif action_val == "continue":
                choice["goToAction"] = "NEXT_SECTION"
            elif action_val == "go_to_section" and target_title:
                target_id = section_title_to_id.get(target_title.strip().lower())
                if target_id:
                    choice["goToSectionId"] = target_id
        
        choice_objects.append(choice)

    # 2. Inject Quiz Grading with the Auto-Healer
    if getattr(q, 'point_value', 0) > 0:
        grading = {"pointValue": q.point_value}
        if getattr(q, 'correct_answers', None):
            safe_answers = []
            for ans in q.correct_answers:
                # If the LLM sent the system 'value' instead of 'label', this instantly fixes it
                resolved_label = label_map.get(str(ans), str(ans))
                
                # Ensure no duplicates in the answer key
                if {"value": resolved_label} not in safe_answers:
                    safe_answers.append({"value": resolved_label})
                    
            grading["correctAnswers"] = {"answers": safe_answers}
        question_payload["grading"] = grading

    # 3. Finalize Question Type
    if q.type == QuestionType.SHORT_TEXT:
        question_payload["textQuestion"] = {"paragraph": False}
    elif q.type == QuestionType.LONG_TEXT:
        question_payload["textQuestion"] = {"paragraph": True}
    elif q.type in [QuestionType.MULTIPLE_CHOICE, QuestionType.CHECKBOXES, QuestionType.DROPDOWN]:
        if q.type == QuestionType.MULTIPLE_CHOICE:
            g_type = "RADIO"
        elif q.type == QuestionType.CHECKBOXES:
            g_type = "CHECKBOX"
        else:
            g_type = "DROP_DOWN"
            
        question_payload["choiceQuestion"] = {"type": g_type, "options": choice_objects}

    return item