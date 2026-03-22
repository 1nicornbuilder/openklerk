"""
BaseStateFiler -- Abstract base class for all state filing modules.

Every state module (CaliforniaSOIFiler, DelawareAnnualFiler, etc.) inherits from this
and implements the abstract methods. The orchestrator calls these methods in sequence.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any
from datetime import datetime


@dataclass
class FilingStep:
    """Represents a single step in the filing workflow."""
    number: int
    name: str
    description: str
    status: str = "pending"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    screenshot_url: Optional[str] = None
    error_message: Optional[str] = None
    requires_user_input: bool = False
    requires_payment: bool = False
    is_payment_step: bool = False
    input_prompt: Optional[str] = None
    input_response: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    is_page_transition: bool = True
    expected_page: str = ""


@dataclass
class FilingContext:
    """
    All the data the filer needs to execute a filing.
    In standalone mode, populated from a JSON config file.
    """
    filing_id: int = 0
    filing_result_id: int = 0
    filing_code: str = ""

    # Entity data
    entity_name: str = ""
    entity_number: Optional[str] = None
    entity_type: str = ""
    state_of_formation: str = ""
    formation_date: Optional[str] = None
    ein: Optional[str] = None
    principal_address: dict = field(default_factory=dict)
    mailing_address: Optional[dict] = None
    sic_code: Optional[str] = None
    naics_code: Optional[str] = None
    business_description: Optional[str] = None
    fiscal_year_end_month: Optional[int] = None
    registered_agent: Optional[dict] = None

    # Officers (list of dicts)
    officers: list[dict] = field(default_factory=list)

    # Business-specific financial data
    business_data: dict = field(default_factory=dict)

    # Portal credentials
    portal_username: Optional[str] = None
    portal_password: Optional[str] = None
    portal_extra: dict = field(default_factory=dict)
    portal_url: Optional[str] = None
    otp_method: Optional[str] = None
    otp_email: Optional[str] = None

    # Payment info
    payment_tier: str = "customer_pays"
    draft_save_available: bool = False

    # Runtime state
    browser_session_id: Optional[str] = None
    screenshots_dir: Optional[str] = None


class BaseStateFiler(ABC):
    """
    Abstract base class for state filing modules.

    Subclasses MUST implement:
    - get_steps() -> list[FilingStep]
    - execute_step(step_number, context, browser) -> FilingStep

    Subclasses MAY override:
    - pre_flight_check(context) -> list[str]
    - handle_otp(context, browser) -> str
    - handle_captcha(context, browser) -> bool
    """

    STATE_CODE: str = ""
    STATE_NAME: str = ""
    FILING_CODE: str = ""
    FILING_NAME: str = ""
    PORTAL_URL: str = ""
    TOTAL_STEPS: int = 0

    @abstractmethod
    def get_steps(self) -> list[FilingStep]:
        """Return the ordered list of steps for this filing."""
        pass

    @abstractmethod
    async def execute_step(
        self,
        step_number: int,
        context: FilingContext,
        browser: Any,
    ) -> FilingStep:
        """Execute a single step of the filing workflow."""
        pass

    def pre_flight_check(self, context: FilingContext) -> list[str]:
        """
        Validate that all required data is present before starting.
        Returns a list of issues. Empty list = all good.
        """
        issues = []
        if not context.entity_name:
            issues.append("Entity name is required")
        if context.payment_tier != "we_handle":
            if not context.portal_username:
                issues.append(f"Portal username required for {self.STATE_NAME}")
            if not context.portal_password:
                issues.append(f"Portal password required for {self.STATE_NAME}")
        if not context.principal_address:
            issues.append("Principal address is required")
        if not context.officers:
            issues.append("At least one officer is required")
        return issues

    async def handle_otp(self, context: FilingContext, browser: Any) -> Optional[str]:
        """Handle OTP/2FA during portal login."""
        return None

    async def handle_captcha(self, context: FilingContext, browser: Any) -> bool:
        """Handle CAPTCHA if encountered."""
        return False

    def get_filing_metadata(self) -> dict:
        """Return metadata about this filer for logging/display."""
        return {
            "state_code": self.STATE_CODE,
            "state_name": self.STATE_NAME,
            "filing_code": self.FILING_CODE,
            "filing_name": self.FILING_NAME,
            "portal_url": self.PORTAL_URL,
            "total_steps": self.TOTAL_STEPS,
        }
