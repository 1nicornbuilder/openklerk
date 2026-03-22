"""Business entity data models."""
from pydantic import BaseModel, Field
from typing import Optional


class Address(BaseModel):
    """Physical address."""
    street1: str = ""
    street2: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""
    country: str = "US"


class Officer(BaseModel):
    """Corporate officer or director."""
    full_name: str
    title: str = ""
    email: str = ""
    phone: str = ""
    address: Optional[Address] = None
    is_signer: bool = False


class BusinessEntity(BaseModel):
    """Complete business entity profile for filing."""
    entity_name: str
    entity_number: Optional[str] = None
    entity_type: str = "corporation"
    state_of_formation: str = ""
    formation_date: Optional[str] = None
    ein: Optional[str] = None

    principal_address: Optional[Address] = None
    mailing_address: Optional[Address] = None
    registered_agent: Optional[dict] = None

    officers: list[Officer] = Field(default_factory=list)

    sic_code: Optional[str] = None
    naics_code: Optional[str] = None
    business_description: Optional[str] = None
    fiscal_year_end_month: Optional[int] = None

    business_data: dict = Field(default_factory=dict)

    portal_username: Optional[str] = None
    portal_password: Optional[str] = None
    portal_extra: dict = Field(default_factory=dict)
