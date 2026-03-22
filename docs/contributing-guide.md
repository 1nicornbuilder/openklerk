# Filer Development Guide

See CONTRIBUTING.md in the project root for the full guide.

## Key Patterns

- Every filer extends `BaseStateFiler`
- Steps are defined in `get_steps()` as `FilingStep` objects
- Browser automation uses `BrowserEngine` (Playwright wrapper)
- Use `human_type()`, `human_click()` for realistic behavior
- Check for pre-populated fields before filling
- Use `domcontentloaded` not `networkidle` for government portals
- React SPAs need `nativeInputValueSetter` + `dispatchEvent`
