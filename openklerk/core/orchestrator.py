"""
StandaloneOrchestrator -- Coordinates a filing from start to finish.

Standalone version: no database, no WebSocket. Reads JSON config,
runs steps, outputs results to stdout/file.
"""
import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from openklerk.core.base_filer import BaseStateFiler, FilingContext, FilingStep
from openklerk.core.browser import BrowserEngine
from openklerk.core.state_machine import FilingStateMachine, FilingStatus
from openklerk.core.exceptions import FilingError, PreFlightError, FilerNotFoundError

logger = logging.getLogger("openklerk")
console = Console()


class FilingResult:
    """Result of a filing execution."""

    def __init__(self):
        self.status: str = "pending"
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.total_steps: int = 0
        self.completed_steps: int = 0
        self.step_log: list[dict] = []
        self.screenshots: list[str] = []
        self.confirmation_number: Optional[str] = None
        self.error_message: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "step_log": self.step_log,
            "screenshots": self.screenshots,
            "confirmation_number": self.confirmation_number,
            "error_message": self.error_message,
        }


class StandaloneOrchestrator:
    """
    Standalone filing orchestrator -- no DB, no WebSocket.

    Reads a JSON config file for entity data and credentials,
    runs the filer steps, outputs results to stdout and optionally a JSON file.
    """

    def __init__(
        self,
        headless: bool = False,
        screenshots_dir: str = "./screenshots",
        openklerk_service=None,
    ):
        self.headless = headless
        self.screenshots_dir = screenshots_dir
        self.openklerk = openklerk_service

    async def execute_filing(
        self,
        filer: BaseStateFiler,
        context: FilingContext,
        output_file: Optional[str] = None,
    ) -> FilingResult:
        """
        Execute a filing end-to-end.

        Args:
            filer: The state filer to use
            context: Filing context with entity data and credentials
            output_file: Optional path to write JSON result
        """
        result = FilingResult()
        result.started_at = datetime.utcnow()
        state_machine = FilingStateMachine(FilingStatus.QUEUED)

        # Pre-flight check
        issues = filer.pre_flight_check(context)
        fatal = [i for i in issues if "entity name" in i.lower()]
        warnings = [i for i in issues if i not in fatal]

        if fatal:
            raise PreFlightError(fatal)

        if warnings:
            for w in warnings:
                console.print(f"  [yellow]Warning:[/yellow] {w}")

        # Get steps
        steps = filer.get_steps()
        result.total_steps = len(steps)

        console.print(Panel(
            f"[bold]{filer.FILING_NAME}[/bold] for [cyan]{context.entity_name}[/cyan]\n"
            f"Portal: {filer.PORTAL_URL}\n"
            f"Steps: {len(steps)}",
            title="OpenKlerk Filing",
            border_style="green",
        ))

        # Launch browser
        browser = BrowserEngine(
            session_id=f"filing_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            screenshots_dir=context.screenshots_dir or self.screenshots_dir,
            headless=self.headless,
        )

        state_machine.transition(FilingStatus.IN_PROGRESS)
        result.status = "in_progress"

        try:
            await browser.start()
            context.browser_session_id = browser.session_id

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Filing...", total=len(steps))

                for step in steps:
                    progress.update(task, description=f"Step {step.number}/{len(steps)}: {step.name}")

                    step.started_at = datetime.utcnow()
                    step.status = "in_progress"

                    try:
                        completed_step = await filer.execute_step(
                            step.number, context, browser
                        )

                        # Take screenshot
                        screenshot_path = await browser.take_screenshot(
                            label=f"step_{step.number}_{step.name}"
                        )
                        completed_step.screenshot_url = screenshot_path
                        result.screenshots.append(screenshot_path)

                        # OpenKlerk analysis at page transitions
                        if self.openklerk and completed_step.is_page_transition:
                            try:
                                screenshot_bytes = await browser.get_screenshot_bytes()
                                from openklerk.intelligence.models import PageAnalysisContext
                                analysis_ctx = PageAnalysisContext(
                                    filing_type=filer.FILING_NAME,
                                    entity_name=context.entity_name,
                                    portal_name=filer.STATE_NAME,
                                    state_code=filer.STATE_CODE,
                                    current_step_number=step.number,
                                    current_step_name=step.name,
                                    current_step_description=step.description,
                                    total_steps=len(steps),
                                    expected_page_description=step.expected_page,
                                )
                                analysis = await self.openklerk.analyze_page(
                                    screenshot_bytes, analysis_ctx
                                )
                                if analysis.recommendation != "proceed":
                                    console.print(
                                        f"  [yellow]OpenKlerk:[/yellow] {analysis.user_message}"
                                    )
                            except Exception as e:
                                logger.debug(f"OpenKlerk analysis failed: {e}")

                        completed_step.status = "completed"
                        completed_step.completed_at = datetime.utcnow()
                        result.completed_steps += 1

                        result.step_log.append({
                            "step": step.number,
                            "name": step.name,
                            "status": "completed",
                            "screenshot": screenshot_path,
                            "timestamp": datetime.utcnow().isoformat(),
                            "metadata": completed_step.metadata,
                        })

                        # Check for payment step
                        if completed_step.requires_payment:
                            if context.payment_tier == "customer_pays":
                                console.print(
                                    "\n  [bold yellow]Payment required.[/bold yellow] "
                                    "Complete payment in the browser window."
                                )
                                console.print("  Press Enter when payment is complete...")
                                await asyncio.get_event_loop().run_in_executor(None, input)

                        progress.advance(task)

                    except Exception as e:
                        step.status = "failed"
                        step.error_message = str(e)
                        result.step_log.append({
                            "step": step.number,
                            "name": step.name,
                            "status": "failed",
                            "error": str(e),
                            "timestamp": datetime.utcnow().isoformat(),
                        })
                        raise FilingError(
                            f"Step {step.number} ({step.name}) failed: {e}"
                        ) from e

            # Success
            state_machine.transition(FilingStatus.COMPLETED)
            result.status = "completed"
            result.completed_at = datetime.utcnow()

            # Check for confirmation number in last step metadata
            last_step_log = result.step_log[-1] if result.step_log else {}
            meta = last_step_log.get("metadata", {})
            result.confirmation_number = meta.get("confirmation_number")

            console.print(Panel(
                f"[bold green]Filing completed successfully![/bold green]\n"
                f"Steps: {result.completed_steps}/{result.total_steps}\n"
                f"Duration: {(result.completed_at - result.started_at).total_seconds():.1f}s"
                + (f"\nConfirmation: {result.confirmation_number}" if result.confirmation_number else ""),
                title="Result",
                border_style="green",
            ))

        except FilingError:
            state_machine.transition(FilingStatus.FAILED)
            result.status = "failed"
            result.completed_at = datetime.utcnow()
            result.error_message = result.step_log[-1].get("error") if result.step_log else "Unknown"
            console.print(f"\n  [bold red]Filing failed:[/bold red] {result.error_message}")
            raise

        except Exception as e:
            state_machine.transition(FilingStatus.FAILED)
            result.status = "failed"
            result.completed_at = datetime.utcnow()
            result.error_message = str(e)
            console.print(f"\n  [bold red]Unexpected error:[/bold red] {e}")
            raise FilingError(str(e)) from e

        finally:
            await browser.stop()

            # Write result JSON
            if output_file:
                output_path = Path(output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "w") as f:
                    json.dump(result.to_dict(), f, indent=2)
                console.print(f"\n  Result saved to: {output_path}")

        return result
