"""Filing request and result models."""
from pydantic import BaseModel, Field
from typing import Optional


class FilingRequest(BaseModel):
    """Request to execute a filing."""
    filing_code: str
    entity_name: str
    entity_number: Optional[str] = None
    entity_type: str = "corporation"
    state_of_formation: str = ""

    principal_address: dict = Field(default_factory=dict)
    mailing_address: Optional[dict] = None
    officers: list[dict] = Field(default_factory=list)
    business_data: dict = Field(default_factory=dict)
    registered_agent: Optional[dict] = None

    portal_username: Optional[str] = None
    portal_password: Optional[str] = None
    portal_extra: dict = Field(default_factory=dict)

    payment_tier: str = "customer_pays"
    headless: bool = False
    screenshots_dir: str = "./screenshots"
    output_file: Optional[str] = None


class FilingResultModel(BaseModel):
    """Result of a completed filing."""
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    total_steps: int = 0
    completed_steps: int = 0
    confirmation_number: Optional[str] = None
    error_message: Optional[str] = None
    screenshots: list[str] = Field(default_factory=list)
