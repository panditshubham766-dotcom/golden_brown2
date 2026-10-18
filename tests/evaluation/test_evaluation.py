"""Pytest hook for Phase 6 evaluation runner."""
from pathlib import Path
from tests.evaluation.evaluate_core import test_evaluate_core


def test_core_evaluation_suite(tmp_path: Path):
    """Run core evaluation suite test to verify Phase 6 execution and metrics."""
    test_evaluate_core(tmp_path)
