"""
DelawareFranchiseTaxFiler — Annual Franchise Tax Report filing for Delaware corporations.

Portal: DCIS - eCorp (icis.corp.delaware.gov)
Login: File Number + CAPTCHA (visual challenge)
CAPTCHA: YES → has_access_restrictions = True → auto-trigger NOT possible
Draft Save: YES → "Save and Exit" / "Exit" available

Steps:
 1. Navigate to Portal
 2. Login (enter file number, CAPTCHA pause via NEEDS_INPUT)
 3. Select Filing from Dashboard
 4. Fill Annual Report Form (stock info, officers, nature of business — single page)
 5. Handle Payment (Save and Exit / submit)
 6. Confirm & Capture Result

Based on screenshots DE-AFT25-001 through DE-AFT25-009.
"""

import logging
from typing import Any, Optional
from datetime import datetime

from openclerc.core.base_filer import BaseStateFiler, FilingContext, FilingStep
from openclerc.filers import register_filer
from openclerc.core.utils import split_name, format_address_line, detect_form_errors
from openclerc.core.settings import get_settings

logger = logging.getLogger("filing_engine")


class DelawareFranchiseTaxFiler(BaseStateFiler):
    """Delaware Annual Franchise Tax Report filer for corporations."""

    STATE_CODE = "DE"
    STATE_NAME = "Delaware"
    FILING_CODE = "de_franchise_tax"
    FILING_NAME = "Annual Franchise Tax Report"
    PORTAL_URL = "https://icis.corp.delaware.gov/ecorp/logintax.aspx?FilingType=FranchiseTax"
    TOTAL_STEPS = 6

    def __init__(self):
        super().__init__()
        self._pending_input: dict[int, str] = {}  # step_number → input_response

    def get_steps(self) -> list[FilingStep]:
        return [
            FilingStep(1, "Navigate to Portal", "Opening Delaware DCIS eCorp portal",
                        is_page_transition=True,
                        expected_page="Delaware DCIS eCorp login page with file number and CAPTCHA fields"),
            FilingStep(2, "Login", "Entering file number and solving CAPTCHA",
                        is_page_transition=True,
                        expected_page="Dashboard page showing available filings for the entity"),
            FilingStep(3, "Select Filing", "Selecting annual report from dashboard",
                        is_page_transition=True,
                        expected_page="Annual franchise tax report form with stock info, officers, and nature of business"),
            FilingStep(4, "Fill Annual Report", "Filling stock info, officers, and nature of business",
                        is_page_transition=False,
                        expected_page="Annual report form being filled with entity data"),
            FilingStep(5, "Handle Payment", "Processing payment or saving as draft",
                        is_page_transition=True, is_payment_step=True,
                        expected_page="Payment page or Save and Exit confirmation"),
            FilingStep(6, "Confirm Filing", "Capturing confirmation and receipt",
                        is_page_transition=True,
                        expected_page="Confirmation page with filing receipt and reference number"),
        ]

    # ── Pre-flight checks ────────────────────────────────────────────────

    def pre_flight_check(self, context: FilingContext) -> list[str]:
        issues = []

        if not context.entity_name:
            issues.append("Entity name is required")

        if not context.entity_number:
            issues.append("Delaware file number is required")

        # DE uses file number as credential — portal_username stores file number
        # No portal_password required (no username/password login)

        # Officers — DE requires President, Secretary, Treasurer minimum for corps
        entity_type = (context.entity_type or "").lower()
        if "corp" in entity_type or "inc" in entity_type:
            titles = [o.get("title", "").lower() for o in context.officers]
            if not any("president" in t or "ceo" in t for t in titles):
                issues.append("Delaware corporation requires a President/CEO")
            if not any("secretary" in t for t in titles):
                issues.append("Delaware corporation requires a Secretary")
            if not any("treasurer" in t or "cfo" in t for t in titles):
                issues.append("Delaware corporation requires a Treasurer/CFO")

        # Financial data for tax calculation
        biz_data = context.business_data or {}
        if not biz_data.get("authorized_shares"):
            issues.append("Authorized shares count is required for Delaware franchise tax calculation")

        return issues

    # ── Main step dispatcher ─────────────────────────────────────────────

    def provide_input(self, step_number: int, response: str):
        """Store user input for a step (called by orchestrator before re-executing)."""
        self._pending_input[step_number] = response

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

        # Restore any pending user input for this step
        if step_number in self._pending_input:
            step.input_response = self._pending_input.pop(step_number)

        dispatch = {
            1: self._step_01_navigate,
            2: self._step_02_login,
            3: self._step_03_select_filing,
            4: self._step_04_fill_form,
            5: self._step_05_handle_payment,
            6: self._step_06_confirm,
        }

        handler = dispatch[step_number]
        await handler(step, context, browser)
        return step

    # ── Step 1: Navigate to Portal ───────────────────────────────────────

    async def _step_01_navigate(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        import asyncio

        logger.info("Step 1: Navigating to Delaware DCIS eCorp portal")

        max_attempts = 3
        last_error = None
        for attempt in range(1, max_attempts + 1):
            try:
                await browser.page.goto(
                    self.PORTAL_URL,
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
            raise RuntimeError(f"Could not load DE portal after {max_attempts} attempts: {last_error}")

        # Verify page loaded — check for "File Number Entry" text
        page_text = (await browser.page.content()).lower()
        if "file number" not in page_text and "dcis" not in page_text:
            raise RuntimeError("Delaware portal login page did not load correctly")

        step.metadata = {"url": self.PORTAL_URL}
        logger.info("Step 1: Delaware portal loaded successfully")

    # ── Step 2: Login (File Number + CAPTCHA) ────────────────────────────

    async def _step_02_login(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 2: Entering file number and handling CAPTCHA")

        file_number = context.entity_number
        if not file_number:
            raise RuntimeError("Delaware file number is missing — cannot log in")

        # Screenshot DE-AFT25-001: File Number Entry page
        # - Input field for "Business Entity File Number"
        # - CAPTCHA image (distorted text)
        # - Input for CAPTCHA solution
        # - "Continue" button

        # Fill file number
        await browser.human_type(
            'input[name*="FileNumber" i], input[name*="filenumber" i], '
            'input[id*="FileNumber" i], input[id*="txtFileNumber" i], '
            'input[type="text"]',
            file_number,
        )
        await browser.human_delay(0.5, 1.0)

        # Take screenshot showing CAPTCHA
        screenshot = await browser.take_screenshot("captcha_challenge")

        # Signal NEEDS_INPUT for CAPTCHA solving
        # The orchestrator will pause and wait for user to solve via cockpit
        step.requires_user_input = True
        step.input_prompt = (
            "Please solve the CAPTCHA on the Delaware portal login page. "
            "Enter the text shown in the CAPTCHA image."
        )
        step.metadata = {
            "input_type": "captcha",
            "interactive_mode": True,
            "screenshot": screenshot,
            "file_number_entered": True,
        }
        logger.info("Step 2: CAPTCHA detected — requesting user input")

        # If we already have a response (re-execution after input), type it and submit
        if step.input_response:
            captcha_text = step.input_response.strip()
            logger.info(f"Step 2: Received CAPTCHA solution, entering...")

            # Type CAPTCHA solution into the CAPTCHA input field
            # Screenshot shows a text input below the CAPTCHA image
            await browser.human_type(
                'input[name*="captcha" i], input[name*="Captcha" i], '
                'input[id*="captcha" i], input[id*="txtCaptcha" i], '
                'input[name*="session" i], input[id*="session" i]',
                captcha_text,
            )
            await browser.human_delay(0.5, 1.0)

            # Click Continue button
            await browser.human_click(
                'input[value="Continue" i], button:has-text("Continue"), '
                'input[type="submit"][value="Continue" i], '
                'a:has-text("Continue")'
            )
            await browser.human_delay(3.0, 5.0)

            try:
                await browser.page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass

            # Verify we're past the login page
            current_url = (await browser.get_current_url()).lower()
            page_text = (await browser.page.content()).lower()

            if "logintax" in current_url and "file number" in page_text:
                # Still on login page — CAPTCHA or file number was wrong
                screenshot = await browser.take_screenshot("login_failed")
                raise RuntimeError(
                    "Login failed — still on login page. CAPTCHA solution may be incorrect "
                    "or file number is invalid."
                )

            step.requires_user_input = False
            step.metadata["login_successful"] = True
            logger.info("Step 2: Login successful — past CAPTCHA")

    # ── Step 3: Select Filing from Dashboard ─────────────────────────────

    async def _step_03_select_filing(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 3: Selecting filing from dashboard")

        # Screenshot DE-AFT25-004: Dashboard page
        # Shows "Annual Report" with File No, Name
        # Tax Year 2025 → "File Amended Annual Report" link
        # Also "File current year taxes" link
        # "Exit" button

        await browser.human_delay(1.0, 2.0)

        # Verify we're on the dashboard
        page_text = (await browser.page.content()).lower()
        if "annual report" not in page_text and "dashboard" not in page_text:
            raise RuntimeError("Not on Delaware dashboard page after login")

        # Verify entity name is shown
        if context.entity_name:
            name_visible = await browser.page_contains_text(context.entity_name)
            step.metadata["entity_name_verified"] = name_visible

        screenshot = await browser.take_screenshot("dashboard")

        # Click "File Amended Annual Report" or "File current year taxes"
        clicked = False

        # Try "File Amended Annual Report" link first (shown in screenshot)
        for link_text in [
            "File Amended Annual Report",
            "File Annual Report",
            "File current year taxes",
        ]:
            try:
                selector = f'a:has-text("{link_text}"), input[value="{link_text}"]'
                if await browser.is_visible(selector):
                    await browser.page.click(selector, timeout=10000)
                    clicked = True
                    logger.info(f"Step 3: Clicked '{link_text}'")
                    break
            except Exception:
                continue

        if not clicked:
            # Try JS-based link clicking (ASP.NET postback links)
            clicked = await browser.page.evaluate("""() => {
                const links = document.querySelectorAll('a, input[type="submit"]');
                for (const link of links) {
                    const text = (link.textContent || link.value || '').toLowerCase();
                    if (text.includes('file') && (text.includes('annual') || text.includes('tax'))) {
                        link.click();
                        return true;
                    }
                }
                return false;
            }""")

        if not clicked:
            raise RuntimeError(
                "Could not find 'File Annual Report' or 'File current year taxes' link on dashboard"
            )

        await browser.human_delay(3.0, 5.0)
        try:
            await browser.page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass

        step.metadata["dashboard_screenshot"] = screenshot
        logger.info("Step 3: Filing selected from dashboard")

    # ── Step 4: Fill Annual Report Form ──────────────────────────────────

    async def _step_04_fill_form(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 4: Filling annual franchise tax report form")

        # Screenshots DE-AFT25-005 through 009: SINGLE PAGE form with:
        # - Entity info at top (File Number, Entity Name — read only)
        # - Stock Information section (table with share classes)
        # - Officer's Information section (table with names/titles/addresses)
        # - Nature of Business section
        # - Bottom tabs and submit buttons

        await browser.human_delay(1.0, 2.0)

        # Verify we're on the filing form
        page_text = (await browser.page.content()).lower()
        if "franchise tax" not in page_text and "annual report" not in page_text:
            raise RuntimeError("Not on the annual franchise tax report form")

        screenshot = await browser.take_screenshot("form_initial")

        # --- Stock Information ---
        biz_data = context.business_data or {}
        authorized_shares = biz_data.get("authorized_shares", "")
        issued_shares = biz_data.get("issued_shares", "")
        par_value = biz_data.get("par_value_per_share", "")
        total_gross_assets = biz_data.get("total_gross_assets", "")

        # Fill stock information fields
        # The form has a table for share classes. Try to fill the first row.
        if authorized_shares:
            await self._fill_field_by_label(
                browser, "authorized", str(authorized_shares),
                fallback_names=["Authorized", "AuthShares", "txtAuthorized"]
            )

        if issued_shares:
            await self._fill_field_by_label(
                browser, "issued", str(issued_shares),
                fallback_names=["Issued", "IssuedShares", "txtIssued"]
            )

        if par_value:
            await self._fill_field_by_label(
                browser, "par", str(par_value),
                fallback_names=["Par", "ParValue", "txtPar"]
            )

        if total_gross_assets:
            await self._fill_field_by_label(
                browser, "gross assets", str(total_gross_assets),
                fallback_names=["GrossAssets", "Assets", "txtGrossAssets"]
            )

        await browser.human_delay(0.5, 1.0)

        # --- Officers/Directors ---
        # The portal may pre-populate officers from previous filings.
        # Check if officers are already filled.
        officers_present = await browser.page.evaluate("""() => {
            const tables = document.querySelectorAll('table');
            for (const table of tables) {
                const text = (table.textContent || '').toLowerCase();
                if (text.includes('officer') || text.includes('director')) {
                    const rows = table.querySelectorAll('tr');
                    // Count rows with actual data (skip header rows)
                    let dataRows = 0;
                    for (const row of rows) {
                        const cells = row.querySelectorAll('td');
                        if (cells.length > 0) {
                            const cellText = Array.from(cells).map(c => c.textContent.trim()).join('');
                            if (cellText.length > 5) dataRows++;
                        }
                    }
                    return dataRows;
                }
            }
            return 0;
        }""")

        if officers_present and officers_present > 0:
            logger.info(f"Step 4: {officers_present} officers already pre-populated")
        else:
            logger.info(f"Step 4: Filling {len(context.officers)} officers")
            for officer in context.officers:
                name = officer.get("full_name", "")
                title = officer.get("title", "")
                address = officer.get("address", {})
                if not name:
                    continue

                first, last = split_name(name)
                addr_line = format_address_line(address) if address else ""

                # Try to add officer via form
                try:
                    # Click "Add" button in officers section
                    add_clicked = await browser.page.evaluate("""() => {
                        const buttons = document.querySelectorAll('input[type="button"], button, a');
                        for (const btn of buttons) {
                            const text = (btn.textContent || btn.value || '').toLowerCase();
                            const parent = btn.closest('div, fieldset, table');
                            const parentText = parent ? parent.textContent.toLowerCase() : '';
                            if (text.includes('add') && parentText.includes('officer')) {
                                btn.click();
                                return true;
                            }
                        }
                        return false;
                    }""")

                    if add_clicked:
                        await browser.human_delay(0.5, 1.0)
                        # Fill the newly added row — look for empty inputs
                        await browser.page.evaluate(f"""(data) => {{
                            const inputs = document.querySelectorAll('input[type="text"]:not([readonly])');
                            const empties = Array.from(inputs).filter(i => !i.value && i.offsetParent !== null);
                            // Fill sequentially: name, title, address fields
                            if (empties.length >= 1) empties[0].value = data.name;
                            if (empties.length >= 2) empties[1].value = data.title;
                            if (empties.length >= 3) empties[2].value = data.address;
                            empties.forEach(inp => {{
                                inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            }});
                        }}""", {"name": name, "title": title, "address": addr_line})
                except Exception as e:
                    logger.warning(f"Step 4: Could not add officer {name}: {e}")

        await browser.human_delay(0.5, 1.0)

        # --- Nature of Business ---
        business_desc = context.business_description or ""
        if business_desc:
            await self._fill_field_by_label(
                browser, "nature of business", business_desc.upper(),
                fallback_names=["NatureOfBusiness", "Business", "txtNature", "txtBusiness"]
            )
            # Also try dropdown if it's a select element
            try:
                select_filled = await browser.page.evaluate(f"""(desc) => {{
                    const selects = document.querySelectorAll('select');
                    for (const sel of selects) {{
                        const label = sel.closest('tr, div, label');
                        const labelText = label ? label.textContent.toLowerCase() : '';
                        if (labelText.includes('nature') || labelText.includes('business')) {{
                            // Try to find a matching option
                            for (const opt of sel.options) {{
                                if (opt.text.toLowerCase().includes(desc.toLowerCase().substring(0, 10))) {{
                                    sel.value = opt.value;
                                    sel.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    return true;
                                }}
                            }}
                            // Select the first non-empty option if no match
                            if (sel.options.length > 1) {{
                                sel.selectedIndex = 1;
                                sel.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                return true;
                            }}
                        }}
                    }}
                    return false;
                }}""", business_desc)
            except Exception:
                pass

        await browser.take_screenshot("form_filled")

        step.metadata = {
            "officers_pre_populated": officers_present or 0,
            "authorized_shares": authorized_shares,
            "nature_of_business": business_desc,
        }
        logger.info("Step 4: Annual report form filled")

    # ── Step 5: Handle Payment ───────────────────────────────────────────

    async def _step_05_handle_payment(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 5: Handling payment")

        # Screenshot DE-AFT25-005-009: Bottom of form has action buttons
        # including Save and Exit / Submit / Calculate Tax

        if context.payment_tier == "customer_pays":
            # Signal payment needed — orchestrator decides path 1a vs 1b
            step.requires_payment = True
            step.metadata = {
                "action": "awaiting_payment_decision",
                "payment_tier": "customer_pays",
                "draft_save_available": context.draft_save_available,
            }
            logger.info("Step 5: Payment required — orchestrator will decide path")

        elif context.payment_tier == "we_handle":
            # Submit the form and proceed to payment
            submit_clicked = False
            for btn_text in ["Submit", "File", "Continue", "Pay"]:
                try:
                    selector = (
                        f'input[value="{btn_text}" i], button:has-text("{btn_text}"), '
                        f'a:has-text("{btn_text}")'
                    )
                    if await browser.is_visible(selector):
                        await browser.page.click(selector, timeout=10000)
                        submit_clicked = True
                        break
                except Exception:
                    continue

            if submit_clicked:
                await browser.human_delay(3.0, 5.0)
                # Payment form handling would go here
                settings = get_settings()
                # Fill card details if available
                if settings.SENSFIX_CARD_NUMBER:
                    logger.info("Step 5: Filling payment with Sensfix card")
                    # Try to fill card number, expiry, CVV
                    try:
                        await browser.human_type(
                            'input[name*="card" i], input[id*="card" i], '
                            'input[name*="ccnum" i]',
                            settings.SENSFIX_CARD_NUMBER,
                        )
                    except Exception:
                        logger.warning("Step 5: Could not fill card number")
                step.metadata = {"action": "submit_and_pay", "payment_tier": "we_handle"}
            else:
                raise RuntimeError("Could not find Submit/Pay button")

        else:
            # Default: save and exit
            step.requires_payment = True
            step.metadata = {"action": "cockpit_handoff", "payment_tier": context.payment_tier}

    async def _save_draft(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        """Save the filing as a draft (click Save and Exit)."""
        logger.info("Step 5: Saving draft — clicking Save and Exit")
        save_clicked = False
        for btn_text in ["Save and Exit", "Save & Exit", "Exit"]:
            try:
                selector = (
                    f'input[value="{btn_text}" i], button:has-text("{btn_text}"), '
                    f'a:has-text("{btn_text}")'
                )
                if await browser.is_visible(selector):
                    await browser.page.click(selector, timeout=10000)
                    save_clicked = True
                    logger.info(f"Step 5: Clicked '{btn_text}'")
                    break
            except Exception:
                continue

        if not save_clicked:
            save_clicked = await browser.page.evaluate("""() => {
                const buttons = document.querySelectorAll('input[type="submit"], input[type="button"], button, a');
                for (const btn of buttons) {
                    const text = (btn.textContent || btn.value || '').toLowerCase();
                    if (text.includes('save') || text.includes('exit')) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }""")

        if save_clicked:
            await browser.human_delay(3.0, 5.0)
            step.metadata = {"action": "save_and_exit", "payment_tier": "customer_pays"}
            logger.info("Step 5: Form saved as draft")
        else:
            logger.warning("Step 5: Could not find 'Save and Exit' button")

    # ── Step 6: Confirm & Capture ────────────────────────────────────────

    async def _step_06_confirm(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 6: Capturing confirmation")

        await browser.human_delay(2.0, 3.0)
        screenshot = await browser.take_screenshot("confirmation")

        # Try to extract confirmation number from the page
        confirmation_number = await browser.page.evaluate("""() => {
            const body = document.body.textContent || '';
            // Look for common confirmation patterns
            const patterns = [
                /confirmation[\\s#:]+([A-Z0-9-]+)/i,
                /reference[\\s#:]+([A-Z0-9-]+)/i,
                /transaction[\\s#:]+([A-Z0-9-]+)/i,
                /receipt[\\s#:]+([A-Z0-9-]+)/i,
            ];
            for (const pattern of patterns) {
                const match = body.match(pattern);
                if (match) return match[1];
            }
            return null;
        }""")

        step.metadata = {
            "confirmation_screenshot": screenshot,
            "confirmation_number": confirmation_number,
        }

        if confirmation_number:
            logger.info(f"Step 6: Confirmation number captured: {confirmation_number}")
        else:
            logger.info("Step 6: Confirmation page captured (no confirmation number found)")

    # ── Helper methods ───────────────────────────────────────────────────

    async def _fill_field_by_label(
        self,
        browser: Any,
        label_text: str,
        value: str,
        fallback_names: list[str] = None,
    ):
        """Fill a form field by finding it near a label containing the given text."""
        filled = await browser.page.evaluate(f"""(data) => {{
            // Strategy 1: Find input near a label/td containing the text
            const labels = document.querySelectorAll('label, td, th, span, div');
            for (const label of labels) {{
                const text = (label.textContent || '').toLowerCase();
                if (text.includes(data.label)) {{
                    // Look for nearby input
                    const parent = label.closest('tr, div, fieldset');
                    if (parent) {{
                        const input = parent.querySelector('input[type="text"]:not([readonly]), textarea, select');
                        if (input && !input.value) {{
                            input.value = data.value;
                            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            return true;
                        }}
                    }}
                }}
            }}
            return false;
        }}""", {"label": label_text.lower(), "value": value})

        if filled:
            return True

        # Strategy 2: Try name-based selectors
        if fallback_names:
            for name in fallback_names:
                try:
                    selector = f'input[name*="{name}" i], input[id*="{name}" i], textarea[name*="{name}" i]'
                    if await browser.is_visible(selector):
                        await browser.human_type(selector, value)
                        return True
                except Exception:
                    continue

        logger.warning(f"Could not fill field '{label_text}' with value '{value}'")
        return False


# Auto-register under all known DE filing codes
register_filer("de_franchise_tax", DelawareFranchiseTaxFiler)
register_filer("de_annual_corp", DelawareFranchiseTaxFiler)
register_filer("de_annual_llc", DelawareFranchiseTaxFiler)
