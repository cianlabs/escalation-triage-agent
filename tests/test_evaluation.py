"""Tests for evaluation and data loading."""

from evaluation import run_incident_evaluation
from sample_data import REAL_ESCALATIONS, list_real_incidents


def test_real_escalations_catalog():
    escalations = list_real_incidents()
    assert len(escalations) == 12
    for esc in escalations:
        assert esc["id"].startswith("INC-")
        assert "logs" in esc
        assert "deploys" in esc
        assert "published_root_cause" in esc


def test_reconstructed_logs_labeled():
    for esc in list_real_incidents():
        for log in esc["logs"]:
            assert "reconstructed" in log["source"]
        for dep in esc["deploys"]:
            assert "reconstructed" in dep["note"]


def test_evaluation_runs_and_scores():
    eval_res = run_incident_evaluation()
    assert eval_res["total"] == 12
    assert eval_res["correct"] == 12
    assert eval_res["score"] == 1.0
    for item in eval_res["results"]:
        assert item["match"] is True
