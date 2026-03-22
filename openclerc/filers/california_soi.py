"""
CaliforniaSOIFiler — Autonomous filing of California Statement of Information.

Implements BaseStateFiler with a 16-step workflow for filing SOIs on
bizfileonline.sos.ca.gov for both corporations and LLCs.

Steps:
 1. Navigate to Portal
 2. Log In (idm.sos.ca.gov)
 3. Search for Entity
 4. Select Entity & Initiate SOI
 5. Accept Privacy Warning / Terms
 6. Fill Submitter Page
 7. Verify Entity Details Page
 8. Fill Business Addresses
 9. Fill Officers & Directors
10. Fill Agent for Service of Process
11. Fill Type of Business & Email Notifications
12. Fill Labor Judgment
13. Review and Sign (e-signature modal)
14. Review Processing Fees
15. Handle Payment (draft save / card / cockpit handoff)
16. Confirm Filing & Download Receipt
"""

import logging
import re
from typing import Any, Optional

from openclerc.core.base_filer import BaseStateFiler, FilingContext, FilingStep
from openclerc.filers import register_filer
from openclerc.core.utils import split_name  # noqa: F401 — shared utility
from openclerc.core.settings import get_settings

logger = logging.getLogger("filing_engine")


class CaliforniaSOIFiler(BaseStateFiler):
    """California Statement of Information filer for corps and LLCs."""

    STATE_CODE = "CA"
    STATE_NAME = "California"
    FILING_CODE = "ca_soi"
    FILING_NAME = "Statement of Information"
    PORTAL_URL = "https://bizfileonline.sos.ca.gov"
    SEARCH_URL = "https://bizfileonline.sos.ca.gov/search/business"
    TOTAL_STEPS = 16

    FEES = {"corporation": 2500, "llc": 2000, "nonprofit": 2500}
    MAX_RELOGIN_ATTEMPTS = 2

    def __init__(self):
        self._relogin_count = 0
        self._last_step_15_action: Optional[str] = None  # Track payment outcome

    # ── Step definitions ─────────────────────────────────────────────────

    def get_steps(self) -> list[FilingStep]:
        return [
            FilingStep(1, "Navigate to Portal", "Opening bizfile Online portal",
                        is_page_transition=True,
                        expected_page="bizfile Online landing page or login redirect"),
            FilingStep(2, "Log In", "Logging in to bizfile account",
                        is_page_transition=True,
                        expected_page="bizfile dashboard showing logged-in user or entity search page"),
            FilingStep(3, "Search for Entity", "Searching for entity by number",
                        is_page_transition=True,
                        expected_page="Search results page showing matching entities"),
            FilingStep(4, "Select Entity & Initiate SOI", "Selecting entity and opening SOI form",
                        is_page_transition=True,
                        expected_page="Statement of Information form first page or privacy warning"),
            FilingStep(5, "Accept Privacy Warning", "Accepting terms and conditions",
                        is_page_transition=True,
                        expected_page="Submitter information form page"),
            FilingStep(6, "Fill Submitter Page", "Entering submitter information",
                        is_page_transition=False,
                        expected_page="Submitter page with name, address, email fields"),
            FilingStep(7, "Verify Entity Details", "Verifying entity details page",
                        is_page_transition=True,
                        expected_page="Entity details page showing name, number, type, formation date"),
            FilingStep(8, "Fill Business Addresses", "Entering principal and mailing addresses",
                        is_page_transition=True,
                        expected_page="Business addresses form with principal and mailing address fields"),
            FilingStep(9, "Fill Officers & Directors", "Entering officer and director information",
                        is_page_transition=True,
                        expected_page="Officers and directors listing page"),
            FilingStep(10, "Fill Agent for Service of Process", "Entering registered agent details",
                        is_page_transition=True,
                        expected_page="Agent for service of process form"),
            FilingStep(11, "Fill Type of Business", "Entering business type and email preferences",
                        is_page_transition=True,
                        expected_page="Type of business and email notification preferences page"),
            FilingStep(12, "Fill Labor Judgment", "Confirming labor judgment disclosure",
                        is_page_transition=True,
                        expected_page="Labor judgment disclosure page with checkbox"),
            FilingStep(13, "Review and Sign", "Reviewing form and applying e-signature",
                        is_page_transition=True,
                        expected_page="Review page with all entered data and e-signature modal"),
            FilingStep(14, "Review Processing Fees", "Reviewing fee summary",
                        is_page_transition=True,
                        expected_page="Processing fees summary page showing filing fee amount"),
            FilingStep(15, "Handle Payment", "Processing payment or saving draft",
                        is_page_transition=True, is_payment_step=True,
                        expected_page="Payment page or draft save confirmation"),
            FilingStep(16, "Confirm Filing & Download Receipt", "Downloading confirmation and receipt",
                        is_page_transition=True,
                        expected_page="Filing confirmation page with confirmation number and receipt download"),
        ]

    # ── Pre-flight checks ────────────────────────────────────────────────

    def pre_flight_check(self, context: FilingContext) -> list[str]:
        issues = super().pre_flight_check(context)

        if not context.entity_number:
            issues.append("California entity number (file number) is required")

        addr = context.principal_address
        if not addr or not addr.get("street1"):
            issues.append("Principal office street address is required")
        if not addr or not addr.get("city"):
            issues.append("Principal office city is required")
        if not addr or not addr.get("state"):
            issues.append("Principal office state is required")
        if not addr or not addr.get("zip"):
            issues.append("Principal office ZIP code is required")

        entity_type = (context.entity_type or "").lower()
        if any(t in entity_type for t in ("corp", "inc", "c_corp", "s_corp")):
            titles = [o.get("title", "").lower() for o in context.officers]
            # Warn about missing officer titles (not hard errors — portal
            # pre-populates officers from the last filing for re-filings)
            if not any("ceo" in t or "chief executive" in t or "president" in t for t in titles):
                logger.warning("No CEO/President officer in database — portal may have it pre-populated")
            if not any("cfo" in t or "chief financial" in t or "treasurer" in t for t in titles):
                logger.warning("No CFO/Treasurer officer in database — portal may have it pre-populated")
            if not any("secretary" in t for t in titles):
                logger.warning("No Secretary officer in database — portal may have it pre-populated")

        if not context.registered_agent:
            logger.warning("No registered agent in database — portal may have it pre-populated")

        if not any(o.get("is_signer") for o in context.officers):
            issues.append("At least one officer must be designated as the signer")

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

        # Check for session expiry before each step (except navigate/search/select/login)
        if step_number > 4:
            await self._check_session_and_relogin(context, browser)

        dispatch = {
            1: self._step_01_navigate,
            2: self._step_02_login,
            3: self._step_03_search_entity,
            4: self._step_04_select_entity_and_file_soi,
            5: self._step_05_accept_privacy,
            6: self._step_06_fill_submitter,
            7: self._step_07_verify_entity_details,
            8: self._step_08_fill_addresses,
            9: self._step_09_fill_officers,
            10: self._step_10_fill_agent,
            11: self._step_11_fill_business_type,
            12: self._step_12_fill_labor_judgment,
            13: self._step_13_review_and_sign,
            14: self._step_14_review_fees,
            15: self._step_15_handle_payment,
            16: self._step_16_confirm_and_download,
        }

        handler = dispatch[step_number]
        await handler(step, context, browser)
        return step

    # ── Step 1: Navigate to Portal ───────────────────────────────────────

    async def _step_01_navigate(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        import asyncio

        logger.info("Step 1: Navigating to bizfile Online search page")

        # Use domcontentloaded instead of networkidle — the CA SOS portal
        # keeps analytics connections open that prevent networkidle from
        # resolving within the timeout.
        max_attempts = 3
        last_error = None
        for attempt in range(1, max_attempts + 1):
            try:
                await browser.page.goto(
                    self.SEARCH_URL,
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
            raise RuntimeError(f"Could not load portal after {max_attempts} attempts: {last_error}")

        # Bring browser window to front after first navigation
        await browser.focus_window()

        # Check for maintenance/errors
        error = await browser.detect_error_page()
        if error:
            raise RuntimeError(f"Portal unavailable: {error}")

        # Wait a moment for JS-rendered content to appear
        await asyncio.sleep(2)

        # Verify page loaded — check several indicators
        page_text = (await browser.page.content()).lower()
        current_url = (await browser.get_current_url()).lower()
        loaded = (
            "bizfile" in page_text
            or "secretary of state" in page_text
            or "california" in page_text
            or "sos.ca.gov" in current_url
            or await browser.is_visible('#SearchCriteria')
            or await browser.is_visible('input[type="search"]')
            or await browser.is_visible('input[type="text"]')
        )

        if not loaded:
            # Log what we actually see for debugging
            title = await browser.page.title()
            logger.error(f"Step 1: Page check failed. URL={current_url}, title={title}")
            logger.error(f"Step 1: Page text (first 500 chars): {page_text[:500]}")
            raise RuntimeError(
                f"Portal search page did not load. URL: {current_url}, Title: {title}"
            )

        step.metadata = {"url": self.SEARCH_URL, "loaded_url": current_url}
        logger.info("Step 1: Search page loaded successfully")

    # ── Step 2: Log In ───────────────────────────────────────────────────

    async def _step_02_login(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 2: Logging in to bizfile Online")

        if not context.portal_username or not context.portal_password:
            raise RuntimeError("Portal credentials are missing — cannot log in")

        # Check if already logged in (e.g. session cookie from previous run)
        # Look for "Logout" link which only appears when logged in
        current_url = await browser.get_current_url()
        if await browser.is_visible('a:has-text("Logout"), a:has-text("Log Out")'):
            logger.info("Step 2: Already logged in (session active)")
            step.metadata = {"login_performed": False, "already_logged_in": True}
            return

        # Extract the Login link href from the page to get the real SSO URL
        login_href = await browser.page.evaluate("""() => {
            // Try top-right Login button/link
            const links = document.querySelectorAll('a');
            for (const link of links) {
                const text = (link.textContent || '').trim().toLowerCase();
                if (text === 'login' || text === 'log in' || text === 'sign in') {
                    return link.href;
                }
            }
            return null;
        }""")

        if login_href:
            logger.info(f"Step 2: Found login link: {login_href}")
            await browser.page.goto(login_href, wait_until="domcontentloaded", timeout=browser.timeout)
        else:
            # Fallback: click the Login link directly and handle navigation
            logger.info("Step 2: No login href found, clicking Login link")
            await browser.human_click(
                'a:has-text("Login"), a:has-text("Log In"), '
                'button:has-text("Login"), button:has-text("Log In")'
            )

        await browser.human_delay(2.0, 4.0)
        try:
            await browser.page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass  # Best-effort — login page may already be loaded

        # Wait for the login form (should be on idm.sos.ca.gov now)
        try:
            await browser.page.wait_for_selector(
                'input[type="password"]', timeout=20000
            )
        except Exception:
            # Check if we ended up logged in somehow (SSO auto-login)
            if await browser.is_visible('a:has-text("Logout"), a:has-text("Log Out")'):
                logger.info("Step 2: SSO auto-login detected")
                step.metadata = {"login_performed": False, "already_logged_in": True}
                return

            screenshot = await browser.take_screenshot("login_page_missing")
            page_url = await browser.get_current_url()
            raise RuntimeError(
                f"Login page did not load — no password field found. "
                f"Current URL: {page_url}"
            )

        # Log the actual login page URL for debugging
        login_page_url = await browser.get_current_url()
        logger.info(f"Step 2: On login page: {login_page_url}")

        # Take screenshot BEFORE entering credentials (never capture passwords)
        await browser.take_screenshot("login_page")

        # Fill username (the portal uses email or username field)
        await browser.human_type(
            'input[type="email"], input[name="email"], input#Email, '
            'input[name="username"], input#Username, '
            'input[type="text"]:not([name*="search" i])',
            context.portal_username,
        )
        await browser.human_delay(0.3, 0.8)

        # Fill password
        await browser.human_type(
            'input[type="password"], input[name="password"], input#Password',
            context.portal_password,
        )
        await browser.human_delay(0.3, 0.8)

        # Click Sign In / Log In / Submit
        await browser.human_click(
            'button:has-text("Sign In"), button:has-text("Log In"), '
            'button[type="submit"], input[type="submit"]'
        )
        await browser.human_delay(3.0, 6.0)

        # Wait for redirect back to bizfile
        try:
            await browser.page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass

        post_login_url = await browser.get_current_url()
        logger.info(f"Step 2: Post-login URL: {post_login_url}")

        # Check if we're STILL on the login page (password field visible = login failed)
        still_on_login = await browser.is_visible('input[type="password"]')
        if still_on_login:
            screenshot = await browser.take_screenshot("login_failed")
            raise RuntimeError(
                "Login failed — still on login page after submitting credentials. "
                "Check portal username/password in vault."
            )

        # Give SSO redirect time to complete if needed
        if not await browser.is_visible('a:has-text("Logout"), a:has-text("Log Out")'):
            await browser.human_delay(3.0, 5.0)
            try:
                await browser.page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass

        screenshot = await browser.take_screenshot("logged_in")
        step.metadata = {
            "login_performed": True,
            "login_page_url": login_page_url,
            "post_login_url": post_login_url,
            "screenshot": screenshot,
        }
        logger.info("Step 2: Login completed successfully")

    # ── Step 3: Search for Entity ────────────────────────────────────────

    async def _step_03_search_entity(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info(f"Step 3: Searching for entity {context.entity_number}")

        # IMPORTANT: Do NOT use page.goto() here — we're inside the React SPA
        # after login. A full navigation can destroy the session and trigger an
        # OAuth redirect. Instead, navigate within the SPA if needed.
        current_url = (await browser.get_current_url()).lower()
        if "/search/business" not in current_url:
            # We're not on the search page — click the search link in the SPA nav
            # or use client-side navigation to avoid breaking the session.
            try:
                search_link = await browser.page.query_selector(
                    'a[href*="/search/business"], a:has-text("Business Search"), '
                    'a:has-text("Search")'
                )
                if search_link:
                    await search_link.click()
                    await browser.human_delay(1.5, 3.0)
                    logger.info("Step 3: Navigated to search via SPA link")
                else:
                    # Last resort: use JS to do a soft navigation
                    await browser.page.evaluate(
                        "window.location.href = arguments[0]",
                        self.SEARCH_URL,
                    )
                    await browser.human_delay(2.0, 4.0)
                    logger.info("Step 3: Navigated to search via JS location")
            except Exception as e:
                logger.warning(f"Step 3: SPA navigation failed ({e}), using direct goto")
                await browser.page.goto(
                    self.SEARCH_URL, wait_until="domcontentloaded",
                    timeout=browser.timeout,
                )
                await browser.human_delay(1.0, 2.0)
        else:
            logger.info("Step 3: Already on search page")
            await browser.human_delay(0.5, 1.0)

        # Try to select "Entity Number" search type if dropdown exists
        try:
            if await browser.is_visible('#SearchType, select[name="SearchType"]'):
                await browser.human_select(
                    '#SearchType, select[name="SearchType"]', "NUMBER"
                )
                await browser.human_delay(0.3, 0.6)
        except Exception:
            pass  # Dropdown may not be present

        # Type entity number into search box
        await browser.human_type(
            '#SearchCriteria, input[name="SearchCriteria"], input[type="search"], '
            'input[placeholder*="Search" i]',
            context.entity_number,
        )
        await browser.human_delay(0.5, 1.0)

        # Submit search — press Enter (the search button is an icon, not text)
        await browser.page.keyboard.press("Enter")
        await browser.human_delay(3.0, 5.0)

        # Wait for results to load (SPA renders results without full page nav)
        try:
            await browser.page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass

        # Check if session was lost (redirected to OAuth login)
        post_search_url = await browser.get_current_url()
        if "idm.sos.ca.gov" in post_search_url or "oauth2" in post_search_url:
            raise RuntimeError(
                "Session lost after search — portal redirected to login page. "
                "The portal may have detected automation or the session expired."
            )

        # Verify results loaded
        if await browser.page_contains_text("No results") or \
           await browser.page_contains_text("No records found"):
            raise RuntimeError(
                f"Entity not found: {context.entity_number}. "
                "Verify the entity number is correct."
            )

        screenshot = await browser.take_screenshot("search_results")
        step.metadata = {"entity_number": context.entity_number, "screenshot": screenshot}
        logger.info("Step 3: Search results loaded")

    # ── Step 4: Select Entity & Initiate SOI ─────────────────────────────

    async def _step_04_select_entity_and_file_soi(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info(f"Step 4: Selecting entity '{context.entity_name}' and initiating SOI")

        # The search results use a custom grid with <span class="cell"> elements,
        # NOT <a> links. We need Playwright's native click (not JS .click())
        # to properly trigger the SPA's event handlers and open the detail panel.
        short_name = context.entity_name.split(",")[0].strip()

        # Scroll the search results into view (they're below the fold)
        entity_name_for_scroll = short_name
        entity_num_for_scroll = context.entity_number or ""
        await browser.page.evaluate("""(data) => {
            const cells = document.querySelectorAll('span.cell, [class*="cell"], td, a');
            for (const cell of cells) {
                const text = (cell.textContent || '').toUpperCase();
                if ((data.name && text.includes(data.name)) ||
                    (data.number && text.includes(data.number))) {
                    cell.scrollIntoView({behavior: 'smooth', block: 'center'});
                    return true;
                }
            }
            // Scroll to bottom as fallback
            window.scrollTo(0, document.body.scrollHeight);
            return false;
        }""", {"name": entity_name_for_scroll.upper(), "number": entity_num_for_scroll})
        await browser.human_delay(1.0, 2.0)

        # Use Playwright's native click on the entity name span
        # This triggers proper mouse events for the SPA
        clicked = False
        try:
            # Try clicking span.cell containing entity name
            await browser.page.click(
                f'span.cell:has-text("{short_name}")',
                timeout=10000,
            )
            clicked = True
            logger.info(f"Step 4: Clicked span.cell for '{short_name}'")
        except Exception:
            pass

        if not clicked:
            try:
                # Try clicking any element with entity number text
                await browser.page.click(
                    f'text="{context.entity_number}"',
                    timeout=10000,
                )
                clicked = True
                logger.info(f"Step 4: Clicked element with entity number")
            except Exception:
                pass

        if not clicked:
            try:
                # Try broader text match
                await browser.page.click(
                    f'text="{short_name}"',
                    timeout=10000,
                )
                clicked = True
                logger.info(f"Step 4: Clicked text element for '{short_name}'")
            except Exception:
                raise RuntimeError(
                    f"Could not find entity '{context.entity_name}' in search results"
                )

        # Wait for the entity detail panel/drawer to slide out
        await browser.human_delay(3.0, 5.0)

        # Take screenshot of entity detail panel
        screenshot = await browser.take_screenshot("entity_detail")
        step.metadata = {"entity_detail_screenshot": screenshot}

        # Click "File Statement of Information" icon button in the drawer
        # These are icon buttons with data-tip tooltips, not text buttons
        soi_clicked = False

        # Try data-tip selector first (React tooltip pattern)
        for tip_text in [
            "File Statement of Information",
            "Statement of Information",
            "File SOI",
        ]:
            try:
                selector = f'[data-tip="{tip_text}"] button, button[data-tip="{tip_text}"], [data-tip="{tip_text}"]'
                if await browser.is_visible(selector):
                    await browser.page.click(selector, timeout=5000)
                    soi_clicked = True
                    logger.info(f"Step 4: Clicked button with data-tip='{tip_text}'")
                    break
            except Exception:
                continue

        if not soi_clicked:
            # Try aria-label selector
            for label in ["File Statement of Information", "Statement of Information"]:
                try:
                    selector = f'button[aria-label="{label}"], [aria-label="{label}"]'
                    if await browser.is_visible(selector):
                        await browser.page.click(selector, timeout=5000)
                        soi_clicked = True
                        logger.info(f"Step 4: Clicked button with aria-label='{label}'")
                        break
                except Exception:
                    continue

        if not soi_clicked:
            # Try text-based selectors as last resort
            try:
                await browser.human_click(
                    'a:has-text("File Statement of Information"), '
                    'button:has-text("File Statement of Information"), '
                    'a:has-text("File a Statement"), '
                    'button:has-text("File a Statement")'
                )
                soi_clicked = True
            except Exception:
                pass

        if not soi_clicked:
            screenshot = await browser.take_screenshot("file_soi_not_found")
            current_url = await browser.get_current_url()
            raise RuntimeError(
                "Could not find 'File Statement of Information' button on entity detail page. "
                f"Current URL: {current_url}"
            )

        await browser.human_delay(3.0, 5.0)
        try:
            await browser.page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass

        # Wait for SOI form to begin loading (privacy page or sidebar nav)
        loaded = await browser.page_contains_text("Privacy") or \
            await browser.page_contains_text("Terms") or \
            await browser.page_contains_text("Submitter") or \
            await browser.page_contains_text("Next Step")

        if not loaded:
            # One more wait
            await browser.human_delay(3.0, 5.0)
            loaded = await browser.page_contains_text("Privacy") or \
                await browser.page_contains_text("Next Step")

        if not loaded:
            screenshot = await browser.take_screenshot("soi_form_not_loaded")
            page_url = await browser.get_current_url()
            raise RuntimeError(
                "SOI form did not load after clicking 'File Statement of Information'. "
                f"Current URL: {page_url}"
            )

        step.metadata["soi_initiated"] = True
        logger.info("Step 4: SOI filing form initiated")

    # ── Step 5: Accept Privacy Warning / Terms ───────────────────────────

    async def _step_05_accept_privacy(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 5: Accepting privacy warning and terms")

        # Check if we're already past this page
        if not await browser.page_contains_text("Privacy") and \
           not await browser.page_contains_text("Terms and Conditions"):
            logger.info("Step 5: Privacy page not found — may already be accepted")
            step.metadata = {"skipped": True}
            return

        # Check the agreement checkbox (scope to terms/privacy area)
        # Use JS to click only the checkbox related to privacy/terms, not other checkboxes
        await browser.page.evaluate("""() => {
            const checkboxes = document.querySelectorAll('input[type="checkbox"]');
            for (const cb of checkboxes) {
                if (cb.checked || cb.disabled) continue;
                // Check if nearby text contains terms/privacy/agree keywords
                const parent = cb.closest('label, div, p, li, span');
                const text = (parent?.textContent || '').toLowerCase();
                if (text.includes('agree') || text.includes('privacy') ||
                    text.includes('terms') || text.includes('read')) {
                    cb.click();
                    return true;
                }
            }
            // Fallback: click the first unchecked checkbox on the page
            for (const cb of checkboxes) {
                if (!cb.checked && !cb.disabled) {
                    cb.click();
                    return true;
                }
            }
            return false;
        }""")
        await browser.human_delay(0.5, 1.0)

        # Click "Next Step"
        await self._click_next_step(browser)

        step.metadata = {"terms_accepted": True}
        logger.info("Step 5: Terms accepted, moved to next page")

    # ── Step 6: Fill Submitter Page ──────────────────────────────────────

    async def _step_06_fill_submitter(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 6: Filling submitter information")

        signer = self._get_signer(context)
        signer_name = signer.get("full_name", "")
        signer_email = signer.get("email") or context.portal_username or ""
        signer_phone = signer.get("phone", "")

        # Fill Name field (single combined field per screenshot CA-SOI-011)
        try:
            await browser.human_type(
                'input[name*="Name" i]:not([name*="Entity" i]):not([name*="Corporation" i]), '
                'input[name*="submitter" i], '
                'input[name*="Submitter" i][name*="Name" i]',
                signer_name,
            )
        except Exception:
            logger.warning("Could not fill submitter name field")

        # Fill Email
        if signer_email:
            try:
                await browser.human_type(
                    'input[type="email"], input[name*="email" i], input[name*="Email" i]',
                    signer_email,
                )
            except Exception:
                logger.warning("Could not fill submitter email field")

        # Fill Phone
        if signer_phone:
            try:
                await browser.human_type(
                    'input[name*="phone" i], input[type="tel"], input[name*="Phone" i]',
                    signer_phone,
                )
            except Exception:
                logger.warning("Could not fill submitter phone field")

        await self._click_next_step(browser)

        # Check for validation errors
        errors = await self._detect_form_errors(browser)
        if errors:
            raise RuntimeError(f"Submitter page validation error: {errors}")

        step.metadata = {"submitter_name": signer_name, "submitter_email": signer_email}
        logger.info("Step 6: Submitter page completed")

    # ── Step 7: Verify Entity Details Page ───────────────────────────────

    async def _step_07_verify_entity_details(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 7: Verifying entity details page")

        # This is mostly a read-only page — screenshot and verify entity name
        screenshot = await browser.take_screenshot("entity_details_page")
        step.metadata["entity_details_screenshot"] = screenshot

        # Optionally verify entity name is shown
        if context.entity_name:
            name_visible = await browser.page_contains_text(context.entity_name)
            step.metadata["entity_name_verified"] = name_visible
            if not name_visible:
                logger.warning(
                    f"Entity name '{context.entity_name}' not found on entity details page"
                )

        # Click "Next Step"
        await self._click_next_step(browser)

        logger.info("Step 7: Entity details verified, moved to next page")

    # ── Step 8: Fill Business Addresses ──────────────────────────────────

    async def _step_08_fill_addresses(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 8: Filling business addresses")

        addr = context.principal_address
        mail = context.mailing_address or addr

        # The portal pre-populates addresses from the last filing.
        # Only fill fields that are empty, using JS to check and fill.
        await self._smart_fill_address(browser, addr, section="principal")
        await self._smart_fill_address(browser, mail, section="mailing")

        await self._click_next_step(browser)

        step.metadata = {
            "principal_address": addr.get("street1", ""),
            "mailing_address": mail.get("street1", ""),
        }
        logger.info("Step 8: Addresses filled")

    # ── Step 9: Fill Officers & Directors ─────────────────────────────────

    async def _step_09_fill_officers(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info(f"Step 9: Filling {len(context.officers)} officers/directors")

        # The portal pre-populates officers from the last filing.
        # For a re-filing, officers are already listed in the table.
        # We check if officers are already present and only modify if needed.

        # Check if officer rows already exist
        has_officers = await browser.page.evaluate("""() => {
            // Look for officer rows in the table
            const rows = document.querySelectorAll('tr, .officer-row, [class*="officer"]');
            let count = 0;
            for (const row of rows) {
                const text = (row.textContent || '').trim();
                if (text.length > 10 && !text.includes('Office Name')) count++;
            }
            return count;
        }""")

        if has_officers and has_officers > 0:
            logger.info(f"Step 9: {has_officers} officers already pre-populated, skipping fill")
        else:
            logger.info("Step 9: No pre-populated officers found, attempting to fill")
            # Only try to fill if there are no pre-populated rows
            for officer in context.officers:
                name = officer.get("full_name", "")
                if not name:
                    continue
                try:
                    # Click "Add" to open a new officer row
                    add_btn = browser.page.locator('button:has-text("Add")')
                    if await add_btn.count() > 0:
                        await add_btn.first.click()
                        await browser.human_delay(0.5, 1.0)

                    # Try to fill the name field
                    name_input = browser.page.locator(
                        'input:not([readonly]):not([disabled])'
                    ).filter(has_text="").first
                    if await name_input.count() > 0:
                        await name_input.fill(name)
                except Exception as e:
                    logger.warning(f"Could not add officer {name}: {e}")

        await self._click_next_step(browser)

        step.metadata = {"officers_pre_populated": has_officers or 0}
        logger.info(f"Step 9: Officers page completed")

    # ── Step 10: Fill Agent for Service of Process ───────────────────────

    async def _step_10_fill_agent(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 10: Filling registered agent information")

        agent = context.registered_agent or {}
        agent_type = agent.get("type", "individual").lower()
        agent_name = agent.get("name", "")

        # The agent is usually pre-populated from the last filing.
        # Check if a radio button is already selected and agent info is displayed.
        agent_already_set = await browser.page.evaluate("""() => {
            const radios = document.querySelectorAll('input[type="radio"]');
            for (const r of radios) {
                if (r.checked) return true;
            }
            return false;
        }""")

        if agent_already_set:
            logger.info("Step 10: Agent radio already selected (pre-populated)")
        else:
            if agent_type in ("corporation", "1505", "corporate"):
                try:
                    await browser.human_click(
                        'input[type="radio"][value*="1505"], '
                        'input[type="radio"][value*="Corp" i], '
                        'label:has-text("California Registered Corporate Agent")'
                    )
                    await browser.human_delay(0.5, 1.0)
                except Exception:
                    logger.warning("Could not select corporate agent radio")
            else:
                try:
                    await browser.human_click(
                        'input[type="radio"][value*="Individual" i], '
                        'label:has-text("Individual")'
                    )
                    await browser.human_delay(0.5, 1.0)
                except Exception:
                    pass

        # Ensure the verification checkbox is checked (required for validation).
        # The checkbox says "I certify the selected California Registered Corporate
        # Agent (1505) has agreed to serve as the Agent for Service of Process."
        # This checkbox MUST be checked or the portal will reject the form at
        # final validation and bounce back to this page.

        # Strategy: Try multiple approaches since framework-wrapped checkboxes
        # may not respond to simple JS .click() or Playwright .check().

        # Approach 1: Use Playwright's .check() — but ONLY target the certification checkbox,
        # not all checkboxes on the page (there may be unrelated ones).
        # Find checkboxes near the "certify" text specifically.
        cert_checkbox = browser.page.locator(
            'label:has-text("certify") input[type="checkbox"], '
            'label:has-text("I certify") input[type="checkbox"]'
        )
        cert_count = await cert_checkbox.count()
        if cert_count > 0:
            for i in range(cert_count):
                try:
                    if not await cert_checkbox.nth(i).is_checked():
                        await cert_checkbox.nth(i).check(force=True)
                        await browser.human_delay(0.3, 0.5)
                except Exception as e:
                    logger.warning(f"Step 10: Playwright .check() on cert checkbox {i}: {e}")
        else:
            # Fallback: find unchecked checkboxes near certification text via JS
            unchecked = browser.page.locator('input[type="checkbox"]:not(:checked):not(:disabled)')
            unchecked_count = await unchecked.count()
            if unchecked_count > 0:
                logger.info(f"Step 10: No labeled cert checkbox, trying {unchecked_count} unchecked checkbox(es)")
                for i in range(unchecked_count):
                    try:
                        await unchecked.nth(i).check(force=True)
                        await browser.human_delay(0.3, 0.5)
                    except Exception as e:
                        logger.warning(f"Step 10: Playwright .check() failed for checkbox {i}: {e}")

        # Approach 2: Click the label element (often more reliable with frameworks)
        still_unchecked = await browser.page.locator(
            'input[type="checkbox"]:not(:checked):not(:disabled)'
        ).count()
        if still_unchecked > 0:
            logger.info(f"Step 10: {still_unchecked} still unchecked, trying label click")
            try:
                # Find the label that contains the certification text
                label = browser.page.locator(
                    'label:has-text("certify"), label:has-text("I certify")'
                )
                if await label.count() > 0:
                    await label.first.click()
                    await browser.human_delay(0.5, 1.0)
            except Exception as e:
                logger.warning(f"Step 10: Label click failed: {e}")

        # Approach 3: JS with full event dispatch (change + input events)
        still_unchecked = await browser.page.locator(
            'input[type="checkbox"]:not(:checked):not(:disabled)'
        ).count()
        if still_unchecked > 0:
            logger.info(f"Step 10: {still_unchecked} still unchecked, trying JS with event dispatch")
            await browser.page.evaluate("""() => {
                const checkboxes = document.querySelectorAll('input[type="checkbox"]');
                for (const cb of checkboxes) {
                    if (!cb.checked && !cb.disabled) {
                        cb.checked = true;
                        cb.dispatchEvent(new Event('change', { bubbles: true }));
                        cb.dispatchEvent(new Event('input', { bubbles: true }));
                        cb.dispatchEvent(new Event('click', { bubbles: true }));
                    }
                }
            }""")
            await browser.human_delay(0.5, 1.0)

        # Final verification
        final_unchecked = await browser.page.locator(
            'input[type="checkbox"]:not(:checked):not(:disabled)'
        ).count()
        if final_unchecked > 0:
            logger.error(f"Step 10: CRITICAL — {final_unchecked} checkbox(es) still unchecked after all attempts")
            await browser.take_screenshot("agent_checkbox_failed")
            raise RuntimeError(
                "Could not check the agent certification checkbox. "
                "The portal requires this checkbox to proceed."
            )
        else:
            logger.info("Step 10: All checkboxes verified as checked")

        await browser.take_screenshot("agent_page_filled")
        await self._click_next_step(browser)

        step.metadata = {"agent_type": agent_type, "agent_name": agent_name}
        logger.info("Step 10: Agent information filled")

    # ── Step 11: Fill Type of Business & Email Notifications ─────────────

    async def _step_11_fill_business_type(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 11: Filling type of business and email notifications")

        business_desc = context.business_description or "GENERAL BUSINESS"

        # Check if "Type of Business" field is already filled (pre-populated)
        biz_type_value = await browser.page.evaluate("""() => {
            const inputs = document.querySelectorAll('input[type="text"]:not([type="hidden"])');
            for (const inp of inputs) {
                const rect = inp.getBoundingClientRect();
                // Look for a visible text input in the main content area (y > 100)
                if (rect.width > 200 && rect.height > 0 && rect.y > 100 && rect.y < 300) {
                    return inp.value || '';
                }
            }
            return '';
        }""")

        if biz_type_value:
            logger.info(f"Step 11: Type of Business already filled: '{biz_type_value}'")
        else:
            # Try to fill using JS since CSS selectors may not match React SPA fields
            filled = await browser.page.evaluate(f"""(desc) => {{
                const inputs = document.querySelectorAll('input[type="text"]:not([type="hidden"])');
                for (const inp of inputs) {{
                    const rect = inp.getBoundingClientRect();
                    if (rect.width > 200 && rect.height > 0 && rect.y > 100 && rect.y < 300) {{
                        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value').set;
                        nativeInputValueSetter.call(inp, desc);
                        inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        return true;
                    }}
                }}
                return false;
            }}""", business_desc.upper())
            if filled:
                logger.info(f"Step 11: Filled Type of Business via JS: '{business_desc.upper()}'")
            else:
                logger.warning("Step 11: Could not fill Type of Business field")

        # Email Notifications section
        # The portal has:
        # - Radio: "Yes, I opt in to receive entity notifications via email."
        # - Radio: "No, I do NOT want to receive entity notifications via email."
        # - Email Address* (required if Yes)
        # - Confirm Email Address* (required if Yes)
        #
        # Strategy: Check if "Yes" is already selected. If so, fill email fields.
        # If we can't fill email fields, switch to "No" to avoid validation error.

        signer = self._get_signer(context)
        signer_email = signer.get("email") or context.portal_username or ""

        # Check current opt-in state and find email fields via JS
        email_state = await browser.page.evaluate("""() => {
            const radios = document.querySelectorAll('input[type="radio"]');
            let yesSelected = false;
            let noSelected = false;
            for (const r of radios) {
                const label = r.closest('label')?.textContent || '';
                const nextLabel = r.parentElement?.textContent || '';
                const combined = (label + ' ' + nextLabel).toLowerCase();
                if (combined.includes('opt in') || combined.includes('yes')) {
                    yesSelected = r.checked;
                }
                if (combined.includes('do not') || combined.includes('no,')) {
                    noSelected = r.checked;
                }
            }
            // Find email input fields (visible, in the lower part of page)
            const emailInputs = [];
            const inputs = document.querySelectorAll('input');
            for (const inp of inputs) {
                const rect = inp.getBoundingClientRect();
                if (rect.width > 100 && rect.height > 0 && rect.y > 300) {
                    const placeholder = (inp.placeholder || '').toLowerCase();
                    const name = (inp.name || '').toLowerCase();
                    const type = inp.type || '';
                    if (type === 'email' || name.includes('email') ||
                        placeholder.includes('email') || placeholder.includes('@')) {
                        emailInputs.push({
                            name: inp.name,
                            id: inp.id,
                            type: type,
                            value: inp.value || '',
                            y: Math.round(rect.y),
                            isConfirm: name.includes('confirm') || placeholder.includes('confirm'),
                        });
                    }
                }
            }
            return { yesSelected, noSelected, emailInputs };
        }""")

        logger.info(f"Step 11: Email state: yes={email_state.get('yesSelected')}, "
                     f"no={email_state.get('noSelected')}, "
                     f"email_inputs={len(email_state.get('emailInputs', []))}")

        email_inputs = email_state.get("emailInputs", [])
        yes_selected = email_state.get("yesSelected", False)

        if signer_email and email_inputs:
            # We have email and can find the fields — ensure "Yes" is selected and fill
            if not yes_selected:
                try:
                    await browser.page.evaluate("""() => {
                        const radios = document.querySelectorAll('input[type="radio"]');
                        for (const r of radios) {
                            const text = (r.closest('label')?.textContent || r.parentElement?.textContent || '').toLowerCase();
                            if (text.includes('opt in') || (text.includes('yes') && text.includes('email'))) {
                                r.click();
                                return true;
                            }
                        }
                        return false;
                    }""")
                    await browser.human_delay(0.5, 1.0)
                except Exception:
                    pass

            # Fill email fields via JS (React SPA needs native value setter)
            email_filled = await browser.page.evaluate(f"""(email) => {{
                let filled = 0;
                const inputs = document.querySelectorAll('input');
                for (const inp of inputs) {{
                    const rect = inp.getBoundingClientRect();
                    if (rect.width > 100 && rect.height > 0 && rect.y > 300) {{
                        const name = (inp.name || '').toLowerCase();
                        const type = inp.type || '';
                        const placeholder = (inp.placeholder || '').toLowerCase();
                        if (type === 'email' || name.includes('email') ||
                            placeholder.includes('email') || placeholder.includes('@')) {{
                            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                                window.HTMLInputElement.prototype, 'value').set;
                            nativeInputValueSetter.call(inp, email);
                            inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            filled++;
                        }}
                    }}
                }}
                return filled;
            }}""", signer_email)
            logger.info(f"Step 11: Filled {email_filled} email field(s) via JS")

        elif yes_selected and not email_inputs and not signer_email:
            # "Yes" is selected but we have no email fields visible AND no email to fill
            # Switch to "No" to avoid validation error
            logger.info("Step 11: No email available, switching to 'No' opt-out")
            await browser.page.evaluate("""() => {
                const radios = document.querySelectorAll('input[type="radio"]');
                for (const r of radios) {
                    const text = (r.closest('label')?.textContent || r.parentElement?.textContent || '').toLowerCase();
                    if (text.includes('do not') || (text.includes('no') && text.includes('email'))) {
                        r.click();
                        return true;
                    }
                }
                return false;
            }""")
            await browser.human_delay(0.5, 1.0)

        elif yes_selected and not email_inputs and signer_email:
            # "Yes" selected but can't find email inputs by position heuristic.
            # Try to find ANY empty text/email inputs in the lower half of the page.
            fallback_filled = await browser.page.evaluate(f"""(email) => {{
                let filled = 0;
                const inputs = document.querySelectorAll('input');
                for (const inp of inputs) {{
                    const rect = inp.getBoundingClientRect();
                    if (rect.width > 100 && rect.height > 0 && rect.y > 350 &&
                        !inp.value && !inp.disabled && !inp.readOnly &&
                        (inp.type === 'text' || inp.type === 'email' || inp.type === '')) {{
                        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value').set;
                        nativeInputValueSetter.call(inp, email);
                        inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        filled++;
                    }}
                }}
                return filled;
            }}""", signer_email)
            if fallback_filled > 0:
                logger.info(f"Step 11: Filled {fallback_filled} email field(s) via fallback JS")
            else:
                # Can't fill email — switch to "No" to prevent red X
                logger.warning("Step 11: Cannot find email fields, switching to 'No'")
                await browser.page.evaluate("""() => {
                    const radios = document.querySelectorAll('input[type="radio"]');
                    for (const r of radios) {
                        const text = (r.closest('label')?.textContent || r.parentElement?.textContent || '').toLowerCase();
                        if (text.includes('do not') || (text.includes('no') && text.includes('email'))) {
                            r.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                await browser.human_delay(0.5, 1.0)

        await browser.take_screenshot("business_type_filled")
        await self._click_next_step(browser)

        step.metadata = {"business_description": biz_type_value or business_desc}
        logger.info("Step 11: Business type and email preferences filled")

    # ── Step 12: Fill Labor Judgment ──────────────────────────────────────

    async def _step_12_fill_labor_judgment(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 12: Confirming labor judgment disclosure")

        # The "No" option is typically pre-selected / default per screenshots
        # Verify "No" is selected — if a radio button exists, ensure it's checked
        try:
            no_radio = (
                'input[type="radio"][value*="No" i], '
                'input[type="radio"][value="false"], '
                'label:has-text("No")'
            )
            if await browser.is_visible(no_radio):
                await browser.human_click(no_radio)
                await browser.human_delay(0.3, 0.6)
        except Exception:
            # May already be pre-selected or displayed as text
            pass

        await self._click_next_step(browser)

        step.metadata = {"labor_judgment": "No"}
        logger.info("Step 12: Labor judgment confirmed")

    # ── Step 13: Review and Sign ─────────────────────────────────────────

    async def _step_13_review_and_sign(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 13: Reviewing form and applying e-signature")

        signer = self._get_signer(context)
        signer_name = signer.get("full_name", "")

        # CRITICAL: Verify we are actually on the Review and Signature page.
        # The portal blocks navigation if prior pages (Agent, Type of Business)
        # have validation errors (red X in sidebar).
        on_review_page = await browser.page_contains_text("Electronic Signature") or \
            await browser.page_contains_text("Review and Signature") or \
            await browser.page_contains_text("By signing")

        if not on_review_page:
            logger.warning("Step 13: NOT on Review and Signature page! Attempting sidebar nav.")
            # Try clicking the sidebar nav item to go directly to Review and Signature
            try:
                await browser.page.click(
                    'text="Review and Signature"',
                    timeout=5000,
                )
                await browser.human_delay(2.0, 3.0)
            except Exception:
                pass

            # Check again
            on_review_page = await browser.page_contains_text("Electronic Signature") or \
                await browser.page_contains_text("Review and Signature") or \
                await browser.page_contains_text("By signing")

            if not on_review_page:
                # Check sidebar for red X marks — that means prior pages have errors
                sidebar_errors = await browser.page.evaluate("""() => {
                    const items = document.querySelectorAll('[class*="nav"], [class*="step"], [class*="sidebar"] a, [class*="sidebar"] li');
                    const errors = [];
                    for (const item of items) {
                        const text = (item.textContent || '').trim();
                        const cls = (item.className || '').toString().toLowerCase();
                        // Red X items typically have error/invalid/danger class
                        if (cls.includes('error') || cls.includes('invalid') ||
                            cls.includes('danger') || cls.includes('fail')) {
                            errors.push(text.substring(0, 60));
                        }
                    }
                    return errors;
                }""")
                screenshot = await browser.take_screenshot("not_on_review_page")
                error_msg = "Cannot navigate to Review and Signature page."
                if sidebar_errors:
                    error_msg += f" Sidebar errors on: {', '.join(sidebar_errors)}"
                error_msg += " Prior pages may have validation errors (red X in sidebar)."
                raise RuntimeError(error_msg)

        # Take screenshot of review page
        screenshot = await browser.take_screenshot("review_page")
        step.metadata["review_screenshot"] = screenshot

        # Scroll down to find the Electronic Signature section
        await browser.page.evaluate("""() => {
            // Try to scroll to the signature section
            const sigSection = document.querySelector('[class*="signature" i], [id*="signature" i]');
            if (sigSection) {
                sigSection.scrollIntoView({behavior: 'smooth', block: 'center'});
            } else {
                window.scrollTo(0, document.body.scrollHeight);
            }
        }""")
        await browser.human_delay(0.5, 1.0)

        # Check the affirmation checkbox: "By signing, I affirm that the
        # information herein is true and correct and that I am authorized
        # by California law to sign."
        # Match by label text to avoid clicking unrelated checkboxes.
        affirm_checked = await browser.page.evaluate("""() => {
            // Strategy 1: Find checkbox whose label/parent contains "affirm" or "signing"
            const checkboxes = document.querySelectorAll('input[type="checkbox"]');
            for (const cb of checkboxes) {
                if (cb.checked || cb.disabled) continue;
                // Check the label text (via <label for=>, parent element, or nearby text)
                const label = cb.id ? document.querySelector(`label[for="${cb.id}"]`) : null;
                const parentText = (
                    (label ? label.textContent : '') +
                    (cb.parentElement ? cb.parentElement.textContent : '') +
                    (cb.closest('div, span, td, li') ? cb.closest('div, span, td, li').textContent : '')
                ).toLowerCase();
                if (parentText.includes('affirm') || parentText.includes('signing') ||
                    parentText.includes('true and correct') || parentText.includes('authorized')) {
                    cb.scrollIntoView({behavior: 'smooth', block: 'center'});
                    cb.click();
                    return true;
                }
            }
            // Strategy 2: Find any unchecked checkbox in the Electronic Signature section
            const sigSection = document.querySelector('[class*="signature" i], [id*="signature" i]');
            if (sigSection) {
                const cb = sigSection.querySelector('input[type="checkbox"]:not(:checked):not(:disabled)');
                if (cb) {
                    cb.scrollIntoView({behavior: 'smooth', block: 'center'});
                    cb.click();
                    return true;
                }
            }
            return false;
        }""")
        if affirm_checked:
            logger.info("Step 13: Affirmation checkbox checked")
        else:
            logger.warning("Step 13: Could not find affirmation checkbox — attempting Playwright click")
            try:
                # Last resort: use Playwright to find and click
                affirm_locator = browser.page.locator(
                    'text="By signing, I affirm" >> .. >> input[type="checkbox"]'
                )
                if await affirm_locator.count() > 0:
                    await affirm_locator.first.check()
                    logger.info("Step 13: Affirmation checkbox checked via Playwright locator")
                else:
                    # Try clicking any unchecked checkbox near "affirm" text
                    await browser.human_click('input[type="checkbox"]:not(:checked)')
            except Exception as e:
                logger.error(f"Step 13: Failed to check affirmation checkbox: {e}")
        await browser.human_delay(0.5, 1.0)

        # Click "Add" button to open signature modal (CA-SOI-022).
        # IMPORTANT: The page also has "Save Draft" at the bottom. We need to
        # click the "Add" button specifically in the Electronic Signature section,
        # NOT any "Add" button elsewhere on the page.
        add_clicked = False
        try:
            # Try to find the "Add" button specifically near the signature table
            add_clicked = await browser.page.evaluate("""() => {
                // Look for buttons with "Add" text in the lower part of the page
                const buttons = document.querySelectorAll('button, a.btn, a[role="button"]');
                for (const btn of buttons) {
                    const text = (btn.textContent || '').trim();
                    const rect = btn.getBoundingClientRect();
                    // The "Add" button for signatures should be below the review tables
                    if (text === 'Add' && rect.y > 300 && rect.width > 0 && rect.height > 0) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }""")
        except Exception:
            pass

        if not add_clicked:
            # Fallback: use Playwright click, but avoid buttons at the very bottom
            # where "Save Draft" lives
            try:
                await browser.human_click('button:has-text("Add")')
                add_clicked = True
            except Exception:
                logger.warning("Step 13: Could not click 'Add' button for signature")

        await browser.human_delay(1.5, 3.0)

        # Wait for signature modal to appear.
        # The modal has: Signature* input, Date* input, "Today" button, "Save" button.
        modal_visible = await browser.page.evaluate("""() => {
            // Check for modal/dialog overlay
            const modals = document.querySelectorAll(
                '.modal, dialog, [role="dialog"], [class*="modal"], [class*="dialog"], [class*="popup"]'
            );
            for (const m of modals) {
                const rect = m.getBoundingClientRect();
                if (rect.width > 100 && rect.height > 100) return true;
            }
            // Check for any overlay/backdrop
            const overlays = document.querySelectorAll('[class*="overlay"], [class*="backdrop"]');
            for (const o of overlays) {
                const rect = o.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) return true;
            }
            return false;
        }""")

        if modal_visible:
            logger.info("Step 13: Signature modal detected")
        else:
            logger.warning("Step 13: No modal detected — looking for inline signature form")

        # Fill signature name in the modal.
        # Use JS to find input fields that appeared after clicking "Add".
        sig_filled = await browser.page.evaluate(f"""(name) => {{
            // Try modal inputs first
            const modalInputs = document.querySelectorAll(
                '.modal input[type="text"], dialog input[type="text"], ' +
                '[role="dialog"] input[type="text"], [class*="modal"] input[type="text"]'
            );
            for (const inp of modalInputs) {{
                const rect = inp.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0 && !inp.disabled && !inp.readOnly) {{
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value').set;
                    nativeInputValueSetter.call(inp, name);
                    inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return true;
                }}
            }}
            // Fallback: find any visible text input with "signature" in name/placeholder
            const allInputs = document.querySelectorAll('input[type="text"]');
            for (const inp of allInputs) {{
                const rect = inp.getBoundingClientRect();
                const nameAttr = (inp.name || '').toLowerCase();
                const placeholder = (inp.placeholder || '').toLowerCase();
                if (rect.width > 0 && rect.height > 0 &&
                    (nameAttr.includes('sign') || nameAttr.includes('name') ||
                     placeholder.includes('sign') || placeholder.includes('name')) &&
                    !inp.value) {{
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value').set;
                    nativeInputValueSetter.call(inp, name);
                    inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return true;
                }}
            }}
            return false;
        }}""", signer_name)

        if sig_filled:
            logger.info(f"Step 13: Filled signature name: '{signer_name}'")
        else:
            logger.warning("Step 13: Could not fill signature name via JS, trying Playwright")
            try:
                await browser.human_type(
                    '.modal input[type="text"], dialog input[type="text"], '
                    '[role="dialog"] input[type="text"], '
                    'input[name*="Signature" i], input[name*="signer" i]',
                    signer_name,
                )
                sig_filled = True
            except Exception:
                await browser.take_screenshot("signature_name_failed")
                raise RuntimeError(
                    "Could not fill the electronic signature name field. "
                    "The filing cannot be submitted without a valid e-signature."
                )

        # Click "Today" button for date auto-fill (inside the modal)
        try:
            await browser.page.evaluate("""() => {
                const buttons = document.querySelectorAll('button, a');
                for (const btn of buttons) {
                    const text = (btn.textContent || '').trim().toLowerCase();
                    if (text === 'today') {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }""")
            await browser.human_delay(0.3, 0.6)
        except Exception:
            pass

        # Click "Save" INSIDE the modal — NOT "Save Draft" at page bottom.
        # This is critical: "Save Draft" is always visible at the bottom of every page.
        # We must only click the "Save" button that belongs to the signature modal.
        save_clicked = await browser.page.evaluate("""() => {
            // Strategy 1: Find "Save" button inside a modal container
            const modalContainers = document.querySelectorAll(
                '.modal, dialog, [role="dialog"], [class*="modal"], [class*="dialog"], [class*="popup"]'
            );
            for (const modal of modalContainers) {
                const buttons = modal.querySelectorAll('button, a.btn');
                for (const btn of buttons) {
                    const text = (btn.textContent || '').trim().toLowerCase();
                    if (text === 'save' || text === 'submit' || text === 'ok') {
                        btn.click();
                        return 'modal_save';
                    }
                }
            }
            // Strategy 2: Find a "Save" button that is NOT "Save Draft"
            const allButtons = document.querySelectorAll('button, a.btn');
            for (const btn of allButtons) {
                const text = (btn.textContent || '').trim();
                const lowerText = text.toLowerCase();
                if (lowerText === 'save' && !lowerText.includes('draft')) {
                    const rect = btn.getBoundingClientRect();
                    // "Save Draft" is typically at the bottom-left of the page
                    // Modal "Save" would be in the center or center-right
                    if (rect.x > 200 || rect.y < 500) {
                        btn.click();
                        return 'positioned_save';
                    }
                }
            }
            return null;
        }""")

        if save_clicked:
            logger.info(f"Step 13: Clicked Save via {save_clicked}")
        else:
            logger.warning("Step 13: Could not find modal Save, trying Playwright with scoped selector")
            try:
                # Last resort: try to click a Save that's not Save Draft
                await browser.page.click(
                    '.modal button:has-text("Save"), dialog button:has-text("Save"), '
                    '[role="dialog"] button:has-text("Save")',
                    timeout=5000,
                )
            except Exception:
                logger.error("Step 13: Failed to click Save in signature modal")

        await browser.human_delay(2.0, 3.0)

        # Verify signature was added (modal closed, signature row visible)
        sig_screenshot = await browser.take_screenshot("after_signature")
        step.metadata["signature_screenshot"] = sig_screenshot

        # Verify we can see the signature in the table
        sig_added = await browser.page_contains_text(signer_name) if signer_name else True
        step.metadata["signature_verified"] = sig_added
        if not sig_added:
            logger.warning("Step 13: Signer name not found on page after saving signature")

        # Click "Next Step"
        await self._click_next_step(browser)

        step.metadata["signed"] = True
        step.metadata["signer"] = signer_name
        logger.info(f"Step 13: E-signature applied by {signer_name}")

    # ── Step 14: Review Processing Fees ──────────────────────────────────

    async def _step_14_review_fees(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info("Step 14: Reviewing processing fees")

        # Determine expected fee
        entity_type = (context.entity_type or "").lower()
        if "llc" in entity_type:
            expected_fee = self.FEES["llc"]
            fee_display = "$20.00"
        elif "nonprofit" in entity_type:
            expected_fee = self.FEES["nonprofit"]
            fee_display = "$25.00"
        else:
            expected_fee = self.FEES["corporation"]
            fee_display = "$25.00"

        screenshot = await browser.take_screenshot("processing_fees")
        step.metadata = {
            "fee_screenshot": screenshot,
            "expected_fee_cents": expected_fee,
            "fee_display": fee_display,
        }

        # Leave "Certified Copy" unchecked (default)
        # Click "Next Step"
        await self._click_next_step(browser)

        logger.info(f"Step 14: Fee review complete — {fee_display}")

    # ── Step 15: Handle Payment ──────────────────────────────────────────

    async def _step_15_handle_payment(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        logger.info(f"Step 15: Handling payment (tier: {context.payment_tier})")

        settings = get_settings()

        # Determine payment path
        if context.payment_tier == "we_handle" and settings.SENSFIX_CARD_NUMBER:
            # Option 3: We handle payment with Sensfix card
            await self._pay_with_card(step, context, browser, settings)

        elif context.payment_tier == "customer_pays":
            # Signal payment needed — orchestrator decides path 1a vs 1b
            # based on whether cockpit is active
            step.requires_payment = True
            step.metadata = {
                "action": "awaiting_payment_decision",
                "message": "Form is complete. Payment required.",
                "draft_save_available": context.draft_save_available,
            }
            logger.info("Step 15: Payment required — orchestrator will decide path")

        elif context.payment_tier == "we_handle" and not settings.SENSFIX_CARD_NUMBER:
            # Option 3 fallback: card not configured, try draft save
            logger.warning("SENSFIX_CARD_NUMBER not configured, falling back to draft save")
            if context.draft_save_available:
                await self._save_draft(step, context, browser)
            else:
                step.requires_payment = True
                step.metadata = {
                    "action": "awaiting_cockpit_payment",
                    "message": "Card not configured and no draft save. Please pay in cockpit.",
                }

        else:
            # Fallback for any other tier (customer_card, etc.)
            step.requires_payment = True
            step.metadata = {
                "action": "awaiting_cockpit_payment",
                "message": "Please complete payment in the cockpit.",
            }
            logger.info(f"Step 15: Unknown tier '{context.payment_tier}', pausing for cockpit")

    async def _save_draft(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        """Save the filing as a draft (Option 1a)."""
        logger.info("Step 15: Saving draft")
        await browser.human_click(
            'button:has-text("Save Draft"), a:has-text("Save Draft")'
        )
        await browser.human_delay(2.0, 4.0)

        # Verify draft saved
        draft_saved = await browser.page_contains_text("saved") or \
            await browser.page_contains_text("draft") or \
            await browser.page_contains_text("Draft")

        self._last_step_15_action = "draft_saved"
        step.metadata = {
            "action": "draft_saved",
            "draft_confirmed": draft_saved,
        }
        logger.info("Step 15: Draft saved — engine stopping, customer pays later")

    async def _pay_with_card(
        self, step: FilingStep, context: FilingContext, browser: Any, settings: Any
    ):
        """Handle payment with corporate card (Option 3)."""
        card_last4 = settings.SENSFIX_CARD_NUMBER[-4:] if settings.SENSFIX_CARD_NUMBER else "????"
        logger.info(f"Step 15: Paying with corporate card ending in {card_last4}")

        # Click "File Online >" button
        await browser.human_click(
            'button:has-text("File Online"), a:has-text("File Online")'
        )
        await browser.human_delay(2.0, 4.0)

        # Wait for cart sidebar (CA-SOI-027)
        await browser.human_click(
            'button:has-text("Pay with Credit Card"), '
            'a:has-text("Pay with Credit Card"), '
            'button:has-text("Pay With Credit Card")'
        )
        await browser.human_delay(2.0, 4.0)

        # Fill payment form fields (CA-SOI-028)
        # Credit Card Number
        await browser.human_type(
            'input[name*="CardNumber" i], input[name*="card_number" i], '
            'input[name*="creditCard" i], input[autocomplete="cc-number"]',
            settings.SENSFIX_CARD_NUMBER,
        )
        await browser.human_delay(0.2, 0.5)

        # Expiration Date
        if settings.SENSFIX_CARD_EXPIRY:
            try:
                await browser.human_type(
                    'input[name*="Expir" i], input[name*="expir" i], '
                    'input[name*="ExpDate" i], input[autocomplete="cc-exp"], '
                    'input[placeholder*="MM" i]',
                    settings.SENSFIX_CARD_EXPIRY,
                )
                await browser.human_delay(0.2, 0.5)
            except Exception:
                logger.warning("Could not fill card expiration date field")

        # CVV / Security Code
        if settings.SENSFIX_CARD_CVV:
            try:
                await browser.human_type(
                    'input[name*="CVV" i], input[name*="cvv" i], '
                    'input[name*="SecurityCode" i], input[name*="security" i], '
                    'input[name*="CVC" i], input[autocomplete="cc-csc"]',
                    settings.SENSFIX_CARD_CVV,
                )
                await browser.human_delay(0.2, 0.5)
            except Exception:
                logger.warning("Could not fill card CVV field")

        # Billing Address
        if settings.SENSFIX_CARD_BILLING_ADDRESS:
            await browser.human_type(
                'input[name*="BillingAddress" i], input[name*="billing" i][name*="address" i], '
                'input[name*="Address" i]',
                settings.SENSFIX_CARD_BILLING_ADDRESS,
            )
            await browser.human_delay(0.2, 0.5)

        # Ste/Apt/Fl
        if settings.SENSFIX_CARD_BILLING_SUITE:
            try:
                await browser.human_type(
                    'input[name*="Suite" i], input[name*="Ste" i], input[name*="Apt" i]',
                    settings.SENSFIX_CARD_BILLING_SUITE,
                )
            except Exception:
                pass

        # City
        if settings.SENSFIX_CARD_BILLING_CITY:
            await browser.human_type(
                'input[name*="City" i]',
                settings.SENSFIX_CARD_BILLING_CITY,
            )
            await browser.human_delay(0.2, 0.5)

        # State
        if settings.SENSFIX_CARD_BILLING_STATE:
            try:
                await browser.human_select(
                    'select[name*="State" i]',
                    settings.SENSFIX_CARD_BILLING_STATE,
                )
            except Exception:
                try:
                    await browser.human_type(
                        'input[name*="State" i]',
                        settings.SENSFIX_CARD_BILLING_STATE,
                    )
                except Exception:
                    pass

        # Zip Code
        if settings.SENSFIX_CARD_BILLING_ZIP:
            await browser.human_type(
                'input[name*="Zip" i]',
                settings.SENSFIX_CARD_BILLING_ZIP,
            )
            await browser.human_delay(0.2, 0.5)

        # Phone Number
        if settings.SENSFIX_CARD_PHONE:
            try:
                await browser.human_type(
                    'input[name*="Phone" i], input[type="tel"]',
                    settings.SENSFIX_CARD_PHONE,
                )
            except Exception:
                pass

        # Take screenshot before submitting payment
        await browser.take_screenshot("payment_form_filled")

        # Click "Submit Payment"
        await browser.human_click(
            'button:has-text("Submit Payment"), '
            'input[value*="Submit" i][value*="Payment" i], '
            'button:has-text("Submit")'
        )
        await browser.human_delay(5.0, 10.0)

        # Verify payment success
        success = await browser.page_contains_text("Payment Successful") or \
            await browser.page_contains_text("payment successful") or \
            await browser.page_contains_text("Transaction Approved") or \
            await browser.page_contains_text("DOWNLOAD RECEIPT")

        if not success:
            # Check for payment errors (specific phrases, not generic "error")
            if await browser.page_contains_text("declined") or \
               await browser.page_contains_text("Declined") or \
               await browser.page_contains_text("payment failed") or \
               await browser.page_contains_text("transaction failed") or \
               await browser.page_contains_text("card was declined"):
                raise RuntimeError("Payment was declined or encountered an error")
            logger.warning("Could not confirm payment success — proceeding cautiously")

        step.metadata = {
            "action": "card_payment",
            "payment_confirmed": success,
        }
        logger.info("Step 15: Card payment submitted")

    # ── Step 16: Confirm Filing & Download Receipt ───────────────────────

    async def _step_16_confirm_and_download(
        self, step: FilingStep, context: FilingContext, browser: Any
    ):
        # If Step 15 saved a draft, skip this step
        if self._last_step_15_action == "draft_saved":
            logger.info("Step 16: Skipping — draft was saved in Step 15")
            step.status = "skipped"
            step.metadata = {"skipped": True, "reason": "draft_saved"}
            return

        logger.info("Step 16: Confirming filing and downloading receipt")

        # Wait for success page
        success = await browser.page_contains_text("Payment Successful") or \
            await browser.page_contains_text("DOWNLOAD RECEIPT") or \
            await browser.page_contains_text("Filed Successfully")

        if not success:
            await browser.human_delay(3.0, 5.0)
            success = await browser.page_contains_text("Payment Successful") or \
                await browser.page_contains_text("DOWNLOAD RECEIPT")

        # Extract confirmation number from visible page text (not HTML source)
        confirmation_number = None
        try:
            page_text = await browser.page.evaluate("() => document.body.innerText")
            # Look for common patterns: filing number, confirmation, entity number
            patterns = [
                r'(?:Filing|Confirmation|Transaction)\s*(?:Number|No\.?|#)\s*[:.]?\s*([A-Z0-9-]+)',
                r'(?:Document|File)\s*(?:Number|No\.?)\s*[:.]?\s*([A-Z0-9-]+)',
            ]
            for pattern in patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    confirmation_number = match.group(1)
                    break
        except Exception:
            pass

        # Download receipt
        try:
            await browser.human_click(
                'a:has-text("DOWNLOAD RECEIPT"), a:has-text("Download Receipt")'
            )
            await browser.human_delay(2.0, 4.0)
        except Exception:
            logger.warning("Could not click DOWNLOAD RECEIPT link")

        # Download filed form (green button)
        try:
            await browser.human_click(
                'a:has-text("Form"), button:has-text("Form")'
            )
            await browser.human_delay(2.0, 4.0)
        except Exception:
            logger.warning("Could not download filed form")

        # Download acknowledgment (green button)
        try:
            await browser.human_click(
                'a:has-text("Business Entity Filing Acknowledgment"), '
                'a:has-text("Acknowledgment")'
            )
            await browser.human_delay(2.0, 4.0)
        except Exception:
            logger.warning("Could not download acknowledgment")

        # Final screenshot
        final_screenshot = await browser.take_screenshot("filing_complete")

        if not confirmation_number:
            logger.warning(
                "Step 16: No confirmation number found on page. "
                "The filing may have succeeded — check the screenshot for manual verification."
            )

        step.metadata = {
            "confirmation_number": confirmation_number,
            "filing_complete": True,
            "final_screenshot": final_screenshot,
            "confirmation_verified": confirmation_number is not None,
        }
        logger.info(f"Step 16: Filing confirmed — confirmation: {confirmation_number}")

    # ── Helper methods ───────────────────────────────────────────────────

    async def _click_next_step(self, browser: Any):
        """Click the 'Next Step' button and wait for page transition."""
        # Capture the current sidebar active item before clicking
        current_page = await browser.page.evaluate("""() => {
            // The active/current sidebar item has a highlighted class
            const items = document.querySelectorAll(
                '[class*="active"], [class*="current"], [class*="selected"]'
            );
            for (const item of items) {
                const rect = item.getBoundingClientRect();
                if (rect.x < 250 && rect.y > 50) {
                    return (item.textContent || '').trim().substring(0, 50);
                }
            }
            return '';
        }""")

        await browser.human_click(
            'button:has-text("Next Step"), a:has-text("Next Step"), '
            'input[value="Next Step"]'
        )
        await browser.human_delay(1.5, 2.5)

        # Check if page actually transitioned by comparing sidebar active item
        new_page = await browser.page.evaluate("""() => {
            const items = document.querySelectorAll(
                '[class*="active"], [class*="current"], [class*="selected"]'
            );
            for (const item of items) {
                const rect = item.getBoundingClientRect();
                if (rect.x < 250 && rect.y > 50) {
                    return (item.textContent || '').trim().substring(0, 50);
                }
            }
            return '';
        }""")

        if current_page and new_page and current_page == new_page:
            # Check for visible validation errors on the page
            error_text = await browser.page.evaluate("""() => {
                const selectors = [
                    '.error', '.validation-error', '.text-danger',
                    '[role="alert"]', '.field-validation-error',
                    '.has-error', '.is-invalid', '.error-message',
                    '[class*="error"]:not(svg):not(path)',
                ];
                const errors = [];
                for (const sel of selectors) {
                    for (const el of document.querySelectorAll(sel)) {
                        const text = (el.textContent || '').trim();
                        if (text && text.length < 200 && el.offsetParent !== null) {
                            errors.push(text);
                        }
                    }
                }
                return errors.join('; ').substring(0, 500);
            }""")
            await browser.take_screenshot("next_step_blocked")
            error_detail = f" Errors: {error_text}" if error_text else ""
            logger.error(
                f"Next Step did NOT navigate — still on '{current_page}'.{error_detail}"
            )
            raise RuntimeError(
                f"Portal validation blocked navigation from '{current_page}'. "
                f"The form has errors that must be resolved.{error_detail}"
            )

    async def _check_session_and_relogin(
        self, context: FilingContext, browser: Any
    ):
        """Check for session expiry and attempt re-login if needed."""
        if not await browser.detect_session_expired():
            return

        if self._relogin_count >= self.MAX_RELOGIN_ATTEMPTS:
            raise RuntimeError(
                f"Session expired and max re-login attempts ({self.MAX_RELOGIN_ATTEMPTS}) reached"
            )

        logger.warning("Session expired — attempting re-login")
        self._relogin_count += 1

        # Reload the current page — portal will redirect to login if needed
        await browser.page.reload(wait_until="domcontentloaded")
        await browser.human_delay(2.0, 3.0)

        # Check if redirected to login page
        if await browser.is_visible('input[type="password"]'):
            # Fill credentials
            await browser.human_type(
                'input[name="username"], input#Username, input[name="email"], '
                'input[type="email"], input[type="text"]:not([name*="search" i])',
                context.portal_username,
            )
            await browser.human_type(
                'input[name="password"], input#Password, input[type="password"]',
                context.portal_password,
            )
            await browser.human_click(
                'button:has-text("Sign In"), button:has-text("Log In"), button[type="submit"]'
            )
            await browser.human_delay(3.0, 5.0)

            # Verify re-login — check if still on login page
            if await browser.is_visible('input[type="password"]'):
                raise RuntimeError("Re-login failed after session expiry")

        logger.info("Session recovered — re-login successful")

    async def _detect_form_errors(self, browser: Any) -> Optional[str]:
        """Check for portal validation errors after form submission."""
        error_selectors = [
            '.error', '.validation-error', '.text-danger',
            '[role="alert"]', '.field-validation-error',
            '.alert-danger', '.error-message',
        ]
        for selector in error_selectors:
            try:
                if await browser.is_visible(selector):
                    error_text = await browser.get_text(selector)
                    if error_text:
                        return error_text
            except Exception:
                pass
        return None

    def _get_signer(self, context: FilingContext) -> dict:
        """Find the designated signer from officers list."""
        # First: officer with is_signer=True
        for officer in context.officers:
            if officer.get("is_signer"):
                return officer

        # Fallback: CEO or President
        for officer in context.officers:
            title = officer.get("title", "").lower()
            if "ceo" in title or "president" in title or "chief executive" in title:
                return officer

        # Fallback: first officer
        if context.officers:
            return context.officers[0]

        return {"full_name": "", "email": "", "phone": ""}

    async def _smart_fill_address(
        self, browser: Any, addr: dict, section: str = "principal"
    ):
        """
        Smart address fill: uses JS to check if fields are already populated
        (common for re-filings) and only fills empty fields.

        The bizfile portal has two address blocks on the Business Addresses page:
        - "Street Address of Principal Office" (top half)
        - "Mailing Address of Corporation" (bottom half)

        Each block has: Address*, STE/APT/FL, Address Continued, City*, State*, ZIP Code*, Country*
        """
        street1 = addr.get("street1", "")
        street2 = addr.get("street2", "")
        city = addr.get("city", "")
        state = addr.get("state", "CA")
        zip_code = addr.get("zip", "")

        # Use page position to distinguish principal vs mailing sections.
        # Principal address is in the top half, mailing in the bottom half.
        # We use a y-threshold to separate them.
        if section == "mailing":
            y_min = 350  # Mailing section starts below this y-coordinate
            y_max = 9999
        else:
            y_min = 0
            y_max = 400  # Principal section ends around here

        # Check which fields are empty and fill them via JS
        result = await browser.page.evaluate(f"""(data) => {{
            const filled = [];
            const inputs = document.querySelectorAll('input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"])');
            const selects = document.querySelectorAll('select');

            // Collect all form fields with their positions
            const fields = [];
            for (const el of [...inputs, ...selects]) {{
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0 && rect.y >= data.yMin && rect.y < data.yMax) {{
                    fields.push({{
                        el: el,
                        tag: el.tagName,
                        name: (el.name || '').toLowerCase(),
                        placeholder: (el.placeholder || '').toLowerCase(),
                        value: el.value || '',
                        y: rect.y,
                        x: rect.x,
                        w: rect.width,
                    }});
                }}
            }}

            // Sort by y position then x
            fields.sort((a, b) => a.y - b.y || a.x - b.x);

            const nativeSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value')?.set;

            function fillField(field, value) {{
                if (!value || field.value) return false;  // Skip if already filled or no value
                if (field.tag === 'SELECT') {{
                    // For selects, find matching option
                    const options = field.el.querySelectorAll('option');
                    for (const opt of options) {{
                        if (opt.value === value || opt.textContent.trim().toUpperCase().includes(value.toUpperCase())) {{
                            field.el.value = opt.value;
                            field.el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            return true;
                        }}
                    }}
                    return false;
                }} else {{
                    if (nativeSetter) {{
                        nativeSetter.call(field.el, value);
                    }} else {{
                        field.el.value = value;
                    }}
                    field.el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    field.el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return true;
                }}
            }}

            // Map fields to address components by position order:
            // Field 0: Address (wide input, first in section)
            // Field 1: STE/APT/FL (second text input)
            // Field 2: Address Continued (third text input, or may not exist)
            // Then: City, State (dropdown), ZIP Code, Country (dropdown)
            let fieldIndex = 0;
            for (const f of fields) {{
                if (f.tag === 'INPUT') {{
                    if (fieldIndex === 0 && f.w > 200) {{
                        if (fillField(f, data.street1)) filled.push('street1');
                        fieldIndex++;
                    }} else if (fieldIndex === 1) {{
                        if (fillField(f, data.street2)) filled.push('street2');
                        fieldIndex++;
                    }} else if (fieldIndex >= 2) {{
                        // Could be Address Continued, City, or ZIP
                        const name = f.name;
                        if (name.includes('city')) {{
                            if (fillField(f, data.city)) filled.push('city');
                        }} else if (name.includes('zip') || name.includes('postal')) {{
                            if (fillField(f, data.zip)) filled.push('zip');
                        }} else if (f.w > 200) {{
                            // Likely Address Continued — skip
                            fieldIndex++;
                        }} else {{
                            // Try to determine by width: City is typically wider than ZIP
                            if (f.w > 150 && !filled.includes('city')) {{
                                if (fillField(f, data.city)) filled.push('city');
                            }} else if (!filled.includes('zip')) {{
                                if (fillField(f, data.zip)) filled.push('zip');
                            }}
                        }}
                        fieldIndex++;
                    }}
                }} else if (f.tag === 'SELECT') {{
                    // Dropdowns: State comes before Country
                    const name = f.name;
                    if (name.includes('state') && !filled.includes('state')) {{
                        if (fillField(f, data.state)) filled.push('state');
                    }} else if (name.includes('country') && !filled.includes('country')) {{
                        // Leave country as-is (usually "United States")
                    }} else if (!filled.includes('state')) {{
                        if (fillField(f, data.state)) filled.push('state');
                    }}
                }}
            }}

            return {{ filled: filled, totalFields: fields.length }};
        }}""", {
            "street1": street1,
            "street2": street2,
            "city": city,
            "state": state,
            "zip": zip_code,
            "yMin": y_min,
            "yMax": y_max,
        })

        filled = result.get("filled", [])
        total = result.get("totalFields", 0)
        if filled:
            logger.info(f"Step 8: Filled {len(filled)} empty {section} fields: {filled}")
        else:
            logger.info(f"Step 8: All {total} {section} address fields already populated")

    async def _fill_address_section(
        self, browser: Any, addr: dict, section: str = "principal"
    ):
        """
        Fill a set of address fields.
        section: 'principal', 'mailing', or 'agent'
        """
        street1 = addr.get("street1", "")
        street2 = addr.get("street2", "")
        city = addr.get("city", "")
        state = addr.get("state", "CA")
        zip_code = addr.get("zip", "")
        country = addr.get("country", "US")

        if section == "mailing":
            name_filter = '[name*="mail" i], [name*="Mail" i]'
        elif section == "agent":
            name_filter = '[name*="agent" i], [name*="Agent" i]'
        else:
            name_filter = ':not([name*="mail" i]):not([name*="Mail" i]):not([name*="agent" i])'

        # Street address
        if street1:
            try:
                await browser.human_type(
                    f'input[name*="Address" i]{name_filter}',
                    street1,
                )
            except Exception:
                # Fallback: try broader selector
                try:
                    await browser.human_type(
                        'input[name*="Address" i]', street1,
                    )
                except Exception:
                    logger.warning(f"Could not fill {section} street address")

        # Suite/Apt
        if street2:
            try:
                await browser.human_type(
                    f'input[name*="Suite" i]{name_filter}, '
                    f'input[name*="Ste" i]{name_filter}, '
                    f'input[name*="Apt" i]{name_filter}',
                    street2,
                )
            except Exception:
                pass

        # City
        if city:
            try:
                await browser.human_type(
                    f'input[name*="City" i]{name_filter}',
                    city,
                )
            except Exception:
                logger.warning(f"Could not fill {section} city")

        # State dropdown
        if state:
            try:
                await browser.human_select(
                    f'select[name*="State" i]{name_filter}',
                    state,
                )
            except Exception:
                try:
                    await browser.human_type(
                        f'input[name*="State" i]{name_filter}',
                        state,
                    )
                except Exception:
                    logger.warning(f"Could not fill {section} state")

        # ZIP Code
        if zip_code:
            try:
                await browser.human_type(
                    f'input[name*="Zip" i]{name_filter}',
                    zip_code,
                )
            except Exception:
                logger.warning(f"Could not fill {section} ZIP code")

        # Country dropdown
        if country:
            try:
                await browser.human_select(
                    f'select[name*="Country" i]{name_filter}',
                    country,
                )
            except Exception:
                pass  # Country may not be present or may default to US

    def _format_address_line(self, address: dict) -> str:
        """Format address dict into a single-line string."""
        parts = []
        if address.get("street1"):
            parts.append(address["street1"])
        if address.get("street2"):
            parts.append(address["street2"])
        if address.get("city"):
            parts.append(address["city"])
        if address.get("state"):
            parts.append(address["state"])
        if address.get("zip"):
            parts.append(address["zip"])
        return ", ".join(parts)

    def _map_title_to_position(self, title: str) -> str:
        """Map officer title string to portal position dropdown value."""
        title_lower = title.lower()
        if "president" in title_lower:
            return "PRESIDENT"
        elif "ceo" in title_lower or "chief executive" in title_lower:
            return "CEO"
        elif "cfo" in title_lower or "chief financial" in title_lower:
            return "CFO"
        elif "treasurer" in title_lower:
            return "TREASURER"
        elif "secretary" in title_lower:
            return "SECRETARY"
        elif "director" in title_lower:
            return "DIRECTOR"
        elif "manager" in title_lower:
            return "MANAGER"
        elif "member" in title_lower:
            return "MEMBER"
        else:
            return title.upper()


# ── Auto-register ────────────────────────────────────────────────────────

register_filer("ca_soi", CaliforniaSOIFiler)
register_filer("ca_soi_corp", CaliforniaSOIFiler)
register_filer("ca_soi_llc", CaliforniaSOIFiler)
