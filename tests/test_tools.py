"""Each tool, on fake data. No network and no approval in this file."""

import pytest

from errors import AgentError
from sample_data import get_escalation
from tools import (
    TOOLS,
    call_tool,
    check_recent_deploys,
    draft_customer_update,
    evidence_is_linked,
    propose_action,
    rank_hypotheses,
    read_logs,
    search_runbooks,
)


def _evidence(escalation_id):
    escalation = get_escalation(escalation_id)
    rows = list(read_logs(escalation_id)["evidence"])
    rows.extend(check_recent_deploys(escalation["service"])["evidence"])
    return rows


def test_search_runbooks_finds_the_rollback_section():
    hits = search_runbooks(get_escalation("ESC-1001")["ticket"])
    assert hits
    assert hits[0]["section"] == "Rollback a bad deploy"
    assert hits[0]["source"] == "rollback_bad_deploy.txt"
    assert hits[0]["score"] > 0


def test_search_runbooks_empty_when_nothing_matches():
    assert search_runbooks(get_escalation("ESC-1003")["ticket"]) == []
    assert search_runbooks("the and for") == []
    assert search_runbooks("") == []


def test_search_runbooks_rejects_a_non_string():
    with pytest.raises(AgentError) as caught:
        search_runbooks(None)
    assert caught.value.name == "BAD_TOOL_ARGS"


def test_read_logs_returns_evidence_ids():
    result = read_logs("ESC-1001")
    assert [row["id"] for row in result["evidence"]] == ["log-1", "log-2"]
    assert "checkout-api.log" in result["evidence"][0]["source"]


def test_read_logs_unknown_escalation_is_named():
    with pytest.raises(AgentError) as caught:
        read_logs("ESC-9999")
    assert caught.value.name == "UNKNOWN_ESCALATION"


def test_check_recent_deploys_returns_the_failed_practice_deploy():
    result = check_recent_deploys("checkout-api")
    assert len(result["deploys"]) == 1
    assert result["deploys"][0]["status"] == "failed"
    assert result["deploys"][0]["version"] == "2.4.1"
    assert result["evidence"][0]["id"] == "deploy-1"
    assert result["evidence"][0]["source"] == "deploys/checkout-api"


def test_check_recent_deploys_does_not_leak_across_services():
    result = check_recent_deploys("checkout-web")
    assert [deploy["service"] for deploy in result["deploys"]] == ["checkout-web"]
    assert result["deploys"][0]["status"] == "succeeded"


def test_rank_hypotheses_links_checkout_evidence_to_bad_deploy():
    result = rank_hypotheses(_evidence("ESC-1001"))
    top = result["hypotheses"][0]
    assert top["title"] == "Bad deploy"
    assert top["status"] == "unverified"
    assert top["supporting_evidence_ids"] == ["log-1", "log-2", "deploy-1"]
    assert result["confirmed_root_cause"] is None
    assert result["action_mode"] == "simulation_only"
    assert all(item["status"] == "unverified" for item in result["hypotheses"])


def test_rank_hypotheses_links_worker_and_outage_cases():
    worker = rank_hypotheses(_evidence("ESC-1002"))["hypotheses"][0]
    outage = rank_hypotheses(_evidence("ESC-1005"))["hypotheses"][0]
    assert worker["title"] == "Process needs a restart"
    assert worker["supporting_evidence_ids"] == ["log-1", "log-2"]
    assert outage["title"] == "Customer-facing outage"
    assert "log-1" in outage["supporting_evidence_ids"]
    assert "log-2" in outage["supporting_evidence_ids"]


def test_rank_hypotheses_leaves_the_slow_dashboard_unlinked():
    result = rank_hypotheses(_evidence("ESC-1004"))
    assert not evidence_is_linked(result["hypotheses"])
    assert result["confirmed_root_cause"] is None


def test_rank_hypotheses_rejects_a_duplicate_id():
    rows = _evidence("ESC-1001")
    rows.append(dict(rows[0]))
    with pytest.raises(AgentError) as caught:
        rank_hypotheses(rows)
    assert caught.value.name == "EVIDENCE_INVALID"


def test_draft_customer_update_is_text_only_and_drops_invented_ids():
    draft = draft_customer_update(
        "ESC-1001",
        "gold",
        "checkout-api",
        "Checkout returns 500.",
        "Bad deploy",
        ["log-1", "made-up", "log-1"],
    )
    assert draft["sent"] is False
    assert "not sent" in draft["text"].lower()
    assert "not confirmed" in draft["text"].lower()
    assert "log-1" in draft["text"]
    assert "made-up" not in draft["text"]
    assert "gold" in draft["text"]


def test_propose_action_does_not_write_and_ignores_approved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = propose_action(
        "rollback",
        "checkout-api",
        "Bad deploy is leading.",
        approved=True,
    )
    assert result["status"] == "pending"
    assert "approved" not in result
    assert result["kind"] == "rollback"
    assert "2.4.1" in result["details"]
    assert "2.4.0" in result["details"]
    assert list(tmp_path.iterdir()) == []


def test_propose_action_unknown_kind_is_named():
    with pytest.raises(AgentError) as caught:
        propose_action("delete_database", "checkout-api", "no")
    assert caught.value.name == "UNKNOWN_ACTION"


def test_record_simulated_action_is_not_a_model_tool():
    assert "record_simulated_action" not in TOOLS
    with pytest.raises(AgentError) as caught:
        call_tool("record_simulated_action", {})
    assert caught.value.name == "UNKNOWN_TOOL"


def test_call_tool_strips_approved_before_propose(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = call_tool(
        "propose_action",
        {"kind": "restart", "target": "image-worker", "reason": "memory", "approved": "yes"},
    )
    assert result["status"] == "pending"
    assert "approved" not in result
    assert list(tmp_path.iterdir()) == []
