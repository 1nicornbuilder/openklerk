# OpenKlerk

**Open-source engine for autonomous government compliance filing.**

OpenKlerk uses browser automation and AI to file government compliance forms (Statement of Information, Annual Reports, Franchise Tax) without human intervention. It navigates real government portals, fills forms, handles payments, and downloads confirmations.

> Part of the [NeverMissAFiling](https://nevermissafiling.com) ecosystem.

---

## What It Does

- **Autonomous filing**: Navigates government portals, fills forms, and submits filings end-to-end
- **AI-assisted**: OpenKlerk intelligence layer analyzes portal pages, detects errors, and handles unexpected situations
- **Multi-state support**: California SOI, Delaware Franchise Tax, San Francisco ABR -- with more coming
- **Contributor-friendly**: Scaffold generator, screenshot analyzer, and quality gate make adding new states straightforward
- **Open source**: BSL 1.1 license (converts to Apache 2.0 after 3 years)

## Quick Start

```bash
git clone https://github.com/NeverMissAFiling/openklerk.git
cd openklerk
pip install -e ".[dev]"
playwright install chromium
openklerk --version
openklerk list
```

## Run a Filing

```bash
openklerk run --config entity.json --filer ca_soi
openklerk run --config entity.json --filer ca_soi --mock-llm
openklerk run --config entity.json --filer ca_soi --headless
```

## Add a State

1. **Screenshot the portal**: Navigate through the filing portal and capture screenshots of every page
2. **Run the analyzer**: `openklerk analyze --screenshots ./screenshots/your_state/ --state "Your State"`
3. **Fill in the code**: Edit the generated draft filer with actual CSS selectors and form logic
4. **Run quality check**: `openklerk check --filer your_state_filing`
5. **Submit a PR**

Or use the scaffold generator:

```bash
openklerk new-filer --state Oregon --filing-type "Annual Report"
```

## Supported States

| State | Filing Type | Code | Status | CAPTCHA |
|-------|------------|------|--------|---------|
| California | Statement of Information | `ca_soi` | Working | No |
| Delaware | Annual Franchise Tax Report | `de_franchise_tax` | Working | Yes (user input) |
| San Francisco | Annual Business Registration | `sf_abr` | Working | No |

## Architecture

```
openklerk/
  core/           # Browser engine, base filer, state machine, orchestrator
  intelligence/   # OpenKlerk LLM service with pluggable backends
  filers/         # State-specific filing implementations
  models/         # Pydantic data models
  contrib/        # Scaffold generator, quality gate, screenshot analyzer
  demo/           # Demo recording and overlay tools
  cli.py          # Click CLI entry point
```

## Configuration

### LLM Backends

| Backend | Status | Setup |
|---------|--------|-------|
| Google Vertex AI | Implemented | Set `GCP_PROJECT_ID`, `GCP_LOCATION` env vars |
| Anthropic (Claude) | Stub | Contributions welcome |
| OpenAI (GPT) | Stub | Contributions welcome |
| Ollama (local) | Stub | Contributions welcome |
| Mock | Built-in | Use `--mock-llm` flag |

## CLI Reference

```
openklerk --version              Show version
openklerk list                   List registered filers
openklerk run -c config.json -f ca_soi    Run a filing
openklerk new-filer -s Oregon -t "Annual Report"    Generate scaffold
openklerk check -f california_soi    Run quality checks
openklerk analyze -s ./screenshots/    Analyze portal screenshots
openklerk post -s Oregon -t "Annual Report"    Generate social post
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide.

## License

Business Source License 1.1 (BSL-1.1). You may use OpenKlerk for any purpose EXCEPT offering it as a commercial service to third parties. After 3 years, converts to Apache 2.0.

For commercial licensing: balaji.renukumar@gmail.com
