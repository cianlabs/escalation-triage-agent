"""Streamlit handlers. Practice model only. No API key and no network.

AppTest runs only when Streamlit is installed. The handler tests do not import it.
"""

import os

import pytest

import agent
import streamlit_app
from sample_data import SAMPLE_ID


def _store():
    return {}


def test_sample_triage_stops_for_approval_and_writes_nothing(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    session = streamlit_app.ensure_session(_store())
    view = streamlit_app.on_sample(session)
    assert view["error"] == ""
    assert view["stop_reason"] == agent.APPROVAL_REQUIRED
    assert view["escalation_id"] == SAMPLE_ID
    assert "1." in view["hypotheses"]
    assert "Confirmed root cause: none" in view["hypotheses"]
    assert view["draft"] and view["draft"] != "(no draft)"
    assert "not sent" in view["summary"].lower() or "Nothing has been simulated" in view["summary"]
    assert view["pending"].startswith("Nothing has run yet.")
    assert "kind:" in view["pending"]
    assert view["citations"] != "No runbook sections were cited."
    assert "propose_action:" in view["trace"]
    assert view["log_text"] == ""
    assert not session["action_log"].exists()


def test_refuse_writes_nothing(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    session = streamlit_app.ensure_session(_store())
    streamlit_app.on_sample(session)
    view = streamlit_app.on_refuse(session)
    assert view["error"] == ""
    assert view["stop_reason"] == agent.ACTION_DENIED
    assert view["pending"] == ""
    assert view["log_text"] == ""
    assert not session["action_log"].exists()
    assert "denied" in view["trace"]


def test_approve_appends_one_simulated_line(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    session = streamlit_app.ensure_session(_store())
    pending = streamlit_app.on_sample(session)
    kind = pending["pending"].split("kind: ", 1)[1].split("\n", 1)[0]
    view = streamlit_app.on_approve(session)
    assert view["error"] == ""
    assert view["stop_reason"] == agent.TRIAGE_COMPLETE
    assert view["pending"] == ""
    assert "simulated" in view["log_text"]
    assert kind in view["log_text"]
    assert SAMPLE_ID in view["log_text"]
    assert session["action_log"].read_text(encoding="utf-8").count("\n") == 1
    assert "human approved; simulated" in view["trace"]


def test_two_sessions_do_not_share_a_pending_action(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    first = streamlit_app.ensure_session(_store())
    second = streamlit_app.ensure_session(_store())
    streamlit_app.on_sample(first)
    streamlit_app.on_approve(first)
    assert first["action_log"] != second["action_log"]
    assert first["action_log"].exists()
    assert not second["action_log"].exists()
    other = streamlit_app.on_sample(second)
    assert other["stop_reason"] == agent.APPROVAL_REQUIRED
    assert other["log_text"] == ""
    # Approving the second session must not append a second line to the first log.
    before = first["action_log"].read_text(encoding="utf-8")
    streamlit_app.on_approve(second)
    assert first["action_log"].read_text(encoding="utf-8") == before
    assert before.count("\n") == 1
    second_text = second["action_log"].read_text(encoding="utf-8")
    assert "simulated |" in second_text
    assert second["action_log"] != first["action_log"]


def test_secret_turns_on_live_mode_without_showing_the_key(monkeypatch):
    secret = "sk-live-test-secret-do-not-leak"
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    streamlit_app.apply_streamlit_secret({"XAI_API_KEY": secret})
    banner = streamlit_app.mode_banner()
    assert os.environ.get("XAI_API_KEY") == secret
    assert "Live mode" in banner
    assert secret not in banner
    assert secret not in streamlit_app.mode_banner()


def test_missing_secret_stays_in_practice_mode(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    class Boom(dict):
        def __contains__(self, key):
            raise RuntimeError("no secrets file")

    streamlit_app.apply_streamlit_secret(Boom())
    streamlit_app.apply_streamlit_secret({})
    assert os.environ.get("XAI_API_KEY", "") == ""
    assert "Practice mode" in streamlit_app.mode_banner()


def test_an_existing_environment_key_is_not_replaced(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "already-set")
    streamlit_app.apply_streamlit_secret({"XAI_API_KEY": "sk-other-secret"})
    assert os.environ["XAI_API_KEY"] == "already-set"
    assert "sk-other-secret" not in streamlit_app.mode_banner()


def test_main_refuses_to_start_without_streamlit(monkeypatch):
    monkeypatch.setattr(streamlit_app, "st", None)
    with pytest.raises(RuntimeError, match="Streamlit is not installed"):
        streamlit_app.main()


def test_apptest_sample_refuse_and_approve(monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    monkeypatch.delenv("XAI_API_KEY", raising=False)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app = AppTest.from_file(os.path.join(root, "streamlit_app.py"), default_timeout=30)
    app.run()
    assert not app.exception
    sample = _button(app, "Run the practice sample")
    sample.click().run()
    assert not app.exception
    text = _page_text(app)
    assert "APPROVAL_REQUIRED" in text
    assert "Nothing has run yet." in text
    assert "Practice mode" in text

    refuse = _button(app, "Do not run")
    refuse.click().run()
    assert not app.exception
    refused = _page_text(app)
    assert "ACTION_DENIED" in refused
    assert "simulated |" not in refused

    again = _button(app, "Run the practice sample")
    again.click().run()
    approve = _button(app, "Approve and simulate")
    approve.click().run()
    assert not app.exception
    approved = _page_text(app)
    assert "TRIAGE_COMPLETE" in approved
    assert "simulated |" in approved
    assert "sk-" not in approved


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


def _button(app, label):
    matches = [button for button in app.button if button.label == label]
    assert matches, f"missing button {label!r}; saw {[button.label for button in app.button]}"
    return matches[0]


def _page_text(app):
    chunks = []
    for widget in list(app.markdown) + list(app.text) + list(app.caption) + list(getattr(app, "write", [])):
        chunks.append(str(getattr(widget, "value", "") or getattr(widget, "body", "")))
    return "\n".join(chunks)
