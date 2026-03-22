# Contributing to OpenKlerk

Every new state filer makes the platform more useful for businesses across the country.

## Prerequisites

- Python 3.11+
- Git
- A government filing portal to automate

## Setup

```bash
git clone https://github.com/NeverMissAFiling/openklerk.git
cd openklerk
pip install -e ".[dev]"
playwright install chromium
pytest tests/ -v
```

## How to Add a New State

### Step 1: Research the Portal

Navigate through the filing portal manually. Screenshot every page.
Save to `docs/screenshots/your_state/` as numbered PNGs.

### Step 2: Generate the Scaffold

```bash
openklerk new-filer --state "Oregon" --filing-type "Annual Report"
```

### Step 3: (Optional) Run the Screenshot Analyzer

```bash
openklerk analyze --screenshots docs/screenshots/oregon/ --state Oregon --mock-llm
```

### Step 4: Implement the Filer

Edit `openklerk/filers/oregon_annual_report.py`. Set metadata, define steps, implement browser automation.

Use existing filers as reference:
- `california_soi.py` -- Complex React SPA (16 steps)
- `delaware_franchise_tax.py` -- Simple form with CAPTCHA (6 steps)
- `sf_business_reg.py` -- Multi-part login (15 steps)

### Step 5: Write Tests and Run Quality Checks

```bash
pytest tests/test_oregon_annual_report.py -v
openklerk check --filer oregon_annual_report
```

### Step 6: Submit a PR

Include portal screenshots and special handling notes in the PR description.

## Code Standards

- Use `async/await` for all browser operations
- Use `browser.human_type()`, `browser.human_click()` for human-like behavior
- Never hardcode credentials or API keys
- Never import from `app.*` (SaaS code)
