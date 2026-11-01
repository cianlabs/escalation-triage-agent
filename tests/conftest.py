"""Shared fixtures. Every test stays on the local disk."""

import pytest


@pytest.fixture
def sandbox(tmp_path):
    """A private memory directory and action log for one test."""
    return {
        "memory_dir": tmp_path / "memory",
        "action_log": tmp_path / "action.log",
    }
