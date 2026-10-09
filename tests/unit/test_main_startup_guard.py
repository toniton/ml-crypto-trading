import sys
from unittest.mock import patch
import pytest

from main import _assert_python_version


def test_main_startup_guard_blocks_old_python_versions():
    with patch.object(sys, "version_info", (3, 8, 10, "final", 0)):
        with pytest.raises(RuntimeError, match="Rio Trading requires Python 3.11+"):
            _assert_python_version()


def test_main_startup_guard_passes_on_supported_version():
    with patch.object(sys, "version_info", (3, 12, 0, "final", 0)):
        _assert_python_version()
