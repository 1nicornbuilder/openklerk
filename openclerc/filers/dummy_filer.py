"""
DummyStateFiler — Simulates a 10-step filing for testing.

Steps simulate realistic timing and behavior:
- Navigates to a fake URL
- "Logs in" (2 second delay)
- "Fills" 5 form pages (1-3 second delays each)
- Reaches "payment" step (triggers payment handoff if payment_tier = customer_pays)
- "Confirms" submission
- "Downloads receipt"

Register with: register_filer("dummy_test", DummyStateFiler)
"""
import asyncio
import random
from openclerc.core.base_filer import BaseStateFiler, FilingContext, FilingStep
from openclerc.filers import register_filer


class DummyStateFiler(BaseStateFiler):

    STATE_CODE = "XX"
    STATE_NAME = "Test State"
    FILING_CODE = "dummy_test"
    FILING_NAME = "Dummy Test Filing"
    PORTAL_URL = "https://example.com/filing-portal"
    TOTAL_STEPS = 10

    def get_steps(self) -> list[FilingStep]:
        return [
            FilingStep(1, "Navigate to Portal", "Opening the state filing portal"),
            FilingStep(2, "Log In", "Entering portal credentials"),
            FilingStep(3, "Select Filing Type", "Choosing Statement of Information"),
            FilingStep(4, "Fill Entity Info", "Entering business name and entity number"),
            FilingStep(5, "Fill Address Page", "Entering principal and mailing addresses"),
            FilingStep(6, "Fill Officers Page", "Entering officer information"),
            FilingStep(7, "Fill Agent Page", "Entering registered agent details"),
            FilingStep(8, "Review & Sign", "Reviewing all information and signing"),
            FilingStep(
                9, "Payment", "Processing payment",
                requires_payment=True, is_payment_step=True,
            ),
            FilingStep(10, "Download Receipt", "Downloading confirmation and receipt"),
        ]

    async def execute_step(
        self,
        step_number: int,
        context: FilingContext,
        browser,  # BrowserEngine, but we don't use it for dummy
    ) -> FilingStep:
        steps = self.get_steps()
        if step_number < 1 or step_number > len(steps):
            raise ValueError(f"Invalid step_number {step_number}: must be 1-{len(steps)}")
        step = steps[step_number - 1]

        if step_number == 1:
            # Navigate — open a test page
            await browser.navigate("https://example.com")
            await asyncio.sleep(random.uniform(1.0, 2.0))
            step.metadata = {"url": "https://example.com"}

        elif step_number == 2:
            # Login simulation
            await asyncio.sleep(random.uniform(1.5, 2.5))
            step.metadata = {"logged_in": True, "username": context.portal_username or "test_user"}

        elif step_number in (3, 4, 5, 6, 7):
            # Form filling simulation
            await asyncio.sleep(random.uniform(1.0, 3.0))
            step.metadata = {
                "page": f"page_{step_number - 2}",
                "fields_filled": random.randint(3, 8),
            }

        elif step_number == 8:
            # Review & sign
            await asyncio.sleep(random.uniform(1.0, 2.0))
            step.metadata = {"signed": True, "signer": context.officers[0]["full_name"] if context.officers else "Unknown"}

        elif step_number == 9:
            # Payment step — this triggers the payment handoff in the orchestrator
            step.requires_payment = True
            step.metadata = {"fee": 2500, "fee_display": "$25.00"}
            # The orchestrator handles the pause/handoff based on payment_tier
            # We just return the step with requires_payment=True

        elif step_number == 10:
            # Download receipt
            await asyncio.sleep(random.uniform(1.0, 2.0))
            step.metadata = {
                "confirmation_number": f"DUMMY-{random.randint(100000, 999999)}",
                "receipt_downloaded": True,
            }

        return step

    def pre_flight_check(self, context: FilingContext) -> list[str]:
        """Dummy filer accepts almost anything."""
        issues = []
        if not context.entity_name:
            issues.append("Entity name is required")
        return issues


# Auto-register
register_filer("dummy_test", DummyStateFiler)
