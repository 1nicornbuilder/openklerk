# Quick Start Guide

## Installation

```bash
git clone https://github.com/NeverMissAFiling/openclerc.git
cd openclerc
pip install -e ".[dev]"
playwright install chromium
```

## Verify

```bash
openclerc --version
openclerc list
```

## Run a Filing

1. Copy `examples/business_entity.json` and fill in your business details
2. Run: `openclerc run --config my_entity.json --filer ca_soi`

Options: `--headless`, `--mock-llm`, `--output result.json`
