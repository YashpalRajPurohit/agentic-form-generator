from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class QuestionType(str, Enum):
    SHORT_TEXT = "short_text"
    LONG_TEXT = "long_text"
    MULTIPLE_CHOICE = "multiple_choice"
    CHECKBOXES = "checkboxes"
    DROPDOWN = "dropdown"

class OptionAction(str, Enum):
    CONTINUE = "continue"
    SUBMIT = "submit"
    GO_TO_SECTION = "go_to_section"

class Option(BaseModel):
    label: str = Field(..., description="The display text shown to the user (e.g., 'Yes').")
    value: str = Field(..., description="The underlying system value (e.g., 'yes_val').")

    action: Optional[OptionAction] = Field(
        default=OptionAction.CONTINUE, 
        description="The navigation action to take if this option is selected."
    )
    go_to_section_title: Optional[str] = Field(
        default=None, 
        description="Required ONLY if action is 'go_to_section'. Must EXACTLY match the title of the target Section."
    )

class Question(BaseModel):
    item_id: Optional[str] = Field(default=None, description="Google's internal ID for this item. Do not generate this.")
    title: str = Field(..., description="The actual question text asked to the user.")
    type: QuestionType = Field(..., description="The UI component type for the question being asked.")
    required: bool = Field(default=False, decription="Whether the user must answer this question.")
    options: list[Option] | None = Field(default=None, description="Required only if type is multiple_choice, checkboxes, or dropdown.")

    point_value: int = Field(
        default=0, 
        description="The number of points this question is worth. Use 0 if it is not a graded question."
    )
    correct_answers: Optional[list[str]] = Field(
        default=None, 
        description="A list of the exact string values of the correct options. Required if point_value > 0."
    )

class SectionAction(str, Enum):
    CONTINUE = "continue"
    SUBMIT = "submit"
    GO_TO_SECTION = "go_to_section"

class Section(BaseModel):
    title: str = Field(..., description="The title of this section of the form.")
    description: Optional[str] = Field(default=None, description="Optional context or instructions for this section.")
    questions: list[Question] = Field(..., description="The list of questions contained in this section.")
    item_id: Optional[str] = Field(default=None, description="Google's internal ID for this section. Do not generate this.")
    
    default_action: Optional[SectionAction] = Field(
        default=SectionAction.CONTINUE, 
        description="The default navigation action after the user completes this section."
    )
    go_to_section_title: Optional[str] = Field(
        default=None, 
        description="Required ONLY if default_action is 'go_to_section'. Must EXACTLY match the title of the target Section."
    )

class Form(BaseModel):
    title: str = Field(..., description="The main, overarching title of the form.")
    description: str | None = Field(default=None, description="General instructions for the whole form.")
    sections: list[Section] = Field(..., description="The sections that make up the complete form.")

    is_quiz: bool = Field(
        default=False, 
        description="Set to True ONLY if the user explicitly asks for a quiz, test, assessment, or graded form."
    )