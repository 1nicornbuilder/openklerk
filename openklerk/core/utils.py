"""
Shared utilities for state filing modules.
"""
import logging
from typing import Any, Optional

logger = logging.getLogger("openklerk")


def split_name(full_name: str) -> tuple[str, str]:
    """Split 'John Smith' into ('John', 'Smith'). Handles middle names."""
    parts = full_name.strip().split()
    if len(parts) == 0:
        return ("", "")
    elif len(parts) == 1:
        return (parts[0], "")
    else:
        return (parts[0], " ".join(parts[1:]))


def format_address_line(address: dict) -> str:
    """Format address dict to single line: '123 Main St, San Jose, CA 95131'."""
    parts = []
    street = address.get("street1", "")
    street2 = address.get("street2", "")
    if street:
        parts.append(street)
    if street2:
        parts.append(street2)
    city = address.get("city", "")
    state = address.get("state", "")
    zip_code = address.get("zip", "")
    if city:
        city_part = city
        if state:
            city_part += f", {state}"
        if zip_code:
            city_part += f" {zip_code}"
        parts.append(city_part)
    elif state or zip_code:
        parts.append(f"{state} {zip_code}".strip())
    return ", ".join(parts)


def get_signer(officers: list[dict]) -> dict:
    """Find the designated signer from officers list."""
    for officer in officers:
        if officer.get("is_signer"):
            return officer
    for officer in officers:
        title = officer.get("title", "").lower()
        if "ceo" in title or "president" in title or "chief executive" in title:
            return officer
    if officers:
        return officers[0]
    return {"full_name": "", "email": "", "phone": ""}


async def detect_form_errors(browser: Any) -> Optional[str]:
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


async def safe_click(browser: Any, selector: str, timeout: int = 5000) -> bool:
    """Try to click an element, return True if successful."""
    try:
        if await browser.is_visible(selector):
            await browser.page.click(selector, timeout=timeout)
            return True
    except Exception:
        pass
    return False


async def wait_for_navigation(browser: Any, timeout: int = 15000):
    """Wait for page navigation to complete."""
    try:
        await browser.page.wait_for_load_state("domcontentloaded", timeout=timeout)
    except Exception:
        pass
