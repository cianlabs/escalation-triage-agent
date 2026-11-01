"""The step budget is checked before every model call."""

import pytest

from agent import MAX_STEPS, run_escalation
from errors import AgentError
from turns import ModelTurn


class NeverDone:
    def __init__(self):
        self.calls = 0

    def next_turn(self, state, last_result=None):
        del state, last_result
        self.calls += 1
        return ModelTurn(
            kind="tool",
            name="search_runbooks",
            arguments={"query": "checkout deploy 500 error rate"},
            thought="Keep searching.",
        )


def test_step_limit_does_not_call_the_model_again(sandbox):
    model = NeverDone()
    result = run_escalation(
        "ESC-1001",
        model=model,
        memory_dir=sandbox["memory_dir"],
        action_log=sandbox["action_log"],
        max_steps=3,
        ask=lambda _prompt: "y",
    )
    assert result.stop_reason == "MAX_STEPS_REACHED"
    assert model.calls == 3
    assert result.state.steps_used == 3
    assert not sandbox["action_log"].exists()


def test_default_budget_fits_the_six_tool_checklist():
    # Search, logs, deploys, rank, draft, propose. The human question is not a step.
    assert MAX_STEPS >= 6


def test_max_steps_of_zero_is_rejected(sandbox):
    with pytest.raises(AgentError) as caught:
        run_escalation(
            "ESC-1001",
            memory_dir=sandbox["memory_dir"],
            action_log=sandbox["action_log"],
            max_steps=0,
        )
    assert caught.value.name == "BAD_SETTINGS"
