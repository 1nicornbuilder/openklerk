"""
Viral post generator -- create social media posts from demo recordings.
"""
import os
from typing import Optional

from rich.console import Console

console = Console()


async def generate_post(
    state: str = "Unknown",
    filing_type: str = "Filing",
    duration: int = 60,
    open_linkedin: bool = False,
    openklerk_service=None,
    demo_video_path: Optional[str] = None,
):
    """Generate social media post from demo recording."""

    if openklerk_service:
        post_text = await openklerk_service.generate_text(
            f"Generate a LinkedIn post for a developer who contributed a "
            f"{filing_type} module for {state} to OpenClerc. Demo shows AI "
            f"filing in {duration} seconds. Hook -- mention OpenClerc + NeverMissAFiling "
            f"-- CTA (star repo, contribute). 100-150 words, authentic, 2-3 hashtags."
        )
    else:
        post_text = _default_post(state, filing_type, duration)

    output_dir = "launch"
    os.makedirs(output_dir, exist_ok=True)
    output = f"{output_dir}/{state.lower()}_{filing_type.lower().replace(' ', '_')}_post.md"
    with open(output, "w") as f:
        f.write(post_text)

    console.print(f"\nPost saved to {output}\n")
    console.print(post_text)

    if open_linkedin:
        await _open_linkedin_and_paste(post_text)


def _default_post(state: str, filing_type: str, duration: int) -> str:
    return f"""Just contributed a {filing_type} module for {state} to OpenClerc!

Watch the AI file a {filing_type} in {duration} seconds -- fully autonomous, zero human intervention.

OpenClerc is the open-source engine behind @NeverMissAFiling. Every contributor adds a state, records a demo, and helps businesses never miss a filing deadline again.

Want to add YOUR state? It's easier than you think:
1. Take screenshots of your state's filing portal
2. Run `openclerc analyze --screenshots ./your_state/`
3. Fill in the generated code
4. Submit a PR

GitHub: github.com/NeverMissAFiling/openclerc

#OpenClerc #GovTech #OpenSource"""


async def _open_linkedin_and_paste(post_text: str):
    """Open LinkedIn, paste post, hand control to user."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        console.print("[yellow]Playwright not available for LinkedIn automation.[/yellow]")
        console.print(f"\nPaste this post manually:\n\n{post_text}")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto("https://www.linkedin.com/feed/")

        console.print("\nLinkedIn opened. Log in if needed.")
        console.print("   Post will be pasted once the feed loads.\n")

        try:
            await page.wait_for_selector("[role='main']", timeout=120000)
            await page.wait_for_timeout(2000)

            start_post = page.locator("button:has-text('Start a post')")
            if await start_post.count() > 0:
                await start_post.first.click()
                await page.wait_for_timeout(1000)

                editor = page.locator("[role='textbox']").first
                await editor.fill(post_text)

                console.print("\nPost pasted! Review and click 'Post' when ready.")
            else:
                console.print(f"\nCouldn't find post button. Paste manually:\n\n{post_text}")
        except Exception:
            console.print(f"\nCouldn't auto-paste. Here's your post:\n\n{post_text}")

        console.print("\nClose the browser window when done.\n")
        input("Press Enter to close...")
        await browser.close()
