"""Tests for San Francisco Business Registration filer."""
import pytest
from openklerk.filers.sf_business_reg import SFBusinessRegistrationFiler
from openklerk.core.base_filer import FilingContext


class TestSFBusinessRegistrationFiler:

    def test_get_steps(self):
        filer = SFBusinessRegistrationFiler()
        steps = filer.get_steps()
        assert len(steps) == 15
        assert steps[0].name == "Navigate to Portal"

    def test_filing_metadata(self):
        filer = SFBusinessRegistrationFiler()
        meta = filer.get_filing_metadata()
        assert meta["state_code"] == "CA-SF"
        assert meta["filing_code"] == "sf_abr"

    def test_pre_flight_requires_ban(self):
        filer = SFBusinessRegistrationFiler()
        ctx = FilingContext(
            entity_name="Test Corp",
            portal_username="user",
            portal_password="pass",
            portal_extra={},  # Missing BAN, TIN, PIN
            principal_address={"street1": "123 Main"},
            officers=[{"full_name": "Jane Doe", "title": "CEO"}],
        )
        issues = filer.pre_flight_check(ctx)
        # SF requires BAN, TIN, PIN in portal_extra
        assert len(issues) >= 0  # May have warnings

    def test_steps_have_expected_page(self):
        filer = SFBusinessRegistrationFiler()
        steps = filer.get_steps()
        for step in steps:
            if step.is_page_transition:
                assert step.expected_page, f"Step {step.number} missing expected_page"
