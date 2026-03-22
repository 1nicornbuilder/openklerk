"""Tests for scaffold generator."""
import os
import tempfile
import pytest
from unittest.mock import patch

from openklerk.contrib.scaffold import (
    to_class_name,
    state_to_code,
    create_filer_scaffold,
)


class TestScaffoldHelpers:

    def test_to_class_name(self):
        assert to_class_name("Oregon", "Annual Report") == "OregonAnnualReportFiler"
        assert to_class_name("New York", "Biennial Statement") == "NewYorkBiennialStatementFiler"

    def test_state_to_code(self):
        assert state_to_code("California") == "CA"
        assert state_to_code("Oregon") == "OR"
        assert state_to_code("New York") == "NY"
        assert state_to_code("Texas") == "TX"

    def test_state_to_code_unknown(self):
        # Unknown states use first 2 chars uppercased
        assert state_to_code("Atlantis") == "AT"


class TestCreateScaffold:

    def test_creates_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = os.getcwd()
            try:
                os.chdir(tmpdir)
                os.makedirs("openklerk/filers", exist_ok=True)
                os.makedirs("tests", exist_ok=True)

                create_filer_scaffold("Oregon", "Annual Report")

                assert os.path.exists("openklerk/filers/oregon_annual_report.py")
                assert os.path.exists("tests/test_oregon_annual_report.py")
                assert os.path.exists("openklerk/filers/oregon_annual_report_config.json")

                # Check filer content
                with open("openklerk/filers/oregon_annual_report.py") as f:
                    content = f.read()
                assert "OregonAnnualReportFiler" in content
                assert "BaseStateFiler" in content
                assert "OR" in content

                # Check test content
                with open("tests/test_oregon_annual_report.py") as f:
                    content = f.read()
                assert "OregonAnnualReportFiler" in content
            finally:
                os.chdir(orig_dir)
