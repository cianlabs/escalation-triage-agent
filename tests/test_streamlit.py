"""Streamlit demo helpers. Streamlit itself is optional."""

import agent
import streamlit_app
from sample_data import SAMPLE_ID


def _store():
    return {}


def test_picker_can_run_an_added_demo_sample(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    session = streamlit_app.ensure_session(_store())
    view = streamlit_app.on_sample(session, "ESC-2001")
    assert view["error"] == ""
    assert view["escalation_id"] == "ESC-2001"
    assert view["stop_reason"] == agent.APPROVAL_REQUIRED
    assert view["citations"] != "No runbook sections were cited."
    assert "redis_memory.txt" in view["citations"] or "worker_memory.txt" in view["citations"]


def test_sample_choices_include_new_demo_titles():
    choices = streamlit_app.sample_choices()
    assert SAMPLE_ID in choices.values()
    assert "ESC-2001" in choices.values()
    assert any("Redis cache memory pressure" in label for label in choices)
