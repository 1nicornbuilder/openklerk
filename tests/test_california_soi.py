"""Tests for California SOI filer."""
import pytest
from openklerk.filers.california_soi import CaliforniaSOIFiler
from openklerk.core.base_filer import FilingContext


class TestCaliforniaSOIFiler:

    def test_get_steps(self):
        filer = CaliforniaSOIFiler()
        steps = filer.get_steps()
        assert len(steps) == 16
        assert steps[0].number == 1
        assert steps[0].name == "Navigate to Portal"

    def test_filing_metadata(self):
        filer = CaliforniaSOIFiler()
        meta = filer.get_filing_metadata()
        assert meta["state_code"] == "CA"
        assert meta["filing_code"] == "ca_soi"
        assert meta["filing_name"] == "Statement of Information"
        assert "bizfileonline" in meta["portal_url"]
        assert meta["total_steps"] == 16

    def test_pre_flight_check_missing_name(self):
        filer = CaliforniaSOIFiler()
        ctx = FilingContext(entity_name="")
        issues = filer.pre_flight_check(ctx)
        assert any("entity name" in i.lower() for i in issues)

    def test_pre_flight_check_missing_entity_number(self):
        filer = CaliforniaSOIFiler()
        ctx = FilingContext(
            entity_name="Test Corp",
            portal_username="user",
            portal_password="pass",
            principal_address={"street1": "123 Main", "city": "LA", "state": "CA", "zip": "90001"},
            officers=[{"full_name": "Jane Doe", "title": "CEO", "is_signer": True}],
        )
        issues = filer.pre_flight_check(ctx)
        assert any("entity number" in i.lower() for i in issues)

    def test_pre_flight_check_valid(self):
        filer = CaliforniaSOIFiler()
        ctx = FilingContext(
            entity_name="Test Corp",
            entity_number="C1234567",
            portal_username="user",
            portal_password="pass",
            principal_address={"street1": "123 Main", "city": "LA", "state": "CA", "zip": "90001"},
            officers=[{"full_name": "Jane Doe", "title": "CEO", "is_signer": True}],
        )
        issues = filer.pre_flight_check(ctx)
        fatal = [i for i in issues if "entity name" in i.lower()]
        assert len(fatal) == 0

    def test_steps_have_page_transitions(self):
        filer = CaliforniaSOIFiler()
        steps = filer.get_steps()
        transition_steps = [s for s in steps if s.is_page_transition]
        assert len(transition_steps) > 0

    def test_payment_step_marked(self):
        filer = CaliforniaSOIFiler()
        steps = filer.get_steps()
        payment_steps = [s for s in steps if s.is_payment_step]
        assert len(payment_steps) >= 1
