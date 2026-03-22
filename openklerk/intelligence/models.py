"""
OpenKlerk Data Models -- Pydantic models for LLM integration.
"""
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class Recommendation(str, Enum):
    PROCEED = "proceed"
    RETRY = "retry"
    ASK_USER = "ask_user"
    TRANSFER_CONTROL = "transfer_control"
    FAIL = "fail"


class MessageType(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    QUESTION = "question"


class UserAction(str, Enum):
    PROCEED_WITH_INFO = "proceed_with_info"
    TRANSFER_CONTROL = "transfer_control"
    ACKNOWLEDGE = "acknowledge"
    ASK_CLARIFICATION = "ask_clarification"


class PageAnalysisContext(BaseModel):
    """Everything OpenKlerk needs to understand the current situation."""
    filing_type: str
    entity_name: str
    portal_name: str
    state_code: str

    current_step_number: int
    current_step_name: str
    current_step_description: str
    total_steps: int
    expected_page_description: str = ""

    entity_data_summary: dict = Field(default_factory=dict)
    officers_summary: list[str] = Field(default_factory=list)

    previous_steps_completed: list[str] = Field(default_factory=list)
    previous_analysis: Optional[str] = None

    error_message: Optional[str] = None
    error_type: Optional[str] = None
    retry_count: int = 0


class PageAnalysisResult(BaseModel):
    """OpenKlerk's decision after analyzing a page."""
    page_matches_expected: bool = True
    page_description: str = ""
    recommendation: str = "proceed"
    user_message: str = ""
    user_message_type: str = "info"
    user_question: Optional[str] = None
    user_options: Optional[list[str]] = None
    allows_text_input: bool = False
    transfer_reason: Optional[str] = None
    transfer_instructions: Optional[str] = None
    reasoning: str = ""
    confidence: float = 0.9

    def validate_recommendation(self) -> "PageAnalysisResult":
        """Clamp recommendation to valid values."""
        valid = {"proceed", "retry", "ask_user", "transfer_control", "fail"}
        if self.recommendation not in valid:
            self.recommendation = "ask_user"
        return self


class ExceptionAnalysisResult(BaseModel):
    """OpenKlerk's diagnosis after a step exception."""
    diagnosis: str = ""
    recommendation: str = "retry"
    user_message: str = ""
    user_message_type: str = "warning"
    user_question: Optional[str] = None
    user_options: Optional[list[str]] = None
    allows_text_input: bool = False
    transfer_reason: Optional[str] = None
    transfer_instructions: Optional[str] = None
    reasoning: str = ""
    confidence: float = 0.5


class UserResponseResult(BaseModel):
    """OpenKlerk's interpretation of a user message."""
    understood: bool = True
    action: str = "acknowledge"
    info_extracted: dict = Field(default_factory=dict)
    user_message: str = ""
    user_message_type: str = "info"
    user_question: Optional[str] = None
    user_options: Optional[list[str]] = None
    allows_text_input: bool = False
    reasoning: str = ""


class AuditIssue(BaseModel):
    """A single issue found by the adversarial audit."""
    severity: str = "warning"
    page_number: Optional[int] = None
    field: str = ""
    expected: str = ""
    found: str = ""
    description: str = ""


class AuditResult(BaseModel):
    """Result of the pre-payment adversarial audit."""
    audit_passed: bool = False
    confidence: float = 0.0
    issues: list[AuditIssue] = Field(default_factory=list)
    summary: str = ""
    recommendation: str = "manual_review"
