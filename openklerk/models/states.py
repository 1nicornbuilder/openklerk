"""State configuration models."""
from pydantic import BaseModel
from typing import Optional


class StateConfig(BaseModel):
    """Configuration for a supported state/jurisdiction."""
    code: str
    name: str
    filing_types: list[str]
    portal_url: str
    captcha: bool = False
    notes: Optional[str] = None


SUPPORTED_STATES: list[StateConfig] = [
    StateConfig(
        code="CA",
        name="California",
        filing_types=["Statement of Information"],
        portal_url="https://bizfileonline.sos.ca.gov",
        captcha=False,
        notes="Corps and LLCs. React SPA portal.",
    ),
    StateConfig(
        code="DE",
        name="Delaware",
        filing_types=["Annual Franchise Tax Report"],
        portal_url="https://icis.corp.delaware.gov",
        captcha=True,
        notes="Corps only. CAPTCHA requires user input.",
    ),
    StateConfig(
        code="CA-SF",
        name="San Francisco",
        filing_types=["Annual Business Registration"],
        portal_url="https://etaxstatement.sfgov.org",
        captcha=False,
        notes="City-level filing. 3-part login (BAN + TIN + PIN).",
    ),
]
