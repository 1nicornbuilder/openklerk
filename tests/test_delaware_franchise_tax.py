"""Tests for Delaware Franchise Tax filer."""
import pytest
from openklerk.filers.delaware_franchise_tax import DelawareFranchiseTaxFiler
from openklerk.core.base_filer import FilingContext


class TestDelawareFranchiseTaxFiler:

    def test_get_steps(self):
        filer = DelawareFranchiseTaxFiler()
        steps = filer.get_steps()
        assert len(steps) == 6
        assert steps[0].name == "Navigate to Portal"

    def test_filing_metadata(self):
        filer = DelawareFranchiseTaxFiler()
        meta = filer.get_filing_metadata()
        assert meta["state_code"] == "DE"
        assert meta["filing_code"] == "de_franchise_tax"

    def test_pre_flight_requires_entity_number(self):
        filer = DelawareFranchiseTaxFiler()
        ctx = FilingContext(
            entity_name="Test Corp",
            entity_type="corporation",
            principal_address={"street1": "123 Main"},
            officers=[
                {"full_name": "A", "title": "President"},
                {"full_name": "B", "title": "Secretary"},
                {"full_name": "C", "title": "Treasurer"},
            ],
            business_data={"authorized_shares": "10000"},
        )
        issues = filer.pre_flight_check(ctx)
        assert any("file number" in i.lower() or "entity number" in i.lower() for i in issues)

    def test_pre_flight_requires_officers(self):
        filer = DelawareFranchiseTaxFiler()
        ctx = FilingContext(
            entity_name="Test Corp",
            entity_number="1234567",
            entity_type="corporation",
            officers=[],
            business_data={"authorized_shares": "10000"},
        )
        issues = filer.pre_flight_check(ctx)
        assert any("president" in i.lower() or "officer" in i.lower() for i in issues)

    def test_payment_step_marked(self):
        filer = DelawareFranchiseTaxFiler()
        steps = filer.get_steps()
        payment_steps = [s for s in steps if s.is_payment_step]
        assert len(payment_steps) >= 1
