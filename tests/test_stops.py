"""One test per named stop reason.

The names are the contract in agent.STOP_REASONS. A new name has to grow
this list or the parametrized test fails the collection of reasons.
"""

import pytest

from agent import STOP_REASONS, run_escalation
from practice_model import PracticeModel
from turns import ModelTurn


class _LoopingSearch:
    """Keeps searching. Used to prove the step budget stops the loop."""

    def __init__(self):
        self.calls = 0

    def next_turn(self, state, last_result=None):
        del state, last_result
        self.calls += 1
        return ModelTurn(
            kind="tool",
            name="search_runbooks",
            arguments={"query": "checkout deploy 500 error rate"},
            thought="Search again.",
        )


class _UnknownTool:
    def next_turn(self, state, last_result=None):
        del state, last_result
        return ModelTurn(kind="tool", name="drop_database", arguments={}, thought="Drop it.")


def _drive(reason, sandbox):
    common = {
        "memory_dir": sandbox["memory_dir"],
        "action_log": sandbox["action_log"],
    }
    if reason == "TRIAGE_COMPLETE":
        return run_escalation("ESC-1001", model=PracticeModel(), ask=lambda _prompt: "y", **common)
    if reason == "ACTION_DENIED":
        return run_escalation("ESC-1001", model=PracticeModel(), ask=lambda _prompt: "n", **common)
    if reason == "APPROVAL_REQUIRED":
        return run_escalation(
            "ESC-1001",
            model=PracticeModel(),
            ask=lambda _prompt: pytest.fail("defer must not ask"),
            defer_approval=True,
            **common,
        )
    if reason == "MAX_STEPS_REACHED":
        model = _LoopingSearch()
        result = run_escalation("ESC-1001", model=model, max_steps=3, ask=lambda _prompt: "y", **common)
        assert model.calls == 3
        return result
    if reason == "ALREADY_RESOLVED":
        run_escalation("ESC-1001", model=PracticeModel(), ask=lambda _prompt: "y", **common)
        second = PracticeModel()
        result = run_escalation(
            "ESC-1001",
            model=second,
            ask=lambda _prompt: pytest.fail("a settled case must not ask again"),
            **common,
        )
        assert second.calls == 0
        return result
    if reason == "NO_RUNBOOK_MATCH":
        return run_escalation("ESC-1003", model=PracticeModel(), ask=lambda _prompt: "y", **common)
    if reason == "INSUFFICIENT_EVIDENCE":
        return run_escalation("ESC-1004", model=PracticeModel(), ask=lambda _prompt: "y", **common)
    if reason == "UNKNOWN_TOOL":
        return run_escalation("ESC-1001", model=_UnknownTool(), ask=lambda _prompt: "y", **common)
    raise AssertionError(f"no driver for {reason}")


@pytest.mark.parametrize("reason", STOP_REASONS, ids=list(STOP_REASONS))
def test_named_stop_reason(reason, sandbox):
    result = _drive(reason, sandbox)
    assert result.stop_reason == reason
    text = sandbox["action_log"].read_text(encoding="utf-8") if sandbox["action_log"].exists() else ""
    if reason in {"TRIAGE_COMPLETE", "ALREADY_RESOLVED"}:
        assert text.count(" | simulated | ") == 1
    else:
        assert text == ""

    if reason == "TRIAGE_COMPLETE":
        assert result.state.settled is True
        assert result.state.confirmed_root_cause is None
        assert "not sent" in result.state.customer_draft.lower()
    elif reason == "ACTION_DENIED":
        assert result.state.settled is True
        assert result.state.settlements[-1]["simulated"] is False
        assert result.state.pending_approval is None
    elif reason == "APPROVAL_REQUIRED":
        assert result.state.settled is False
        assert result.state.pending_approval["status"] == "pending"
    elif reason == "MAX_STEPS_REACHED":
        assert result.state.steps_used == 3
        assert result.state.settled is False
    elif reason == "ALREADY_RESOLVED":
        assert result.state.settled is True
        assert result.state.stop_reason == "TRIAGE_COMPLETE"
    elif reason == "NO_RUNBOOK_MATCH":
        assert result.state.runbook_hits == []
        assert result.state.hypotheses == []
        assert result.state.pending_approval is None
    elif reason == "INSUFFICIENT_EVIDENCE":
        assert result.state.hypotheses
        assert not any(item["supporting_evidence_ids"] for item in result.state.hypotheses)
        assert result.state.pending_approval is None
    elif reason == "UNKNOWN_TOOL":
        assert any(line.startswith("unknown tool:") for line in result.state.step_log)
        assert result.state.pending_approval is None
    else:
        raise AssertionError(f"unchecked stop reason {reason}")
