"""
OpenKlerk -- Intelligent Filing Assistant

Multi-backend LLM service for page analysis, exception diagnosis,
and user interaction during automated filing.
"""
import asyncio
import json
import logging
import re
from typing import Optional

from openklerk.intelligence.models import (
    PageAnalysisContext,
    PageAnalysisResult,
    ExceptionAnalysisResult,
    UserResponseResult,
    AuditResult,
    AuditIssue,
)
from openklerk.intelligence.prompts import (
    OPENKLERK_SYSTEM_PROMPT,
    ANALYZE_PAGE_PROMPT,
    HANDLE_EXCEPTION_PROMPT,
    RESPOND_TO_USER_PROMPT,
    RECALIBRATE_PROMPT,
    ADVERSARIAL_AUDIT_PROMPT,
)

logger = logging.getLogger("openklerk")


def _strip_json_wrapper(text: str) -> str:
    """Strip markdown code fences and preamble from LLM response."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        text = text[first_brace : last_brace + 1]
    return text.strip()


def get_openklerk_service(backend: str = "google", **kwargs) -> "OpenKlerkService":
    """Factory function to get an OpenKlerk service with the specified backend."""
    from openklerk.intelligence.backends import get_backend
    llm_backend = get_backend(backend, **kwargs)
    return OpenKlerkService(llm_backend=llm_backend, **kwargs)


class OpenKlerkService:
    """
    Provides page analysis, exception diagnosis, and user-facing
    message generation for the filing engine.
    """

    def __init__(
        self,
        llm_backend=None,
        enabled: bool = True,
        analysis_timeout: int = 15,
        confidence_threshold: float = 0.7,
        **kwargs,
    ):
        self.llm_backend = llm_backend
        self.enabled = enabled
        self.analysis_timeout = analysis_timeout
        self.confidence_threshold = confidence_threshold

    async def analyze_page(
        self, screenshot: bytes, context: PageAnalysisContext,
    ) -> PageAnalysisResult:
        """Analyze a browser screenshot in the context of the current filing step."""
        if not self.enabled:
            return PageAnalysisResult(
                page_matches_expected=True,
                recommendation="proceed",
                user_message="Proceeding with next step.",
                reasoning="OpenKlerk disabled -- auto-proceeding.",
            )

        system_prompt = OPENKLERK_SYSTEM_PROMPT.format(
            filing_type=context.filing_type,
            entity_name=context.entity_name,
            portal_name=context.portal_name,
        )

        error_context = ""
        if context.error_message:
            error_context = f"Error context: {context.error_type}: {context.error_message}"

        analysis_prompt = ANALYZE_PAGE_PROMPT.format(
            step_number=context.current_step_number,
            total_steps=context.total_steps,
            step_name=context.current_step_name,
            step_description=context.current_step_description,
            expected_page_description=context.expected_page_description or "Not specified",
            previous_steps_summary=", ".join(context.previous_steps_completed) or "None",
            error_context=error_context,
            entity_data_summary=json.dumps(context.entity_data_summary, default=str)[:2000],
            officers_summary=", ".join(context.officers_summary) or "None listed",
        )

        raw = await self._call_llm(system_prompt, analysis_prompt, screenshot)
        return self._parse_page_analysis(raw)

    async def handle_exception(
        self, screenshot: bytes, exception: Exception, context: PageAnalysisContext,
    ) -> ExceptionAnalysisResult:
        """Diagnose an exception during step execution."""
        if not self.enabled:
            return ExceptionAnalysisResult(
                diagnosis=str(exception),
                recommendation="retry",
                user_message="Encountered an issue. Retrying...",
                reasoning="OpenKlerk disabled -- defaulting to retry.",
            )

        system_prompt = OPENKLERK_SYSTEM_PROMPT.format(
            filing_type=context.filing_type,
            entity_name=context.entity_name,
            portal_name=context.portal_name,
        )

        previous_analysis_context = ""
        if context.previous_analysis:
            previous_analysis_context = f"Previous analysis: {context.previous_analysis}"

        exception_prompt = HANDLE_EXCEPTION_PROMPT.format(
            step_number=context.current_step_number,
            step_name=context.current_step_name,
            error_type=type(exception).__name__,
            error_message=str(exception)[:500],
            retry_count=context.retry_count,
            max_retries=2,
            previous_analysis_context=previous_analysis_context,
        )

        raw = await self._call_llm(system_prompt, exception_prompt, screenshot)
        return self._parse_exception_analysis(raw)

    async def respond_to_user(
        self, user_message: str, screenshot: bytes, context: PageAnalysisContext,
    ) -> UserResponseResult:
        """Process a user message."""
        if not self.enabled:
            return UserResponseResult(
                understood=True, action="acknowledge",
                user_message="Noted. Continuing with the filing.",
                reasoning="OpenKlerk disabled -- acknowledging.",
            )

        system_prompt = OPENKLERK_SYSTEM_PROMPT.format(
            filing_type=context.filing_type,
            entity_name=context.entity_name,
            portal_name=context.portal_name,
        )
        truncated_msg = user_message[:2000]
        user_prompt = RESPOND_TO_USER_PROMPT.format(
            step_number=context.current_step_number,
            step_name=context.current_step_name,
            user_message=truncated_msg,
        )

        raw = await self._call_llm(system_prompt, user_prompt, screenshot)
        return self._parse_user_response(raw)

    async def recalibrate_after_control_return(
        self, screenshot: bytes, filer, last_known_step: int, transfer_reason: str,
    ) -> tuple[int, str]:
        """After user returns control, determine which step to resume from."""
        if not self.enabled:
            return last_known_step + 1, "Resuming from next step."

        steps = filer.get_steps()
        remaining = [s for s in steps if s.number > last_known_step]
        remaining_desc = "\n".join(
            f"Step {s.number}: {s.name} -- {s.description}" for s in remaining
        )
        last_step_name = ""
        for s in steps:
            if s.number == last_known_step:
                last_step_name = s.name
                break

        system_prompt = OPENKLERK_SYSTEM_PROMPT.format(
            filing_type=filer.FILING_NAME,
            entity_name="the entity",
            portal_name=filer.STATE_NAME,
        )
        prompt = RECALIBRATE_PROMPT.format(
            transfer_reason=transfer_reason,
            last_step=last_known_step,
            last_step_name=last_step_name,
            remaining_steps=remaining_desc,
        )

        raw = await self._call_llm(system_prompt, prompt, screenshot)
        try:
            data = json.loads(_strip_json_wrapper(raw))
            if data.get("user_completed_task") is True:
                return len(steps) + 1, data.get("user_message", "Filing completed!")
            resume_step = int(data.get("resume_from_step", last_known_step + 1))
            msg = data.get("user_message", "Resuming filing.")
            resume_step = max(last_known_step, min(resume_step, len(steps)))
            return resume_step, msg
        except Exception:
            return last_known_step + 1, "Resuming from next step."

    async def audit_filing(
        self, screenshots: list[bytes], entity_data: dict, filing_type: str, state: str,
    ) -> AuditResult:
        """Run adversarial audit on all screenshots from a filing."""
        if not self.enabled:
            return AuditResult(
                audit_passed=True, confidence=1.0,
                summary="OpenKlerk disabled -- auto-passing audit.",
                recommendation="proceed",
            )

        officers_list = ", ".join(
            f"{o.get('title', 'Officer')}: {o.get('full_name', 'Unknown')}"
            for o in (entity_data.get("officers") or [])
        )
        principal_address = json.dumps(entity_data.get("principal_address", {}), default=str)

        audit_prompt = ADVERSARIAL_AUDIT_PROMPT.format(
            entity_name=entity_data.get("entity_name", "Unknown"),
            entity_number=entity_data.get("entity_number", "Unknown"),
            formation_state=entity_data.get("state_of_formation", state),
            principal_address=principal_address,
            officers_list=officers_list or "None listed",
            business_data_json=json.dumps(entity_data, default=str)[:3000],
            filing_type=filing_type,
            state=state,
        )

        system_prompt = (
            "You are an adversarial auditor for government compliance filings. "
            "Your ONLY job is to find mistakes. Be strict."
        )

        screenshot = screenshots[0] if screenshots else None
        raw = await self._call_llm(system_prompt, audit_prompt, screenshot)
        return self._parse_audit_result(raw)

    async def analyze_screenshot(
        self, screenshot: bytes, page_number: int, total_pages: int,
        state: Optional[str] = None, previous_pages: Optional[list[str]] = None,
    ) -> dict:
        """Analyze a portal screenshot for contributor tooling."""
        from openklerk.intelligence.prompts import SCREENSHOT_ANALYSIS_PROMPT

        state_context = f"State: {state}" if state else ""
        prompt = SCREENSHOT_ANALYSIS_PROMPT.format(
            page_number=page_number,
            total_pages=total_pages,
            state_context=state_context,
            previous_pages=", ".join(previous_pages or []) or "None",
        )

        raw = await self._call_llm("You are a portal page analyzer.", prompt, screenshot)
        try:
            return json.loads(_strip_json_wrapper(raw))
        except Exception:
            return {
                "suggested_step_name": f"Page {page_number}",
                "page_type": "other",
                "page_description": "Analysis failed",
                "fields": [],
                "buttons": [],
            }

    async def generate_text(self, prompt: str) -> str:
        """Generate free-form text (for viral post, etc.)."""
        raw = await self._call_llm("You are a helpful writing assistant.", prompt)
        return raw.strip() if raw else ""

    # --- Internal LLM call ---

    async def _call_llm(
        self, system_prompt: str, user_prompt: str, screenshot: Optional[bytes] = None,
    ) -> str:
        """Call the LLM backend with optional screenshot."""
        if not self.llm_backend:
            logger.warning("OpenKlerk: No LLM backend configured")
            return ""
        try:
            return await asyncio.wait_for(
                self.llm_backend.call(system_prompt, user_prompt, screenshot),
                timeout=self.analysis_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("OpenKlerk: LLM call timed out")
            return ""
        except Exception as e:
            logger.error(f"OpenKlerk: LLM call failed: {e}")
            return ""

    # --- Parsing ---

    def _parse_page_analysis(self, raw: str) -> PageAnalysisResult:
        if not raw:
            return self._fallback_page_result()
        try:
            data = json.loads(_strip_json_wrapper(raw))
            result = PageAnalysisResult(**data)
            return result.validate_recommendation()
        except Exception as e:
            logger.warning(f"OpenKlerk: Failed to parse page analysis: {e}")
            return self._fallback_page_result()

    def _parse_exception_analysis(self, raw: str) -> ExceptionAnalysisResult:
        if not raw:
            return self._fallback_exception_result()
        try:
            data = json.loads(_strip_json_wrapper(raw))
            result = ExceptionAnalysisResult(**data)
            valid_recs = {"retry", "ask_user", "transfer_control", "fail"}
            if result.recommendation not in valid_recs:
                result.recommendation = "ask_user"
            return result
        except Exception as e:
            logger.warning(f"OpenKlerk: Failed to parse exception analysis: {e}")
            return self._fallback_exception_result()

    def _parse_user_response(self, raw: str) -> UserResponseResult:
        if not raw:
            return self._fallback_user_result()
        try:
            data = json.loads(_strip_json_wrapper(raw))
            result = UserResponseResult(**data)
            valid_actions = {"proceed_with_info", "transfer_control", "acknowledge", "ask_clarification"}
            if result.action not in valid_actions:
                result.action = "acknowledge"
            return result
        except Exception as e:
            logger.warning(f"OpenKlerk: Failed to parse user response: {e}")
            return self._fallback_user_result()

    def _parse_audit_result(self, raw: str) -> AuditResult:
        if not raw:
            return self._fallback_audit_result()
        try:
            data = json.loads(_strip_json_wrapper(raw))
            issues = [AuditIssue(**i) for i in data.get("issues", [])]
            return AuditResult(
                audit_passed=data.get("audit_passed", False),
                confidence=float(data.get("confidence", 0.0)),
                issues=issues,
                summary=data.get("summary", ""),
                recommendation=data.get("recommendation", "manual_review"),
            )
        except Exception as e:
            logger.warning(f"OpenKlerk: Failed to parse audit result: {e}")
            return self._fallback_audit_result()

    # --- Fallbacks ---

    def _fallback_page_result(self) -> PageAnalysisResult:
        return PageAnalysisResult(
            page_matches_expected=True, recommendation="ask_user",
            user_message="I'm having trouble analyzing this page. Can you tell me what you see?",
            user_message_type="question",
            user_question="What do you see on the portal page?",
            allows_text_input=True,
            reasoning="LLM response was empty or unparseable.",
            confidence=0.0,
        )

    def _fallback_exception_result(self) -> ExceptionAnalysisResult:
        return ExceptionAnalysisResult(
            diagnosis="Unable to diagnose -- LLM response unavailable",
            recommendation="ask_user",
            user_message="I encountered an issue I couldn't diagnose. Can you check the browser?",
            user_message_type="question",
            user_question="Can you see what's happening on the portal page?",
            allows_text_input=True,
            reasoning="LLM response was empty or unparseable.",
            confidence=0.0,
        )

    def _fallback_user_result(self) -> UserResponseResult:
        return UserResponseResult(
            understood=False, action="ask_clarification",
            user_message="I didn't quite understand. Could you rephrase that?",
            user_message_type="question",
            user_question="Could you rephrase or provide more details?",
            allows_text_input=True,
            reasoning="LLM response was empty or unparseable.",
        )

    def _fallback_audit_result(self) -> AuditResult:
        return AuditResult(
            audit_passed=False, confidence=0.0,
            issues=[AuditIssue(
                severity="warning",
                description="Audit could not be completed -- LLM response unavailable",
            )],
            summary="Audit inconclusive -- flagging for manual review.",
            recommendation="manual_review",
        )


class MockOpenKlerkService(OpenKlerkService):
    """Mock service for testing without a real LLM backend."""

    def __init__(self, **kwargs):
        super().__init__(enabled=True, **kwargs)

    async def analyze_page(self, screenshot, context):
        return PageAnalysisResult(
            page_matches_expected=True,
            page_description="Mock analysis -- page looks correct.",
            recommendation="proceed",
            user_message=f"Verified step {context.current_step_number}: {context.current_step_name}. Proceeding.",
            user_message_type="success",
            reasoning="Mock service -- always proceeds.",
            confidence=1.0,
        )

    async def handle_exception(self, screenshot, exception, context):
        retry_count = getattr(context, 'retry_count', 0)
        if retry_count >= 2:
            return ExceptionAnalysisResult(
                diagnosis=f"Mock diagnosis: step keeps failing -- {exception}",
                recommendation="transfer_control",
                user_message="This step isn't working automatically. Handing over to you.",
                user_message_type="warning",
                reasoning=f"Mock service -- retry cap reached ({retry_count}).",
                confidence=0.3,
            )
        return ExceptionAnalysisResult(
            diagnosis=f"Mock diagnosis: {exception}",
            recommendation="retry",
            user_message="Encountered a minor issue. Retrying...",
            user_message_type="warning",
            reasoning=f"Mock service -- retrying after: {exception}",
            confidence=0.5,
        )

    async def respond_to_user(self, user_message, screenshot, context):
        return UserResponseResult(
            understood=True, action="acknowledge",
            user_message="Got it! Continuing with the filing.",
            user_message_type="info",
            reasoning=f"Mock service -- acknowledged: {user_message[:100]}",
        )

    async def recalibrate_after_control_return(self, screenshot, filer, last_known_step, transfer_reason):
        return last_known_step + 1, "Mock: Resuming from next step."

    async def audit_filing(self, screenshots, entity_data, filing_type, state):
        return AuditResult(
            audit_passed=True, confidence=1.0,
            summary="Mock audit -- all data verified.",
            recommendation="proceed",
        )

    async def analyze_screenshot(self, screenshot, page_number, total_pages, state=None, previous_pages=None):
        return {
            "suggested_step_name": f"Mock Page {page_number}",
            "page_type": "form",
            "page_description": "Mock analysis of portal page",
            "fields": [],
            "buttons": [],
        }

    async def generate_text(self, prompt: str) -> str:
        return "Mock generated text for: " + prompt[:100]
