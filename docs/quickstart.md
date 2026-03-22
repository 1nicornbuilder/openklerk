# Quick Start Guide

## Installation

```bash
git clone https://github.com/NeverMissAFiling/openklerk.git
cd openklerk
pip install -e ".[dev]"
playwright install chromium
```

## Verify

```bash
openklerk --version
openklerk list
```

## Run a Filing

1. Copy `examples/business_entity.json` and fill in your business details
2. Run: `openklerk run --config my_entity.json --filer ca_soi`

Options: `--headless`, `--mock-llm`, `--output result.json`
