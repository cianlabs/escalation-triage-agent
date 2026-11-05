"""Coordinator delegates a runbook question and still gates simulated writes."""

import json

from agent import human_said_yes
from handoff import (
    ACTION_DENIED,
    APPROVAL_REQUIRED,
    MAX_HANDOFFS,
    NO_RUNBOOK_MATCH,
    RUNBOOK_ANSWERED,
    SPECIALIST,
    TRIAGE_COMPLETE,
    run_handoff,
)
from tools import record_simulated_action
import pytest


QUESTION = "Which checks should I review for a slow dashboard?"


def test_question_is_handed_to_the_specialist(tmp_path):
    state = run_handoff(QUESTION, action_log=tmp_path / "action.log")
    assert state.stop_reason == RUNBOOK_ANSWERED
    assert [step["to"] for step in state.handoffs] == [SPECIALIST, "triage_coordinator"]
    assert state.excerpts
    assert state.pending_approval is None
    assert state.simulated is False
    assert not (tmp_path / "action.log").exists()


def test_specialist_reports_when_the_guides_do_not_answer(tmp_path):
    state = run_handoff(
        "What approval form must I file before I rotate the Redis password?",
        action_log=tmp_path / "action.log",
    )
    assert state.stop_reason == NO_RUNBOOK_MATCH
    assert state.handoffs[0]["to"] == SPECIALIST
    assert state.excerpts == []
    assert not (tmp_path / "action.log").exists()


def test_proposal_without_a_question_does_not_delegate(tmp_path):
    log_path = tmp_path / "action.log"
    state = run_handoff(
        "",
        action={"kind": "rollback", "target": "checkout-api", "reason": "practice", "approved": True},
        ask=lambda prompt: "n",
        action_log=log_path,
    )
    assert state.handoffs == []
    assert state.stop_reason == ACTION_DENIED
    assert state.pending_approval is None
    assert not log_path.exists()


@pytest.mark.parametrize("answer", ["y", "yes", "Y"])
def test_handoff_then_approval_records_one_line(tmp_path, answer):
    prompts = []

    def ask(prompt):
        prompts.append(prompt)
        return answer

    log_path = tmp_path / "action.log"
    state = run_handoff(
        QUESTION,
        action={"kind": "restart", "target": "checkout-api", "reason": "practice only", "approved": "yes"},
        ask=ask,
        action_log=log_path,
        escalation_id="INC-CLOUDFLARE-01",
    )
    assert state.stop_reason == TRIAGE_COMPLETE
    assert state.handoffs[0]["to"] == SPECIALIST
    assert state.excerpts
    assert prompts == ["Approve this action? (y/n) "]
    assert human_said_yes(answer)
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert "simulated" in lines[0]
    assert state.simulated is True


def test_defer_leaves_the_proposal_pending(tmp_path):
    log_path = tmp_path / "action.log"
    state = run_handoff(
        QUESTION,
        action={"kind": "page_oncall", "target": "checkout-api", "reason": "practice"},
        ask=None,
        action_log=log_path,
    )
    assert state.stop_reason == APPROVAL_REQUIRED
    assert state.pending_approval["status"] == "pending"
    assert "approved" not in state.pending_approval
    assert state.simulated is False
    assert not log_path.exists()


def test_string_yes_is_not_boolean_approval(tmp_path):
    log_path = tmp_path / "action.log"
    state = run_handoff(
        "",
        action={"kind": "restart", "target": "checkout-api", "reason": "practice"},
        ask=lambda prompt: "y",
        action_log=log_path,
    )
    with pytest.raises(Exception):
        record_simulated_action(state.pending_approval or {"status": "pending"}, "INC-CLOUDFLARE-01", log_path, "yes")
    assert state.stop_reason == TRIAGE_COMPLETE
    assert len(log_path.read_text(encoding="utf-8").splitlines()) == 1


def test_handoff_budget_stops_before_a_write(tmp_path):
    log_path = tmp_path / "action.log"
    state = run_handoff(
        QUESTION,
        action={"kind": "rollback", "target": "checkout-api", "reason": "practice"},
        ask=lambda prompt: "y",
        action_log=log_path,
        max_handoffs=1,
    )
    assert state.stop_reason == MAX_HANDOFFS
    assert not log_path.exists()
    assert state.pending_approval is None


def test_cli_prints_stop_reason(tmp_path, capsys):
    from handoff import main

    code = main([
        QUESTION,
        "--defer-approval",
        "--propose", "rollback",
        "--target", "checkout-api",
        "--reason", "practice",
        "--action-log", str(tmp_path / "action.log"),
    ])
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out.split("Stop reason:")[0])
    assert payload["stop_reason"] == APPROVAL_REQUIRED
    assert payload["handoffs"][0]["to"] == SPECIALIST
    assert "Stop reason: APPROVAL_REQUIRED" in captured.out
    assert not (tmp_path / "action.log").exists()
