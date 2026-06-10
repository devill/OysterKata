"""Diff-reporter wiring for the approval suite.

Quiet and non-interactive in CI (the CI env var is set); locally, launch the
first working diff tool ApprovalTests can find so received-vs-approved opens for
review, falling back to the Python-native reporter if none is available.

This file also lives in tests/, which pytest's rootdir-insertion places on
sys.path, so the test can import the sibling `scenario_support` module.
"""

import os

from approvaltests import set_default_reporter
from approvaltests.reporters.generic_diff_reporter_factory import (
    GenericDiffReporterFactory,
)
from approvaltests.reporters.python_native_reporter import PythonNativeReporter


def pytest_configure(config):
    set_default_reporter(_reporter_for_environment())


def _reporter_for_environment():
    if os.environ.get("CI"):
        return PythonNativeReporter()
    return GenericDiffReporterFactory().get_first_working() or PythonNativeReporter()
