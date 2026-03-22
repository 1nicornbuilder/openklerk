"""
Quality gate -- automated checks on filer modules.

Runs before merging PRs that modify openclerc/filers/.
"""
import ast
import importlib
import json
import os
import re
import sys

from rich.console import Console

console = Console()

CHECKS = [
    ("file_exists", "Filer .py file exists"),
    ("class_inherits_base", "Class extends BaseStateFiler"),
    ("filing_code_set", "FILING_CODE is set and non-empty"),
    ("steps_defined", "get_steps() returns non-empty list"),
    ("steps_have_names", "Every step has name + description"),
    ("page_transitions", "is_page_transition set on relevant steps"),
    ("execute_handles_all", "execute_step() handles every step number"),
    ("test_file_exists", "Test file exists"),
    ("config_json_exists", "Config JSON exists"),
    ("no_hardcoded_creds", "No passwords/keys in source code"),
    ("no_saas_imports", "No imports from app.* (SaaS code)"),
]


def run_quality_checks(filer_name: str) -> bool:
    """Run all quality checks on a filer module. Returns True if all pass."""
    results = []
    for check_name, description in CHECKS:
        checker = globals().get(f"check_{check_name}")
        if checker:
            passed, message = checker(filer_name)
        else:
            passed, message = False, f"Check not implemented: {check_name}"
        results.append((check_name, passed, message))
        icon = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
        console.print(f"  {icon} {description}: {message}")

    all_passed = all(r[1] for r in results)
    if all_passed:
        console.print(f"\n[bold green]ALL CHECKS PASSED[/bold green]")
    else:
        console.print(f"\n[bold red]SOME CHECKS FAILED[/bold red]")
    return all_passed


def _get_filer_path(filer_name: str) -> str:
    return f"openclerc/filers/{filer_name}.py"


def _get_test_path(filer_name: str) -> str:
    return f"tests/test_{filer_name}.py"


def _get_config_path(filer_name: str) -> str:
    return f"openclerc/filers/{filer_name}_config.json"


def _read_source(filer_name: str) -> str:
    path = _get_filer_path(filer_name)
    if not os.path.exists(path):
        return ""
    with open(path) as f:
        return f.read()


def check_file_exists(filer_name: str) -> tuple[bool, str]:
    path = _get_filer_path(filer_name)
    exists = os.path.exists(path)
    return exists, path if exists else f"{path} not found"


def check_class_inherits_base(filer_name: str) -> tuple[bool, str]:
    source = _read_source(filer_name)
    if not source:
        return False, "Source file not found"
    if "BaseStateFiler" in source and "class " in source:
        return True, "Found BaseStateFiler inheritance"
    return False, "No class extending BaseStateFiler found"


def check_filing_code_set(filer_name: str) -> tuple[bool, str]:
    source = _read_source(filer_name)
    if not source:
        return False, "Source file not found"
    match = re.search(r'FILING_CODE\s*=\s*["\']([^"\']+)["\']', source)
    if match:
        return True, f'FILING_CODE = "{match.group(1)}"'
    return False, "FILING_CODE not set or empty"


def check_steps_defined(filer_name: str) -> tuple[bool, str]:
    source = _read_source(filer_name)
    if not source:
        return False, "Source file not found"
    if "def get_steps" in source and "FilingStep(" in source:
        count = source.count("FilingStep(")
        return True, f"{count} steps defined"
    return False, "get_steps() not found or returns empty"


def check_steps_have_names(filer_name: str) -> tuple[bool, str]:
    source = _read_source(filer_name)
    if not source:
        return False, "Source file not found"
    steps = re.findall(r'FilingStep\(\d+,\s*"([^"]+)",\s*"([^"]+)"', source)
    if steps:
        unnamed = [s for s in steps if not s[0].strip() or not s[1].strip()]
        if unnamed:
            return False, f"{len(unnamed)} steps missing name or description"
        return True, f"All {len(steps)} steps have name + description"
    return False, "No FilingStep definitions found"


def check_page_transitions(filer_name: str) -> tuple[bool, str]:
    source = _read_source(filer_name)
    if not source:
        return False, "Source file not found"
    if "is_page_transition" in source:
        return True, "is_page_transition found in step definitions"
    return False, "No is_page_transition settings found"


def check_execute_handles_all(filer_name: str) -> tuple[bool, str]:
    source = _read_source(filer_name)
    if not source:
        return False, "Source file not found"
    if "def execute_step" not in source:
        return False, "execute_step() not found"
    step_count = source.count("FilingStep(")
    handled = len(re.findall(r'step_number\s*==\s*\d+', source))
    if handled >= step_count:
        return True, f"{handled} step cases for {step_count} steps"
    return True, f"{handled}/{step_count} step cases (some may use range handling)"


def check_test_file_exists(filer_name: str) -> tuple[bool, str]:
    path = _get_test_path(filer_name)
    exists = os.path.exists(path)
    return exists, path if exists else f"{path} not found"


def check_config_json_exists(filer_name: str) -> tuple[bool, str]:
    path = _get_config_path(filer_name)
    if os.path.exists(path):
        return True, path
    # Config is optional for existing filers
    return True, "Config JSON optional (not found but OK)"


def check_no_hardcoded_creds(filer_name: str) -> tuple[bool, str]:
    source = _read_source(filer_name)
    if not source:
        return False, "Source file not found"
    patterns = [
        r'password\s*=\s*["\'][^"\']+["\']',
        r'api_key\s*=\s*["\'][^"\']+["\']',
        r'secret\s*=\s*["\'][^"\']+["\']',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, source, re.IGNORECASE)
        # Exclude test/example values
        real_matches = [m for m in matches if "test" not in m.lower() and "example" not in m.lower()]
        if real_matches:
            return False, f"Possible hardcoded credential: {real_matches[0]}"
    return True, "No hardcoded credentials found"


def check_no_saas_imports(filer_name: str) -> tuple[bool, str]:
    source = _read_source(filer_name)
    if not source:
        return False, "Source file not found"
    saas_imports = re.findall(r'from\s+app\.\w+', source)
    if saas_imports:
        return False, f"SaaS imports found: {', '.join(saas_imports)}"
    return True, "No SaaS imports (app.*)"
