"""A second run resumes from the JSON file instead of starting over."""

from agent import run_escalation
from practice_model import PracticeModel
from state import load_state


def test_resume_continues_the_checklist_without_repeating_the_search(sandbox):
    model = PracticeModel()
    first = run_escalation(
        "ESC-1001",
        model=model,
        memory_dir=sandbox["memory_dir"],
        action_log=sandbox["action_log"],
        max_steps=2,
        ask=lambda _prompt: "y",
    )
    assert first.stop_reason == "MAX_STEPS_REACHED"
    assert first.state.checked["runbooks"] is True
    assert first.state.checked["logs"] is True
    assert first.state.checked["deploys"] is False
    assert model.calls == 2

    second = run_escalation(
        "ESC-1001",
        model=model,
        memory_dir=sandbox["memory_dir"],
        action_log=sandbox["action_log"],
        ask=lambda _prompt: "n",
    )
    assert second.stop_reason == "ACTION_DENIED"
    assert second.state.checked["deploys"] is True
    assert sum(line.startswith("search_runbooks:") for line in second.state.step_log) == 1
    assert model.calls == 6
    assert not sandbox["action_log"].exists()
    # The second call loaded the file. It was not handed the first Python object.
    assert load_state("ESC-1001", sandbox["memory_dir"]).stop_reason == "ACTION_DENIED"


def test_resume_of_a_pending_approval_asks_once_and_writes_one_line(sandbox):
    first_model = PracticeModel()
    first = run_escalation(
        "ESC-1001",
        model=first_model,
        memory_dir=sandbox["memory_dir"],
        action_log=sandbox["action_log"],
        defer_approval=True,
    )
    assert first.stop_reason == "APPROVAL_REQUIRED"
    assert first.state.pending_approval["kind"] == "rollback"
    assert not sandbox["action_log"].exists()

    second_model = PracticeModel()
    prompts = []

    def ask(prompt):
        prompts.append(prompt)
        return "y"

    second = run_escalation(
        "ESC-1001",
        model=second_model,
        memory_dir=sandbox["memory_dir"],
        action_log=sandbox["action_log"],
        ask=ask,
    )
    assert second_model.calls == 0
    assert prompts == ["Approve this action? (y/n) "]
    assert second.stop_reason == "TRIAGE_COMPLETE"
    assert second.state.steps_used == first.state.steps_used
    lines = sandbox["action_log"].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert "simulated" in lines[0]
    assert "rollback" in lines[0]
    assert "ESC-1001" in lines[0]


def test_two_escalations_do_not_share_a_memory_file(sandbox):
    run_escalation(
        "ESC-1003",
        model=PracticeModel(),
        memory_dir=sandbox["memory_dir"],
        action_log=sandbox["action_log"],
    )
    run_escalation(
        "ESC-1004",
        model=PracticeModel(),
        memory_dir=sandbox["memory_dir"],
        action_log=sandbox["action_log"],
    )
    coffee = load_state("ESC-1003", sandbox["memory_dir"])
    slow = load_state("ESC-1004", sandbox["memory_dir"])
    assert coffee.escalation_id == "ESC-1003"
    assert slow.escalation_id == "ESC-1004"
    assert coffee.stop_reason == "NO_RUNBOOK_MATCH"
    assert slow.stop_reason == "INSUFFICIENT_EVIDENCE"
    assert "coffee" not in slow.ticket


def test_a_sticky_stop_does_not_run_tools_again(sandbox):
    run_escalation(
        "ESC-1003",
        model=PracticeModel(),
        memory_dir=sandbox["memory_dir"],
        action_log=sandbox["action_log"],
    )
    saved_log = list(load_state("ESC-1003", sandbox["memory_dir"]).step_log)
    again = PracticeModel()
    result = run_escalation(
        "ESC-1003",
        model=again,
        memory_dir=sandbox["memory_dir"],
        action_log=sandbox["action_log"],
        ask=lambda _prompt: "y",
    )
    assert result.stop_reason == "NO_RUNBOOK_MATCH"
    assert again.calls == 0
    assert result.state.step_log == saved_log
    assert not sandbox["action_log"].exists()
