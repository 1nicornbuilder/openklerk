"""
Contributor leaderboard -- stats from GitHub API.
"""
import logging
from typing import Optional

import httpx
from rich.console import Console
from rich.table import Table

logger = logging.getLogger("openclerc")
console = Console()

REPO = "NeverMissAFiling/openclerc"
GITHUB_API = "https://api.github.com"


async def show_leaderboard(token: Optional[str] = None):
    """Fetch and display contributor leaderboard."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    async with httpx.AsyncClient() as client:
        # Get contributors
        resp = await client.get(
            f"{GITHUB_API}/repos/{REPO}/contributors",
            headers=headers,
        )
        if resp.status_code != 200:
            console.print(f"[red]Failed to fetch contributors:[/red] {resp.status_code}")
            return

        contributors = resp.json()

        # Get filer files to count state contributions
        tree_resp = await client.get(
            f"{GITHUB_API}/repos/{REPO}/git/trees/main",
            headers=headers,
            params={"recursive": "1"},
        )

        filer_count = 0
        if tree_resp.status_code == 200:
            tree = tree_resp.json()
            filer_files = [
                f["path"] for f in tree.get("tree", [])
                if f["path"].startswith("openclerc/filers/") and f["path"].endswith(".py")
                and not f["path"].endswith("__init__.py") and "template" not in f["path"]
                and "dummy" not in f["path"]
            ]
            filer_count = len(filer_files)

    # Display
    table = Table(title=f"OpenClerc Contributors ({filer_count} filers)")
    table.add_column("#", style="dim")
    table.add_column("Contributor", style="cyan")
    table.add_column("Contributions", style="green", justify="right")
    table.add_column("Profile", style="dim")

    for i, contrib in enumerate(contributors[:20], 1):
        table.add_row(
            str(i),
            contrib.get("login", "?"),
            str(contrib.get("contributions", 0)),
            contrib.get("html_url", ""),
        )

    console.print(table)
