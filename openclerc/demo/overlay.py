"""
Overlay injection for OpenClerc demos.

Injects a floating "AI thinking" panel into the browser page
and provides methods to update it during the demo sequence.
"""
import asyncio


OVERLAY_CSS = """
#nmaf-overlay {
    position: fixed; bottom: 20px; right: 20px; z-index: 99999;
    background: rgba(15, 23, 42, 0.95); color: white;
    border-radius: 16px; padding: 20px 24px; width: 340px;
    font-family: 'Inter', sans-serif; box-shadow: 0 8px 32px rgba(0,0,0,0.3);
    border: 1px solid rgba(255,255,255,0.1);
}
#nmaf-overlay .logo-row { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
#nmaf-overlay .n-box { background: #3b82f6; width: 32px; height: 32px; border-radius: 8px;
    display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 18px; }
#nmaf-overlay .agent-label { font-weight: 600; font-size: 14px; }
#nmaf-overlay .step-counter { font-size: 12px; color: #94a3b8; margin-bottom: 8px; }
#nmaf-overlay .thinking { font-size: 13px; line-height: 1.5; min-height: 40px; }
#nmaf-overlay .cursor { display: inline-block; width: 2px; height: 14px; background: #3b82f6;
    margin-left: 2px; animation: blink 1s infinite; vertical-align: middle; }
@keyframes blink { 0%,49% { opacity: 1; } 50%,100% { opacity: 0; } }
#nmaf-overlay .progress-track { height: 3px; background: rgba(255,255,255,0.1); border-radius: 2px;
    margin: 12px 0 8px; }
#nmaf-overlay .progress-fill { height: 100%; background: #3b82f6; border-radius: 2px;
    transition: width 0.5s ease; }
#nmaf-overlay .steps-done { display: flex; gap: 4px; flex-wrap: wrap; }
#nmaf-overlay .dot { width: 8px; height: 8px; border-radius: 50%; background: rgba(255,255,255,0.2); }
#nmaf-overlay .dot.done { background: #22c55e; }
#nmaf-overlay .dot.active { background: #3b82f6; animation: pulse 1.5s infinite; }
@keyframes pulse { 0%,100% { transform: scale(1); } 50% { transform: scale(1.3); } }
#nmaf-demo-watermark { position: fixed; top: 10px; left: 10px; z-index: 99999;
    background: rgba(239,68,68,0.9); color: white; padding: 4px 12px; border-radius: 6px;
    font-size: 11px; font-weight: bold; letter-spacing: 1px; }
"""

OVERLAY_HTML = """
<div id="nmaf-demo-watermark">DEMO MODE</div>
<div id="nmaf-overlay">
  <div class="logo-row">
    <div class="n-box">O</div>
    <div><div class="agent-label">OpenClerc AI Agent</div></div>
  </div>
  <div class="step-counter" id="nmaf-step-counter">Initializing...</div>
  <div class="thinking" id="nmaf-thinking">
    <span class="icon" id="nmaf-icon"></span>
    <span id="nmaf-thought-text"></span>
    <span class="cursor"></span>
  </div>
  <div class="progress-track"><div class="progress-fill" id="nmaf-progress"></div></div>
  <div class="steps-done" id="nmaf-steps-done"></div>
</div>
"""


async def inject_overlay(page, total_steps: int = 19):
    """Inject the overlay HTML and CSS into the current page."""
    css_escaped = OVERLAY_CSS.replace("`", "\\`")
    html_escaped = OVERLAY_HTML.replace("`", "\\`")
    await page.evaluate(f"""() => {{
        const style = document.createElement('style');
        style.textContent = `{css_escaped}`;
        document.head.appendChild(style);
        const div = document.createElement('div');
        div.innerHTML = `{html_escaped}`;
        while (div.firstChild) document.body.appendChild(div.firstChild);
        const dotsContainer = document.getElementById('nmaf-steps-done');
        for (let i = 0; i < {total_steps}; i++) {{
            const dot = document.createElement('div');
            dot.className = 'dot';
            dot.id = 'nmaf-dot-' + i;
            dotsContainer.appendChild(dot);
        }}
    }}""")


async def ensure_overlay(page, total_steps: int = 19):
    """Re-inject overlay if it was wiped by a page navigation."""
    exists = await page.evaluate("() => !!document.getElementById('nmaf-overlay')")
    if not exists:
        await inject_overlay(page, total_steps)


async def update_overlay(page, step: dict, total_steps: int = 19):
    """Update the overlay with the current step's thinking text."""
    await ensure_overlay(page, total_steps)

    step_num = step["step"]
    thought = step["thought"]
    icon = step.get("icon", "")
    progress = round((step_num / total_steps) * 100)

    await page.evaluate(f"""() => {{
        document.getElementById('nmaf-step-counter').textContent = 'Step {step_num} of {total_steps}';
        document.getElementById('nmaf-progress').style.width = '{progress}%';
        document.getElementById('nmaf-icon').textContent = '{icon}';
        for (let i = 0; i < {step_num - 1}; i++) {{
            const dot = document.getElementById('nmaf-dot-' + i);
            if (dot) {{ dot.className = 'dot done'; }}
        }}
        const activeDot = document.getElementById('nmaf-dot-' + {step_num - 1});
        if (activeDot) {{ activeDot.className = 'dot active'; }}
    }}""")

    # Typewriter effect
    await page.evaluate("() => { document.getElementById('nmaf-thought-text').textContent = ''; }")
    for char in thought:
        escaped = char.replace("'", "\\'").replace("\\", "\\\\")
        await page.evaluate(f"""() => {{
            document.getElementById('nmaf-thought-text').textContent += '{escaped}';
        }}""")
        await asyncio.sleep(0.03 if char != " " else 0.06)


async def finalize_overlay(page, total_steps: int = 19):
    """Mark all steps as done in the overlay."""
    await ensure_overlay(page, total_steps)
    await page.evaluate(f"""() => {{
        for (let i = 0; i < {total_steps}; i++) {{
            const dot = document.getElementById('nmaf-dot-' + i);
            if (dot) {{ dot.className = 'dot done'; }}
        }}
        document.getElementById('nmaf-progress').style.width = '100%';
        document.getElementById('nmaf-step-counter').textContent = 'Complete -- {total_steps}/{total_steps} steps';
    }}""")
