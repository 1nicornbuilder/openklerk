"""
OpenKlerk CLI -- Command-line interface for the filing engine.

Usage:
    openklerk run --config entity.json --filer ca_soi
    openklerk new-filer --state Oregon --filing-type "Annual Report"
    openklerk check --filer california_soi
    openklerk analyze --screenshots ./screenshots/oregon/
    openklerk post --demo-video ./demo.mp4
    openklerk list
    openklerk --version
"""
import asyncio
import json
import sys

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

import openklerk

console = Console()


@click.group()
@click.version_option(version=openklerk.__version__, prog_name="openklerk")
def cli():
    """OpenKlerk -- Open-source government compliance filing engine."""
    pass


@cli.command()
@click.option("--config", "-c", required=True, help="Path to entity JSON config file")
@click.option("--filer", "-f", required=True, help="Filing code (e.g., ca_soi, de_franchise_tax)")
@click.option("--headless", is_flag=True, help="Run browser in headless mode")
@click.option("--screenshots-dir", default="./screenshots", help="Screenshots output directory")
@click.option("--output", "-o", help="Path to write JSON result file")
@click.option("--mock-llm", is_flag=True, help="Use mock LLM (no real API calls)")
def run(config, filer, headless, screenshots_dir, output, mock_llm):
    """Run a filing from a JSON config file."""
    from openklerk.filers import get_filer_for_code
    from openklerk.core.base_filer import FilingContext
    from openklerk.core.orchestrator import StandaloneOrchestrator

    # Load config
    try:
        with open(config) as f:
            data = json.load(f)
    except Exception as e:
        console.print(f"[red]Error loading config:[/red] {e}")
        sys.exit(1)

    # Get filer
    filer_instance = get_filer_for_code(filer)
    if not filer_instance:
        console.print(f"[red]No filer registered for code:[/red] {filer}")
        console.print("Run 'openklerk list' to see available filers.")
        sys.exit(1)

    # Build context from JSON
    context = FilingContext(
        entity_name=data.get("entity_name", ""),
        entity_number=data.get("entity_number"),
        entity_type=data.get("entity_type", "corporation"),
        state_of_formation=data.get("state_of_formation", ""),
        formation_date=data.get("formation_date"),
        ein=data.get("ein"),
        principal_address=data.get("principal_address", {}),
        mailing_address=data.get("mailing_address"),
        officers=data.get("officers", []),
        business_data=data.get("business_data", {}),
        registered_agent=data.get("registered_agent"),
        portal_username=data.get("portal_username"),
        portal_password=data.get("portal_password"),
        portal_extra=data.get("portal_extra", {}),
        payment_tier=data.get("payment_tier", "customer_pays"),
        screenshots_dir=screenshots_dir,
    )

    # Set up OpenKlerk
    openklerk = None
    if mock_llm:
        from openklerk.intelligence.service import MockOpenKlerkService
        openklerk = MockOpenKlerkService()

    orchestrator = StandaloneOrchestrator(
        headless=headless,
        screenshots_dir=screenshots_dir,
        openklerk_service=openklerk,
    )

    try:
        asyncio.run(orchestrator.execute_filing(filer_instance, context, output))
    except Exception as e:
        console.print(f"\n[red]Filing failed:[/red] {e}")
        sys.exit(1)


@cli.command("new-filer")
@click.option("--state", "-s", required=True, help="State name (e.g., Oregon)")
@click.option("--filing-type", "-t", required=True, help="Filing type (e.g., 'Annual Report')")
def new_filer(state, filing_type):
    """Generate a new filer module from template."""
    from openklerk.contrib.scaffold import create_filer_scaffold
    create_filer_scaffold(state, filing_type)


@cli.command("check")
@click.option("--filer", "-f", required=True, help="Filer module name (e.g., california_soi)")
def check(filer):
    """Run quality checks on a filer module."""
    from openklerk.contrib.quality_gate import run_quality_checks
    passed = run_quality_checks(filer)
    sys.exit(0 if passed else 1)


@cli.command("analyze")
@click.option("--screenshots", "-s", required=True, help="Directory containing portal screenshots")
@click.option("--state", help="State name for context")
@click.option("--mock-llm", is_flag=True, help="Use mock LLM")
def analyze(screenshots, state, mock_llm):
    """Analyze portal screenshots and generate a draft filer."""
    from openklerk.intelligence.analyzer import analyze_screenshots

    openklerk = None
    if mock_llm:
        from openklerk.intelligence.service import MockOpenKlerkService
        openklerk = MockOpenKlerkService()

    asyncio.run(analyze_screenshots(screenshots, state=state, openklerk_service=openklerk))


@cli.command("post")
@click.option("--demo-video", "-v", help="Path to demo video file")
@click.option("--state", "-s", help="State name")
@click.option("--filing-type", "-t", help="Filing type")
@click.option("--duration", "-d", type=int, help="Demo duration in seconds")
@click.option("--open-linkedin", is_flag=True, help="Open LinkedIn to paste post")
@click.option("--mock-llm", is_flag=True, help="Use mock LLM")
def post(demo_video, state, filing_type, duration, open_linkedin, mock_llm):
    """Generate a social media post for a demo recording."""
    from openklerk.demo.viral_post import generate_post

    openklerk = None
    if mock_llm:
        from openklerk.intelligence.service import MockOpenKlerkService
        openklerk = MockOpenKlerkService()

    asyncio.run(generate_post(
        state=state or "Unknown",
        filing_type=filing_type or "Filing",
        duration=duration or 60,
        open_linkedin=open_linkedin,
        openklerk_service=openklerk,
    ))


@cli.command("list")
def list_filers():
    """List all registered filers."""
    from openklerk.filers import list_registered_filers

    filers = list_registered_filers()

    if not filers:
        console.print("[yellow]No filers registered.[/yellow]")
        return

    table = Table(title="Registered Filers")
    table.add_column("Filing Code", style="cyan")
    table.add_column("Class Name", style="green")

    for code, cls_name in sorted(filers.items()):
        table.add_row(code, cls_name)

    console.print(table)


if __name__ == "__main__":
    cli()
