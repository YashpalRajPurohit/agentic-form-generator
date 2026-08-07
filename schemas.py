from enum import Enum

from pydantic import BaseModel, Field


class QuestionType(str, Enum):
    SHORT_TEXT = "short_text"
    LONG_TEXT = "long_text"
    MULTIPLE_CHOICE = "multiple_choice"
    CHECKBOXES = "checkboxes"
    DROPDOWN = "dropdown"

class Option(BaseModel):
    label: str = Field(..., description="The display text shown to the user (e.g., 'Yes').")
    value: str = Field(..., description="The underlying system value (e.g., 'yes_val').")

class Question(BaseModel):
    id: str = Field(..., description="A unique machine-readable identifier for the question.")
    title: str = Field(..., description="The actual question text asked to the user.")
    type: QuestionType = Field(..., description="The UI component type for the question being asked.")
    required: bool = Field(default=False, decription="Whether the user must answer this question.")
    options: list[Option] | None = Field(default=None, description="Required only if type is multiple_choice, checkboxes, or dropdown.")

class Section(BaseModel):
    title: str = Field(..., description="The title of this section of the form.")
    description: str | None = Field(default=None, description="Optional context or instructions for this section.")
    questions: list[Question] = Field(..., description="The list of questions contained in this section.")

class Form(BaseModel):
    title: str = Field(..., description="The main, overarching title of the form.")
    description: str | None = Field(default=None, description="General instructions for the whole form.")
    sections: list[Section] = Field(..., description="The sections that make up the complete form.")
    