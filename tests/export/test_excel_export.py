"""
Test Excel export functionality.

Tests that the write_excel() method provides clear error guidance when the
optional xlsxwriter dependency is not installed.
"""

import sys
import unittest.mock
import pytest
from battery_optimizer.export import Exporter


class TestWriteExcelMissingDependency:
    """Test that write_excel raises a clear ImportError when xlsxwriter is missing."""

    def test_write_excel_without_xlsxwriter_raises_import_error(self, tmp_path):
        """
        Test that calling write_excel() without xlsxwriter raises a clear ImportError.

        When xlsxwriter is not installed, write_excel() should raise an ImportError
        with a message that tells the user how to install the required optional
        dependency, rather than a generic ModuleNotFoundError from inside pandas.
        """
        # Simulate xlsxwriter not being installed by hiding it from imports
        with unittest.mock.patch.dict(sys.modules, {"xlsxwriter": None}):
            mock_model = unittest.mock.MagicMock()
            exporter = Exporter(mock_model)

            with pytest.raises(ImportError, match=r"battery_optimizer\[excel\]"):
                exporter.write_excel(str(tmp_path / "output.xlsx"))

    def test_write_excel_without_xlsxwriter_error_message_is_helpful(
        self, tmp_path
    ):
        """
        Test that the ImportError message includes actionable install instructions.

        The error message should tell the user exactly what command to run to
        install the missing dependency.
        """
        with unittest.mock.patch.dict(sys.modules, {"xlsxwriter": None}):
            mock_model = unittest.mock.MagicMock()
            exporter = Exporter(mock_model)

            with pytest.raises(ImportError) as exc_info:
                exporter.write_excel(str(tmp_path / "output.xlsx"))

            error_message = str(exc_info.value)
            assert "xlsxwriter" in error_message
            assert "pip install battery_optimizer[excel]" in error_message
