"""
SFBusinessRegistrationFiler — Annual Business Registration for San Francisco.

Portal: SF Treasurer & Tax Collector (etaxstatement.sfgov.org)
Login: BAN (7 digits) + TIN last 4 + PIN (8 chars) — THREE-PART login
CAPTCHA: NO → has_access_restrictions = False
Draft Save: YES → individual pages have "Save & Continue", "Exit Application" allows partial save

City-level filing: STATE_CODE = "CA-SF" (composite code)

Steps:
 1. Navigate to Portal
 2. Login (3-part: BAN + TIN last 4 + PIN)
 3. Filing Questionnaire (9 questions)
 4. Filing Menu (click Amend)
 5. Business Information Questionnaire
 6. Business Categories Selection
 7. Gross Receipts Calculation
 8. SF Gross Receipts Summary (review)
 9. Gross Receipts Tax Calculations (review)
10. Registration Renewal Fee (review)
11. Certify & Submit
12. Submission Confirmation (capture)
13. Courtesy Calculations (continue)
14. Filing Menu (proceed to payment)
15. Handle Payment

Based on screenshots SF-ABT25-001 through SF-ABT25-024.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from openklerk.core.base_filer import BaseStateFiler, FilingContext, FilingStep
from openklerk.filers import register_filer
from openklerk.core.utils import split_name, detect_form_errors, get_signer
from openklerk.core.settings import get_settings

logger = logging.getLogger("filing_engine")


def _get_sf_portal_url() -> str:
    """Generate SF portal URL with dynamic tax year.
    URL pattern: etaxstatement.sfgov.org/ABT{YY}/
    where YY is the 2-digit tax year (current year - 1).
    """
    current_year = datetime.now().year
    tax_year = current_year - 1  # Filing in 2026 for tax year 2025
    return f"https://etaxstatement.sfgov.org/ABT{tax_year % 100}/"


class SFBusinessRegistrationFiler(BaseStateFiler):
    """San Francisco Annual Business Registration filer."""

    STATE_CODE = "CA-SF"
    STATE_NAME = "San Francisco"
    FILING_CODE = "sf_abr"
    FILING_NAME = "Annual Business Registration"
    PORTAL_URL = "https://etaxstatement.sfgov.org/ABT25/"
    TOTAL_STEPS = 15

    def get_steps(self) -> list[FilingStep]:
        return [
            FilingStep(1, "Navigate to Portal", "Opening SF Treasurer portal",
                        is_page_transition=True,
                        expected_page="SF Treasurer & Tax Collector portal login page"),
            FilingStep(2, "Login", "Entering BAN, TIN last 4, and PIN",
                        is_page_transition=True,
                        expected_page="Filing questionnaire or main dashboard after successful login"),
            FilingStep(3, "Filing Questionnaire", "Answering initial screening questions",
                        is_page_transition=False,
                        expected_page="Questionnaire page with yes/no questions about business status"),
            FilingStep(4, "Filing Menu", "Selecting filing to amend",
                        is_page_transition=True,
                        expected_page="Filing menu page showing available filings with Amend button"),
            FilingStep(5, "Business Information", "Verifying business information",
                        is_page_transition=True,
                        expected_page="Business information page with entity details and contact info"),
            FilingStep(6, "Business Categories", "Selecting business category codes",
                        is_page_transition=True,
                        expected_page="Business categories selection page with NAICS/SIC codes"),
            FilingStep(7, "Gross Receipts", "Entering gross receipts data",
                        is_page_transition=True,
                        expected_page="Gross receipts data entry form with revenue fields"),
            FilingStep(8, "Gross Receipts Summary", "Reviewing SF gross receipts summary",
                        is_page_transition=True,
                        expected_page="Summary page showing entered gross receipts data"),
            FilingStep(9, "Tax Calculations", "Reviewing gross receipts tax calculations",
                        is_page_transition=True,
                        expected_page="Tax calculation page showing computed tax amounts"),
            FilingStep(10, "Registration Fee", "Reviewing registration renewal fee",
                        is_page_transition=True,
                        expected_page="Registration renewal fee page showing fee amount"),
            FilingStep(11, "Certify & Submit", "Certifying and submitting the filing",
                        is_page_transition=True,
                        expected_page="Certification page with signer name and submit button"),
            FilingStep(12, "Submission Confirmation", "Capturing submission confirmation",
                        is_page_transition=True,
                        expected_page="Confirmation page showing successful submission with reference"),
            FilingStep(13, "Courtesy Calculations", "Reviewing courtesy calculations",
                        is_page_transition=True,
                        expected_page="Courtesy tax calculations review page"),
            FilingStep(14, "Filing Menu Return", "Returning to filing menu for payment",
                        is_page_transition=True,
                        expected_page="Filing menu page with payment option available"),
            FilingStep(15, "Handle Payment", "Processing payment or deferring to user",
                        is_page_transition=True, is_payment_step=True,
                        expected_page="Payment page or payment confirmation"),
        ]

    # ── Pre-flight checks ────────────────────────────────────────────────

    def pre_flight_check(self, context: FilingContext) -> list[str]:
        issues = []

        if not context.entity_name:
            issues.append("Entity name is required")

        # SF uses BAN stored in entity_number
        if not context.entity_number:
            issues.append("San Francisco Business Account Number (BAN) is required")

        # Check portal credentials — SF needs 3 fields
        if not context.portal_username:
            issues.append("Portal username (BAN) is required for SF portal login")
        if not context.portal_password:
            issues.append("Portal password (PIN) is required for SF portal login")

        # Check portal_extra for TIN last 4
        extra = context.portal_extra or {}
        if not extra.get("tin_last4"):
            issues.append("Last 4 digits of TIN/EIN required for SF portal login")

        # Financial data
        biz_data = context.business_data or {}
        if not biz_data.get("total_gross_receipts") and biz_data.get("total_gross_receipts") != 0:
            issues.append("Total gross receipts amount is required for SF registration")
        if not biz_data.get("avg_weekly_employees_total") and biz_data.get("avg_weekly_employees_total") != 0:
            issues.append("Average weekly employee count is required for SF registration")

        return issues

    # ── Main step dispatcher ─────────────────────────────────────────────

    async def execute_step(
        self,
        step_number: int,
        context: FilingContext,
        browser: Any,
    ) -> FilingStep:
        steps = self.get_steps()
        if step_number < 1 or step_number > len(steps):
            raise ValueError(f"Invalid step_number {step_number}: must be 1-{len(steps)}")

        step = steps[step_number - 1]
        step.status = "in_progress"
        step.started_at = datetime.utcnow()

        dispatch = {
            1: self._step_01_navigate,
            2: self._step_02_login,
            3: self._step_03_filing_questionnaire,
            4: self._step_04_filing_menu,
            5: self._step_05_business_info,
            6: self._step_06_business_categories,
            7: self._step_07_gross_receipts,
            8: self._step_08_gross_receipts_summary,
            9: self._step_09_tax_calculations,
            10: self._step_10_registration_fee,
            11: self._step_11_certify_submit,
            12: self._step_12_submission_confirmation,
            13: self._step_13_courtesy_calculations,
            14: self._step_14_filing_menu_return,
            15: self._step_15_handle_payment,
        }

        handler = dispatch[step_number]
        await handler(step, context, browser)
        return step

    # ── Step 1: Navigate ─────────────────────────────────────────────────

    async def _step_01_navigate(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        import asyncio

        logger.info("Step 1: Navigating to SF Treasurer portal")

        # Use dynamic URL based on current tax year
        portal_url = context.portal_url or _get_sf_portal_url()

        max_attempts = 3
        last_error = None
        for attempt in range(1, max_attempts + 1):
            try:
                await browser.page.goto(
                    portal_url,
                    wait_until="domcontentloaded",
                    timeout=browser.timeout,
                )
                await browser.human_delay(1.0, 2.0)
                last_error = None
                break
            except Exception as e:
                last_error = e
                logger.warning(f"Step 1: Navigation attempt {attempt}/{max_attempts} failed: {e}")
                if attempt < max_attempts:
                    await asyncio.sleep(3)

        if last_error:
            raise RuntimeError(f"Could not load SF portal after {max_attempts} attempts: {last_error}")

        # Verify page loaded — check for "Treasurer" or "Business Registration"
        page_text = (await browser.page.content()).lower()
        if "treasurer" not in page_text and "business registration" not in page_text:
            raise RuntimeError("SF portal login page did not load correctly")

        step.metadata = {"url": portal_url}
        logger.info("Step 1: SF portal loaded successfully")

    # ── Step 2: Login (3-part) ───────────────────────────────────────────

    async def _step_02_login(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 2: Three-part login (BAN + TIN last 4 + PIN)")

        # Screenshot SF-ABT25-001/002: Login page with 3 fields
        # - "Your seven (7) digit Business Account Number"
        # - "The last four (4) digits of your Tax Identification Number *"
        # - "Your eight (8) character Online PIN *"
        # - "Login" button
        # NO CAPTCHA

        ban = context.portal_username  # 7-digit BAN
        pin = context.portal_password  # 8-character PIN
        extra = context.portal_extra or {}
        tin_last4 = extra.get("tin_last4", "")

        if not ban or not pin or not tin_last4:
            raise RuntimeError(
                "SF portal requires BAN, TIN last 4, and PIN. "
                f"Missing: {', '.join(f for f, v in [('BAN', ban), ('PIN', pin), ('TIN last 4', tin_last4)] if not v)}"
            )

        # Fill BAN (first field)
        await browser.human_type(
            'input[type="text"]:nth-of-type(1), '
            'input[name*="AccountNumber" i], input[id*="AccountNumber" i], '
            'input[name*="ban" i]',
            ban,
        )
        await browser.human_delay(0.3, 0.6)

        # Fill TIN last 4 (second field)
        # Try to find by position or label
        tin_filled = await browser.page.evaluate(f"""(tin) => {{
            const inputs = document.querySelectorAll('input[type="text"], input[type="password"]');
            const visibleInputs = Array.from(inputs).filter(i => {{
                const rect = i.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0 && !i.value;
            }});
            // The TIN field should be the first unfilled field after BAN
            if (visibleInputs.length > 0) {{
                visibleInputs[0].value = tin;
                visibleInputs[0].dispatchEvent(new Event('input', {{ bubbles: true }}));
                visibleInputs[0].dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }}
            return false;
        }}""", tin_last4)

        if not tin_filled:
            # Fallback: try specific selectors
            try:
                await browser.human_type(
                    'input[name*="TIN" i], input[name*="tin" i], '
                    'input[name*="TaxId" i], input[id*="TIN" i]',
                    tin_last4,
                )
            except Exception:
                logger.warning("Step 2: Could not fill TIN last 4 field")

        await browser.human_delay(0.3, 0.6)

        # Fill PIN (third field — may be password type)
        pin_filled = await browser.page.evaluate(f"""(pin) => {{
            const inputs = document.querySelectorAll('input[type="text"], input[type="password"]');
            const visibleInputs = Array.from(inputs).filter(i => {{
                const rect = i.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0 && !i.value;
            }});
            if (visibleInputs.length > 0) {{
                visibleInputs[0].value = pin;
                visibleInputs[0].dispatchEvent(new Event('input', {{ bubbles: true }}));
                visibleInputs[0].dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }}
            return false;
        }}""", pin)

        if not pin_filled:
            try:
                await browser.human_type(
                    'input[name*="PIN" i], input[name*="pin" i], '
                    'input[type="password"]',
                    pin,
                )
            except Exception:
                logger.warning("Step 2: Could not fill PIN field")

        await browser.human_delay(0.5, 1.0)
        await browser.take_screenshot("login_filled")

        # Click Login button
        await browser.human_click(
            'button:has-text("Login"), input[value="Login" i], '
            'button:has-text("Log In"), input[type="submit"]'
        )
        await browser.human_delay(3.0, 5.0)

        try:
            await browser.page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass

        # Verify login succeeded
        current_url = (await browser.get_current_url()).lower()
        page_text = (await browser.page.content()).lower()

        # After login, page should show entity info or filing questionnaire
        if "login" in page_text and "business account number" in page_text:
            # Still on login page
            screenshot = await browser.take_screenshot("login_failed")
            raise RuntimeError(
                "SF portal login failed — still on login page. "
                "Verify BAN, TIN last 4, and PIN are correct."
            )

        step.metadata = {"login_successful": True, "post_login_url": current_url}
        logger.info("Step 2: SF portal login successful")

    # ── Step 3: Filing Questionnaire ─────────────────────────────────────

    async def _step_03_filing_questionnaire(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 3: Filling Filing Questionnaire")

        # Screenshot SF-ABT25-003: Filing Questionnaire page
        # 9 questions — most are Yes/No with a few number inputs
        # - Q1: Taxable business personal property in SF? → No
        # - Q2: Average employees per week → number input
        # - Q3: NAICS code → 6-digit code + Search button
        # - Q4: Purchaser of residential real estate? → No
        # - Q5: Reporting tax credit? → No
        # - Q6: Combined/consolidated return? → No
        # - Q7: Commercial Real Property Owner? → No
        # - Q8: Receipts from lease of Commercial Real Estate? → No
        # - Q9: Related entities paid? → No

        await browser.human_delay(1.0, 2.0)

        # Check if we're on the questionnaire page
        page_text = (await browser.page.content()).lower()
        if "questionnaire" not in page_text and "filing" not in page_text:
            # May have gone directly to Filing Menu
            logger.info("Step 3: Not on questionnaire page — may have been previously completed")
            step.metadata = {"skipped": True}
            return

        biz_data = context.business_data or {}

        # Fill employee count (Q2)
        avg_employees = biz_data.get("avg_weekly_employees_total", "1")
        try:
            await browser.page.evaluate(f"""(count) => {{
                const inputs = document.querySelectorAll('input[type="text"], input[type="number"]');
                for (const inp of inputs) {{
                    const parent = inp.closest('tr, div, li, p');
                    const text = parent ? parent.textContent.toLowerCase() : '';
                    if (text.includes('employee') || text.includes('average number')) {{
                        inp.value = count;
                        inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        return true;
                    }}
                }}
                return false;
            }}""", str(avg_employees))
        except Exception:
            logger.warning("Step 3: Could not fill employee count")

        # Fill NAICS code (Q3)
        naics_code = context.naics_code or biz_data.get("naics_code", "")
        if naics_code:
            try:
                await browser.page.evaluate(f"""(code) => {{
                    const inputs = document.querySelectorAll('input[type="text"]');
                    for (const inp of inputs) {{
                        const parent = inp.closest('tr, div, li, p');
                        const text = parent ? parent.textContent.toLowerCase() : '';
                        if (text.includes('naics') || text.includes('classification')) {{
                            inp.value = code;
                            inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            return true;
                        }}
                    }}
                    return false;
                }}""", naics_code)
            except Exception:
                logger.warning("Step 3: Could not fill NAICS code")

        # Answer Yes/No questions — default to "No" for most
        # Use radio buttons or dropdowns
        await browser.page.evaluate("""() => {
            const radios = document.querySelectorAll('input[type="radio"]');
            for (const radio of radios) {
                const label = radio.closest('label');
                const parentText = (label ? label.textContent : (radio.parentElement?.textContent || '')).toLowerCase();
                // Select "No" for all Yes/No questions by default
                if (radio.value.toLowerCase() === 'no' || parentText.trim() === 'no') {
                    if (!radio.checked) {
                        radio.click();
                    }
                }
            }
        }""")
        await browser.human_delay(0.5, 1.0)

        # Click "Save & Continue"
        await self._click_save_continue(browser)

        await browser.take_screenshot("questionnaire_filled")
        step.metadata = {"avg_employees": str(avg_employees), "naics_code": naics_code}
        logger.info("Step 3: Filing Questionnaire completed")

    # ── Step 4: Filing Menu ──────────────────────────────────────────────

    async def _step_04_filing_menu(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 4: Filing Menu — selecting filing to amend")

        # Screenshot SF-ABT25-004: Filing Menu page
        # Shows: "Registration Renewal, Gross Receipts Tax, Overpaid Executive Tax,
        #         and Homelessness Gross Receipts Tax Returns"
        # "Amend" button (green), "View Prior Submission" link
        # Bottom buttons: "Exit Application", "Back", "Payment Details", "Proceed to Pay"

        await browser.human_delay(1.0, 2.0)

        # Click "Amend" button to start/edit the filing
        amend_clicked = False
        try:
            await browser.human_click(
                'button:has-text("Amend"), a:has-text("Amend"), '
                'input[value="Amend" i]'
            )
            amend_clicked = True
        except Exception:
            pass

        if not amend_clicked:
            # Try JS fallback
            amend_clicked = await browser.page.evaluate("""() => {
                const buttons = document.querySelectorAll('button, a, input[type="button"], input[type="submit"]');
                for (const btn of buttons) {
                    const text = (btn.textContent || btn.value || '').trim().toLowerCase();
                    if (text === 'amend') {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }""")

        if not amend_clicked:
            raise RuntimeError("Could not find 'Amend' button on Filing Menu")

        await browser.human_delay(2.0, 4.0)
        try:
            await browser.page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass

        step.metadata = {"amend_clicked": True}
        logger.info("Step 4: Filing Menu — Amend clicked")

    # ── Step 5: Business Information Questionnaire ───────────────────────

    async def _step_05_business_info(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 5: Business Information Questionnaire")

        # Screenshot SF-ABT25-005: Business Information Questionnaire
        # - "Are you exempt from the Registration Fee?" → No
        # - "Do you have no business activities outside of San Francisco?" → Yes/No

        await browser.human_delay(1.0, 2.0)

        biz_data = context.business_data or {}
        sf_wholly_within = biz_data.get("sf_wholly_within", True)

        # Answer questions with radio buttons
        # "Are you exempt?" → No
        await self._select_radio_near_text(browser, "exempt", "No")

        # "Do you have no business activities outside SF?" → based on business_data
        if sf_wholly_within:
            await self._select_radio_near_text(browser, "outside", "Yes")
        else:
            await self._select_radio_near_text(browser, "outside", "No")

        await browser.human_delay(0.5, 1.0)
        await self._click_save_continue(browser)

        step.metadata = {"sf_wholly_within": sf_wholly_within}
        logger.info("Step 5: Business Information completed")

    # ── Step 6: Business Categories Selection ────────────────────────────

    async def _step_06_business_categories(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 6: Business Categories Selection")

        # Screenshots SF-ABT25-006/007: Long list of business categories with checkboxes
        # Also has "Apportionment Calculation" section at bottom

        await browser.human_delay(1.0, 2.0)

        # Check if any categories are already selected (from prior filing)
        has_selection = await browser.page.evaluate("""() => {
            const checkboxes = document.querySelectorAll('input[type="checkbox"]:checked');
            return checkboxes.length > 0;
        }""")

        if has_selection:
            logger.info("Step 6: Business categories already selected from prior filing")
        else:
            # Try to match business description to a category
            business_desc = (context.business_description or "").lower()

            # Select the most generic applicable category
            category_selected = await browser.page.evaluate(f"""(desc) => {{
                const checkboxes = document.querySelectorAll('input[type="checkbox"]');
                for (const cb of checkboxes) {{
                    const label = cb.closest('label, tr, div');
                    const text = (label ? label.textContent : '').toLowerCase();
                    // Try to match business description keywords
                    if (desc && text.includes(desc.substring(0, 15))) {{
                        if (!cb.checked) cb.click();
                        return true;
                    }}
                }}
                // Fallback: select first available category if none match
                for (const cb of checkboxes) {{
                    if (!cb.checked && !cb.disabled) {{
                        const label = cb.closest('label, tr, div');
                        const text = (label ? label.textContent : '').toLowerCase();
                        if (!text.includes('select all') && text.length > 5) {{
                            cb.click();
                            return true;
                        }}
                    }}
                }}
                return false;
            }}""", business_desc)

            if category_selected:
                logger.info("Step 6: Business category selected")
            else:
                logger.warning("Step 6: No business category selected — may need user input")

        # Handle apportionment if present
        biz_data = context.business_data or {}
        apportionment = biz_data.get("apportionment_percentage", "100")
        await browser.page.evaluate(f"""(pct) => {{
            const inputs = document.querySelectorAll('input[type="text"], input[type="number"]');
            for (const inp of inputs) {{
                const parent = inp.closest('tr, div, label');
                const text = parent ? parent.textContent.toLowerCase() : '';
                if (text.includes('apportionment') && text.includes('percentage')) {{
                    if (!inp.value) {{
                        inp.value = pct;
                        inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                    return true;
                }}
            }}
            return false;
        }}""", str(apportionment))

        await browser.human_delay(0.5, 1.0)
        await self._click_save_continue(browser)

        step.metadata = {"categories_pre_selected": bool(has_selection)}
        logger.info("Step 6: Business Categories completed")

    # ── Step 7: Gross Receipts Calculation ────────────────────────────────

    async def _step_07_gross_receipts(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 7: Gross Receipts Calculation")

        # Screenshot SF-ABT25-008: Gross Receipts Calculation Credits/Exemptions
        # Multiple line items with dollar amount fields

        await browser.human_delay(1.0, 2.0)

        biz_data = context.business_data or {}
        total_gross = biz_data.get("total_gross_receipts", "0")

        # Try to fill the gross receipts field
        await browser.page.evaluate(f"""(amount) => {{
            const inputs = document.querySelectorAll('input[type="text"], input[type="number"]');
            for (const inp of inputs) {{
                const parent = inp.closest('tr, div, label');
                const text = parent ? parent.textContent.toLowerCase() : '';
                if ((text.includes('gross receipts') || text.includes('total')) &&
                    !inp.readOnly && !inp.disabled) {{
                    if (!inp.value || inp.value === '0' || inp.value === '$0.00') {{
                        inp.value = amount;
                        inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        return true;
                    }}
                }}
            }}
            return false;
        }}""", str(total_gross))

        await browser.human_delay(0.5, 1.0)
        await self._click_save_continue(browser)

        step.metadata = {"total_gross_receipts": str(total_gross)}
        logger.info("Step 7: Gross Receipts Calculation completed")

    # ── Step 8: SF Gross Receipts Summary ────────────────────────────────

    async def _step_08_gross_receipts_summary(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 8: SF Gross Receipts Summary (review)")

        # Screenshot SF-ABT25-009: Summary table with categories and amounts
        # Read-only review page — just click Continue

        await browser.human_delay(1.0, 2.0)
        screenshot = await browser.take_screenshot("gross_receipts_summary")

        # Extract total from the page
        total = await browser.page.evaluate("""() => {
            const cells = document.querySelectorAll('td, th, span');
            for (const cell of cells) {
                const text = (cell.textContent || '').trim();
                if (text.includes('Total') && cell.nextElementSibling) {
                    return cell.nextElementSibling.textContent.trim();
                }
            }
            return null;
        }""")

        await self._click_continue(browser)

        step.metadata = {"total_gross_receipts_displayed": total, "screenshot": screenshot}
        logger.info(f"Step 8: Gross Receipts Summary reviewed (total: {total})")

    # ── Step 9: Gross Receipts Tax Calculations ──────────────────────────

    async def _step_09_tax_calculations(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 9: Gross Receipts Tax Calculations (review)")

        # Screenshot SF-ABT25-010: Tax calculations — read-only
        await browser.human_delay(1.0, 2.0)
        screenshot = await browser.take_screenshot("tax_calculations")

        await self._click_continue(browser)

        step.metadata = {"screenshot": screenshot}
        logger.info("Step 9: Tax Calculations reviewed")

    # ── Step 10: Registration Renewal Fee ─────────────────────────────────

    async def _step_10_registration_fee(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 10: Registration Renewal Fee")

        # Screenshot SF-ABT25-011: Shows Registration Renewal Fee, State Fee,
        # Registration Total Due

        await browser.human_delay(1.0, 2.0)
        screenshot = await browser.take_screenshot("registration_fee")

        # Extract fee amounts from the page
        fees = await browser.page.evaluate("""() => {
            const result = {};
            const rows = document.querySelectorAll('tr, div.row, p');
            for (const row of rows) {
                const text = (row.textContent || '').trim();
                if (text.includes('Registration Renewal Fee')) {
                    const match = text.match(/\\$(\\d+\\.?\\d*)/);
                    if (match) result.renewal_fee = match[1];
                }
                if (text.includes('State Fee')) {
                    const match = text.match(/\\$(\\d+\\.?\\d*)/);
                    if (match) result.state_fee = match[1];
                }
                if (text.includes('Registration Total')) {
                    const match = text.match(/\\$(\\d+\\.?\\d*)/);
                    if (match) result.total = match[1];
                }
            }
            return result;
        }""")

        await self._click_save_continue(browser)

        step.metadata = {"fees": fees, "screenshot": screenshot}
        logger.info(f"Step 10: Registration Fee reviewed: {fees}")

    # ── Step 11: Certify & Submit ─────────────────────────────────────────

    async def _step_11_certify_submit(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 11: Certify & Submit")

        # Screenshot SF-ABT25-012/013: Taxpayer Statement with legal text
        # Fields: Name*, Title*, Phone*, Email*, Company*
        # Pre-filled with CEO info
        # "Submit" button → shows processing banner

        await browser.human_delay(1.0, 2.0)

        # Fill certification fields if empty
        signer = get_signer(context.officers)
        signer_name = signer.get("full_name", "")
        signer_title = signer.get("title", "CEO")
        signer_phone = signer.get("phone", "")
        signer_email = signer.get("email", "")

        # Fill Name field
        if signer_name:
            await self._fill_empty_field_near(browser, "name", signer_name)
        if signer_title:
            await self._fill_empty_field_near(browser, "title", signer_title)
        if signer_phone:
            await self._fill_empty_field_near(browser, "phone", signer_phone)
        if signer_email:
            await self._fill_empty_field_near(browser, "email", signer_email)

        # Fill Company
        if context.entity_name:
            await self._fill_empty_field_near(browser, "company", context.entity_name)

        await browser.human_delay(0.5, 1.0)
        await browser.take_screenshot("certify_filled")

        # Click Submit
        await browser.human_click(
            'button:has-text("Submit"), input[value="Submit" i], '
            'button[type="submit"]'
        )

        # Wait for submission processing (screenshot shows "Please wait..." banner)
        await browser.human_delay(5.0, 10.0)
        try:
            await browser.page.wait_for_load_state("domcontentloaded", timeout=30000)
        except Exception:
            pass

        step.metadata = {"submitted": True, "signer": signer_name}
        logger.info("Step 11: Filing submitted")

    # ── Step 12: Submission Confirmation ──────────────────────────────────

    async def _step_12_submission_confirmation(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 12: Capturing submission confirmation")

        # Screenshot SF-ABT25-014/015: Submission Confirmation
        # "Your 2025 Gross Receipts Tax and 2026-2027 Business Registration Renewal
        #  fees have been successfully submitted..."
        # "Download a Copy" and "Continue" buttons

        await browser.human_delay(2.0, 3.0)
        screenshot = await browser.take_screenshot("submission_confirmation")

        # Extract confirmation info
        confirmation = await browser.page.evaluate("""() => {
            const body = document.body.textContent || '';
            const result = {};
            if (body.toLowerCase().includes('successfully submitted')) {
                result.submitted = true;
            }
            // Look for email confirmation
            const emailMatch = body.match(/emailed to ([\\w.@]+)/i);
            if (emailMatch) result.email = emailMatch[1];
            // Look for confirmation number
            const confMatch = body.match(/confirmation[\\s#:]+([A-Z0-9-]+)/i);
            if (confMatch) result.confirmation_number = confMatch[1];
            return result;
        }""")

        # Click Continue to proceed
        await self._click_continue(browser)

        step.metadata = {"confirmation": confirmation, "screenshot": screenshot}
        logger.info(f"Step 12: Submission confirmation captured: {confirmation}")

    # ── Step 13: Courtesy Calculations ───────────────────────────────────

    async def _step_13_courtesy_calculations(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 13: Courtesy Calculations")

        # Screenshot SF-ABT25-016/017: Payment calculation summary
        # Shows: Date, Description, Registration Renewal Fee, Gross Receipts Tax

        await browser.human_delay(1.0, 2.0)
        screenshot = await browser.take_screenshot("courtesy_calculations")

        await self._click_continue(browser)

        step.metadata = {"screenshot": screenshot}
        logger.info("Step 13: Courtesy Calculations reviewed")

    # ── Step 14: Filing Menu Return ──────────────────────────────────────

    async def _step_14_filing_menu_return(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 14: Filing Menu — handling payment navigation")

        # Screenshot SF-ABT25-018: Back on Filing Menu
        # "Proceed to Pay" button to go to payment portal

        await browser.human_delay(1.0, 2.0)
        screenshot = await browser.take_screenshot("filing_menu_post_submit")

        # The filing is already submitted at this point
        # For customer_pays: stop here, user pays later
        # For we_handle: click "Proceed to Pay"

        step.metadata = {"screenshot": screenshot, "filing_submitted": True}
        logger.info("Step 14: Filing Menu (post-submission)")

    # ── Step 15: Handle Payment ──────────────────────────────────────────

    async def _step_15_handle_payment(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 15: Handling payment")

        # The filing is already submitted. Payment is separate.
        # Screenshot SF-ABT25-019/020: Payment Portal page
        # Screenshot SF-ABT25-021-023: Citybase payment (pay.sfgov.org)
        # Screenshot SF-ABT25-024: Payment confirmation ("Thank You!")

        if context.payment_tier == "customer_pays":
            # Filing is submitted. User pays later via portal.
            # Click "Exit Application" to cleanly exit
            try:
                await browser.human_click(
                    'button:has-text("Exit Application"), a:has-text("Exit Application"), '
                    'button:has-text("Exit"), a:has-text("Exit")'
                )
            except Exception:
                pass

            step.requires_payment = True  # Triggers AWAITING_USER_PAYMENT in orchestrator
            step.metadata = {
                "action": "exit_application",
                "payment_tier": "customer_pays",
                "note": "Filing submitted successfully. User must pay via SF portal.",
            }
            logger.info("Step 15: Filing submitted — user pays later")

        elif context.payment_tier == "we_handle":
            # Click "Proceed to Pay" to go to payment portal
            try:
                await browser.human_click(
                    'button:has-text("Proceed to Pay"), a:has-text("Proceed to Pay"), '
                    'input[value="Proceed to Pay" i]'
                )
                await browser.human_delay(3.0, 5.0)
                try:
                    await browser.page.wait_for_load_state("domcontentloaded", timeout=15000)
                except Exception:
                    pass

                # Now on Payment Portal (SF-ABT25-019)
                # Click "Pay Online"
                await browser.human_click(
                    'button:has-text("Pay Online"), a:has-text("Pay Online"), '
                    'input[value="Pay Online" i]'
                )
                await browser.human_delay(3.0, 5.0)
                try:
                    await browser.page.wait_for_load_state("domcontentloaded", timeout=15000)
                except Exception:
                    pass

                # Now on Citybase payment portal (SF-ABT25-021)
                # Fill card details
                settings = get_settings()
                if settings.SENSFIX_CARD_NUMBER:
                    # Select Credit/Debit Card payment method
                    try:
                        await browser.human_click(
                            'input[type="radio"][value*="credit" i], '
                            'label:has-text("Credit"), label:has-text("Debit")'
                        )
                    except Exception:
                        pass

                    await browser.human_delay(0.5, 1.0)

                    # Fill card number
                    try:
                        await browser.human_type(
                            'input[name*="card" i], input[id*="card" i], '
                            'input[name*="ccNumber" i], input[placeholder*="Card" i]',
                            settings.SENSFIX_CARD_NUMBER,
                        )
                    except Exception:
                        logger.warning("Step 15: Could not fill card number on Citybase")

                    step.metadata = {"action": "pay_via_citybase", "payment_tier": "we_handle"}
                else:
                    step.metadata = {"action": "no_card_configured", "payment_tier": "we_handle"}
            except Exception as e:
                logger.warning(f"Step 15: Could not proceed to payment: {e}")
                step.requires_payment = True
                step.metadata = {"action": "payment_error", "error": str(e)}

        else:
            # Cockpit handoff — click Proceed to Pay and let user take over
            try:
                await browser.human_click(
                    'button:has-text("Proceed to Pay"), a:has-text("Proceed to Pay")'
                )
                await browser.human_delay(3.0, 5.0)
            except Exception:
                pass
            step.requires_payment = True
            step.metadata = {"action": "cockpit_handoff", "payment_tier": context.payment_tier}

        logger.info(f"Step 15: Payment handling complete — {step.metadata.get('action')}")

    # ── Helper methods ───────────────────────────────────────────────────

    async def _click_save_continue(self, browser: Any):
        """Click the 'Save & Continue' button."""
        clicked = False
        for btn_text in ["Save & Continue", "Save and Continue", "Save &amp; Continue"]:
            try:
                selector = (
                    f'button:has-text("{btn_text}"), a:has-text("{btn_text}"), '
                    f'input[value="{btn_text}" i]'
                )
                if await browser.is_visible(selector):
                    await browser.page.click(selector, timeout=10000)
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            # JS fallback
            clicked = await browser.page.evaluate("""() => {
                const buttons = document.querySelectorAll('button, a, input[type="button"], input[type="submit"]');
                for (const btn of buttons) {
                    const text = (btn.textContent || btn.value || '').toLowerCase();
                    if (text.includes('save') && text.includes('continue')) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }""")

        if not clicked:
            # Try generic "Continue" as fallback
            await self._click_continue(browser)
            return

        await browser.human_delay(2.0, 4.0)
        try:
            await browser.page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass

    async def _click_continue(self, browser: Any):
        """Click the 'Continue' button."""
        try:
            await browser.human_click(
                'button:has-text("Continue"), a:has-text("Continue"), '
                'input[value="Continue" i]'
            )
        except Exception:
            # JS fallback
            await browser.page.evaluate("""() => {
                const buttons = document.querySelectorAll('button, a, input[type="button"], input[type="submit"]');
                for (const btn of buttons) {
                    const text = (btn.textContent || btn.value || '').trim().toLowerCase();
                    if (text === 'continue') {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }""")

        await browser.human_delay(2.0, 4.0)
        try:
            await browser.page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass

    async def _select_radio_near_text(self, browser: Any, text_match: str, value: str):
        """Select a radio button near text matching the given string."""
        await browser.page.evaluate(f"""(data) => {{
            const radios = document.querySelectorAll('input[type="radio"]');
            for (const radio of radios) {{
                const parent = radio.closest('tr, div, p, li, label');
                const parentText = parent ? parent.textContent.toLowerCase() : '';
                if (parentText.includes(data.text)) {{
                    const radioLabel = radio.closest('label') || radio.parentElement;
                    const radioText = (radioLabel ? radioLabel.textContent : '').trim().toLowerCase();
                    if (radioText === data.value.toLowerCase() ||
                        radio.value.toLowerCase() === data.value.toLowerCase()) {{
                        if (!radio.checked) radio.click();
                        return true;
                    }}
                }}
            }}
            return false;
        }}""", {"text": text_match.lower(), "value": value})

    async def _fill_empty_field_near(self, browser: Any, label: str, value: str):
        """Fill a text input near a label, only if the field is empty."""
        await browser.page.evaluate(f"""(data) => {{
            const inputs = document.querySelectorAll('input[type="text"], input[type="email"], input[type="tel"]');
            for (const inp of inputs) {{
                if (inp.readOnly || inp.disabled || inp.value) continue;
                const parent = inp.closest('tr, div, label');
                const nearby = parent ? parent.textContent.toLowerCase() : '';
                const name = (inp.name || '').toLowerCase();
                const placeholder = (inp.placeholder || '').toLowerCase();
                if (nearby.includes(data.label) || name.includes(data.label) || placeholder.includes(data.label)) {{
                    inp.value = data.value;
                    inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return true;
                }}
            }}
            return false;
        }}""", {"label": label.lower(), "value": value})


# Auto-register
register_filer("sf_abr", SFBusinessRegistrationFiler)
