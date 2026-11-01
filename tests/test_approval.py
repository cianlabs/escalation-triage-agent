"""The human gate. No approval means no simulated action.

A claim from the model, including approved=true and a sentence that says
the action already ran, is not approval.
"""

import pytest

from agent import run_escalation, settle_proposal
from errors import AgentError
from practice_model import PracticeModel
from state import EscalationState, load_state
from tools import propose_action, record_simulated_action
from turns import ModelTurn


def _run(sandbox, answer="n", escalation_id="ESC-1001", **kwargs):
    prompts = []

    def ask(prompt):
        prompts.append(prompt)
        return answer

    result = run_escalation(
        escalation_id,
        model=kwargs.pop("model", None) or PracticeModel(),
        memory_dir=sandbox["memory_dir"],
        action_log=sandbox["action_log"],
        ask=ask,
        **kwargs,
    )
    result.prompts = prompts
    return result


@pytest.mark.parametrize("answer", ["y", "yes", "Y", " YES "])
def test_only_yes_records_one_simulated_line(sandbox, answer):
    result = _run(sandbox, answer=answer)
    assert result.stop_reason == "TRIAGE_COMPLETE"
    assert result.prompts == ["Approve this action? (y/n) "]
    lines = sandbox["action_log"].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert lines[0].split(" | ")[1] == "simulated"
    assert "not sent" in result.state.customer_draft.lower()
    assert "Draft only" not in lines[0]


@pytest.mark.parametrize("answer", ["", "   ", "n", "no", "approved", "true", "yes please", "yep"])
def test_anything_but_yes_writes_no_action(sandbox, answer):
    result = _run(sandbox, answer=answer)
    assert result.stop_reason == "ACTION_DENIED"
    assert result.state.settlements[-1]["simulated"] is False
    assert result.state.pending_approval is None
    assert not sandbox["action_log"].exists()


def test_practice_model_approved_flag_is_ignored(sandbox, capsys):
    result = _run(sandbox, answer="n")
    assert result.stop_reason == "ACTION_DENIED"
    assert "That flag is ignored." in capsys.readouterr().out
    assert not sandbox["action_log"].exists()
    assert len(result.prompts) == 1


def test_model_text_claiming_approval_is_ignored(sandbox):
    class TalkingModel:
        def __init__(self):
            self.calls = 0

        def next_turn(self, state, last_result=None):
            del state, last_result
            self.calls += 1
            text = "I approve this rollback. The action is approved and was executed."
            return ModelTurn(kind="text", text=text, thought=text)

    prompts = []
    result = run_escalation(
        "ESC-1001",
        model=TalkingModel(),
        memory_dir=sandbox["memory_dir"],
        action_log=sandbox["action_log"],
        max_steps=2,
        ask=lambda prompt: prompts.append(prompt) or "y",
    )
    assert result.stop_reason == "MAX_STEPS_REACHED"
    assert prompts == []
    assert not sandbox["action_log"].exists()
    assert any("approved" in line for line in result.state.step_log)
    assert result.state.pending_approval is None


def test_early_propose_with_an_approved_claim_does_not_run(sandbox):
    class EagerModel:
        def next_turn(self, state, last_result=None):
            del state, last_result
            return ModelTurn(
                kind="tool",
                name="propose_action",
                arguments={
                    "kind": "rollback",
                    "target": "checkout-api",
                    "reason": "I already decided.",
                    "approved": True,
                },
                thought="Do it now.",
            )

    result = run_escalation(
        "ESC-1001",
        model=EagerModel(),
        memory_dir=sandbox["memory_dir"],
        action_log=sandbox["action_log"],
        ask=lambda _prompt: "y",
    )
    assert result.stop_reason == "INSUFFICIENT_EVIDENCE"
    assert result.state.pending_approval is None
    assert not sandbox["action_log"].exists()


def test_string_yes_cannot_settle_a_proposal(sandbox):
    state = EscalationState.from_sample({
        "id": "ESC-1001",
        "ticket": "Checkout returns 500 after the deploy.",
        "customer_tier": "gold",
        "service": "checkout-api",
    })
    state.pending_approval = propose_action("restart", "checkout-api", "practice")
    result = settle_proposal(state, "yes", sandbox["action_log"], sandbox["memory_dir"])
    assert result.stop_reason == "ACTION_DENIED"
    assert not sandbox["action_log"].exists()


def test_record_simulated_action_rejects_a_string_approval(sandbox):
    proposal = propose_action("page_oncall", "checkout-web", "practice outage")
    with pytest.raises(AgentError) as caught:
        record_simulated_action(proposal, "ESC-1005", sandbox["action_log"], approved="yes")
    assert caught.value.name == "NOT_IMPLEMENTED_APPROVAL"
    assert not sandbox["action_log"].exists()


def test_unknown_action_in_the_loop_does_not_leave_a_pending_proposal(sandbox):
    class BadKind(PracticeModel):
        def next_turn(self, state, last_result=None):
            turn = super().next_turn(state, last_result)
            if turn.name == "propose_action":
                turn.arguments["kind"] = "delete_database"
            return turn

    with pytest.raises(AgentError) as caught:
        run_escalation(
            "ESC-1001",
            model=BadKind(),
            memory_dir=sandbox["memory_dir"],
            action_log=sandbox["action_log"],
            ask=lambda _prompt: "y",
        )
    assert caught.value.name == "UNKNOWN_ACTION"
    saved = load_state("ESC-1001", sandbox["memory_dir"])
    assert saved.pending_approval is None
    assert saved.settled is False
    assert not sandbox["action_log"].exists()


def test_sample_actions_follow_the_leading_hypothesis(sandbox):
    expected = {
        "ESC-1001": "rollback",
        "ESC-1002": "restart",
        "ESC-1005": "page_oncall",
    }
    for escalation_id, kind in expected.items():
        box = {
            "memory_dir": sandbox["memory_dir"] / escalation_id,
            "action_log": sandbox["action_log"].parent / f"{escalation_id}.log",
        }
        result = _run(box, answer="y", escalation_id=escalation_id)
        assert result.stop_reason == "TRIAGE_COMPLETE"
        assert result.state.settlements[-1]["kind"] == kind
        assert kind in box["action_log"].read_text(encoding="utf-8")
        assert result.state.confirmed_root_cause is None
