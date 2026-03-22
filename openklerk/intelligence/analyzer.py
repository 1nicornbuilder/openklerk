"""Screenshot analyzer for contributor tooling."""
import glob
import json
import logging
import os
from typing import Optional

from rich.console import Console

logger = logging.getLogger("openklerk")
console = Console()


async def analyze_screenshots(
    screenshots_dir: str,
    state: Optional[str] = None,
    openklerk_service=None,
):
    """
    Analyze portal screenshots and generate a draft filer.

    Args:
        screenshots_dir: Directory containing PNG/JPG screenshots
        state: State name (e.g., "Oregon")
        openklerk_service: OpenKlerk service instance for LLM analysis
    """
    # 1. Find and sort screenshots
    files = sorted(glob.glob(os.path.join(screenshots_dir, "*.png")))
    if not files:
        files = sorted(glob.glob(os.path.join(screenshots_dir, "*.jpg")))

    if not files:
        console.print("[red]No screenshots found in directory.[/red]")
        return None

    console.print(f"Found {len(files)} screenshots to analyze")

    if not openklerk_service:
        from openklerk.intelligence.service import MockOpenKlerkService
        openklerk_service = MockOpenKlerkService()

    # 2. Analyze each screenshot
    analyses = []
    for i, filepath in enumerate(files):
        console.print(f"  Analyzing {i+1}/{len(files)}: {os.path.basename(filepath)}...")

        with open(filepath, "rb") as f:
            screenshot_bytes = f.read()

        result = await openklerk_service.analyze_screenshot(
            screenshot=screenshot_bytes,
            page_number=i + 1,
            total_pages=len(files),
            state=state,
            previous_pages=[a["suggested_step_name"] for a in analyses],
        )
        analyses.append(result)

    # 3. Generate draft filer from analyses
    draft_code = _generate_draft_filer(state or "Unknown", analyses)

    # 4. Save
    state_slug = (state or "unknown").lower().replace(" ", "_")
    output_path = f"openklerk/filers/{state_slug}_draft.py"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        f.write(draft_code)

    analysis_path = f"docs/analysis/{state_slug}_analysis.json"
    os.makedirs(os.path.dirname(analysis_path), exist_ok=True)
    with open(analysis_path, "w") as f:
        json.dump(analyses, f, indent=2)

    console.print(f"\n[green]Draft filer generated![/green]")
    console.print(f"  Code: {output_path}")
    console.print(f"  Analysis: {analysis_path}")
    console.print(f"\n[yellow]Review the TODOs in the generated code and fill in CSS selectors.[/yellow]")

    return {"code_path": output_path, "analysis_path": analysis_path, "analyses": analyses}


def _generate_draft_filer(state: str, analyses: list[dict]) -> str:
    """Generate a draft filer module from screenshot analyses."""
    state_slug = state.lower().replace(" ", "_")
    class_name = "".join(w.capitalize() for w in state.split()) + "Filer"

    steps_code = []
    execute_cases = []
    for i, analysis in enumerate(analyses, 1):
        step_name = analysis.get("suggested_step_name", f"Page {i}")
        page_type = analysis.get("page_type", "form")
        desc = analysis.get("page_description", "")[:80]

        steps_code.append(
            f'            FilingStep({i}, "{step_name}", "{desc}",\n'
            f'                        is_page_transition=True,\n'
            f'                        expected_page="{desc}"),\n'
        )

        fields = analysis.get("fields", [])
        field_comments = "\n".join(
            f"            # TODO: Fill field '{f.get('label', '?')}' ({f.get('type', 'text')}) "
            f"selector: {f.get('selector_hint', 'unknown')}"
            for f in fields
        )

        execute_cases.append(
            f"        {'el' if i > 1 else ''}if step_number == {i}:\n"
            f"            # {step_name} ({page_type})\n"
            f"{field_comments}\n"
            f"            pass  # TODO: Implement\n"
        )

    return f'''"""
{class_name} -- DRAFT filer generated from screenshot analysis.

THIS IS A DRAFT. Review all TODOs and fill in CSS selectors.
"""
import logging
from typing import Any, Optional

from openklerk.core.base_filer import BaseStateFiler, FilingContext, FilingStep
from openklerk.filers import register_filer

logger = logging.getLogger("openklerk")


class {class_name}(BaseStateFiler):
    """{state} filing -- DRAFT."""

    STATE_CODE = "{state_slug[:2].upper()}"  # TODO: Set correct state code
    STATE_NAME = "{state}"
    FILING_CODE = "{state_slug}_draft"  # TODO: Set correct filing code
    FILING_NAME = "{state} Filing"  # TODO: Set correct filing name
    PORTAL_URL = ""  # TODO: Set portal URL
    TOTAL_STEPS = {len(analyses)}

    def get_steps(self) -> list[FilingStep]:
        return [
{"".join(steps_code)}        ]

    async def execute_step(
        self,
        step_number: int,
        context: FilingContext,
        browser: Any,
    ) -> FilingStep:
        steps = self.get_steps()
        step = steps[step_number - 1]

{"".join(execute_cases)}
        return step

    def pre_flight_check(self, context: FilingContext) -> list[str]:
        issues = super().pre_flight_check(context)
        # TODO: Add state-specific pre-flight checks
        return issues


# TODO: Uncomment when filer is ready
# register_filer("{state_slug}_draft", {class_name})
'''
