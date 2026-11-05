"""The agent eval set runs offline and writes an inspectable trace."""

import json
from pathlib import Path

from agent_eval import GOLDEN, HOLDOUT, load_cases, run_case, run_eval


def test_datasets_are_synthetic_and_unique():
    cases = load_cases((GOLDEN, HOLDOUT))
    assert len(cases) >= 15
    blob = GOLDEN.read_text(encoding="utf-8") + HOLDOUT.read_text(encoding="utf-8")
    assert "sk-" not in blob
    assert "XAI_API_KEY" not in blob
    for case in cases:
        assert case["id"]
        assert case["dataset_id"].startswith("agent-eval-")


def test_eval_set_passes_and_writes_traces(tmp_path):
    rows = run_eval(tmp_path)
    failed = [row["id"] for row in rows if not row["passed"]]
    assert failed == []
    for row in rows:
        trace = json.loads(Path(row["trace"]).read_text(encoding="utf-8"))
        assert trace["case_id"] == row["id"]
        assert trace["passed"] is True
        assert isinstance(trace["elapsed_ms"], float)
        assert trace["events"]
        assert "checks" in trace


def test_failed_case_still_writes_a_trace(tmp_path):
    case = {
        "id": "Z99-forced-miss",
        "dataset_id": "agent-eval-test",
        "kind": "triage",
        "escalation_id": "ESC-1003",
        "human": "n",
        "expect": {"stop_reason": "TRIAGE_COMPLETE", "action_logged": True},
    }
    sandbox = {"memory_dir": tmp_path / "memory", "action_log": tmp_path / "action.log"}
    checks, path = run_case(case, tmp_path / "traces", sandbox)
    assert any(not item["passed"] for item in checks)
    trace = json.loads(path.read_text(encoding="utf-8"))
    assert trace["passed"] is False
    assert trace["stop_reason"] == "NO_RUNBOOK_MATCH"
    assert trace["events"][0]["name"] == "search_runbooks"
    assert not (tmp_path / "action.log").exists()
