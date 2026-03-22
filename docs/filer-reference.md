# Filer API Reference

## BaseStateFiler

Abstract base class. Set `STATE_CODE`, `FILING_CODE`, `PORTAL_URL`, `TOTAL_STEPS`.
Implement `get_steps()`, `execute_step()`. Override `pre_flight_check()` for validation.

## FilingStep

Fields: `number`, `name`, `description`, `is_page_transition`, `expected_page`, `is_payment_step`, `requires_user_input`, `metadata`.

## FilingContext

Fields: `entity_name`, `entity_number`, `entity_type`, `principal_address`, `officers`, `portal_username`, `portal_password`, `portal_extra`, `payment_tier`, `business_data`.

## BrowserEngine

Methods: `navigate()`, `human_type()`, `human_click()`, `human_select()`, `human_delay()`, `take_screenshot()`, `get_text()`, `get_value()`, `is_visible()`, `page_contains_text()`, `detect_session_expired()`, `detect_error_page()`, `detect_captcha()`.
