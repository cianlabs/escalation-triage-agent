"""The optional real-model path, driven by a fake client.

Nothing here opens a socket. The live key is not required, and a dummy
value set in the environment must not show up in the output or the state.
"""

import json
from types import SimpleNamespace

import pytest

from agent import MODEL, run_escalation
from errors import AgentError
from fake_client import FakeClient, tool_reply
from tools import TOOLS


ESC_1001_EVIDENCE = [
    {
        "id": "log-1",
        "source": "checkout-api.log (reconstructed from public write-up)",
        "observation": "checkout-api error rate jumped to 40 percent after the deploy",
    },
    {
        "id": "log-2",
        "source": "checkout-api.log (reconstructed from public write-up)",
        "observation": "POST /checkout returned 500",
    },
    {
        "id": "deploy-1",
        "source": "deploys/checkout-api",
        "observation": "error rate jumped right after the deploy of 2.4.1",
    },
]


def test_real_model_adapter_runs_offline_and_still_asks(sandbox):
    client = FakeClient(
        tool_reply("search_runbooks", {"query": "checkout 500"}, "call-1"),
        tool_reply("read_logs", {"escalation_id": "ESC-1001"}, "call-2"),
        tool_reply("check_recent_deploys", {"service": "checkout-api"}, "call-3"),
        tool_reply("rank_hypotheses", {"evidence": ESC_1001_EVIDENCE}, "call-4"),
        tool_reply(
            "draft_customer_update",
            {
                "escalation_id": "ESC-1001",
                "customer_tier": "gold",
                "service": "checkout-api",
                "symptom": "Checkout returns 500.",
                "hypothesis_title": "Bad deploy",
                "evidence_ids": ["log-1", "made-up"],
            },
            "call-5",
        ),
        tool_reply(
            "propose_action",
            {"kind": "rollback", "target": "checkout-api", "reason": "bad deploy", "approved": True},
            "call-6",
        ),
    )
    prompts = []
    result = run_escalation(
        "ESC-1001",
        use_real=True,
        client=client,
        memory_dir=sandbox["memory_dir"],
        action_log=sandbox["action_log"],
        ask=lambda prompt: prompts.append(prompt) or "y",
    )
    assert result.stop_reason == "TRIAGE_COMPLETE"
    assert prompts == ["Approve this action? (y/n) "]
    assert len(client.calls) == 6
    first = client.calls[0]
    assert first["model"] == MODEL == "grok-build-0.1"
    names = [spec["function"]["name"] for spec in first["tools"]]
    assert names == list(TOOLS)
    tool_messages = [message for message in client.calls[1]["messages"] if message["role"] == "tool"]
    assert tool_messages
    assert tool_messages[0]["tool_call_id"] == "call-1"
    assert "made-up" not in result.state.customer_draft
    assert "log-1" in result.state.customer_draft
    line = sandbox["action_log"].read_text(encoding="utf-8")
    assert "simulated" in line
    assert "approved" not in line


def test_real_flag_without_a_key_is_missing_key(sandbox, monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    with pytest.raises(AgentError) as caught:
        run_escalation(
            "ESC-1001",
            use_real=True,
            memory_dir=sandbox["memory_dir"],
            action_log=sandbox["action_log"],
        )
    assert caught.value.name == "MISSING_KEY"
    assert "XAI_API_KEY" in str(caught.value)
    assert not sandbox["action_log"].exists()


def test_a_dummy_key_is_not_copied_into_the_run(sandbox, monkeypatch, capsys):
    dummy = "practice-key-not-real"
    monkeypatch.setenv("XAI_API_KEY", dummy)
    result = run_escalation(
        "ESC-1001",
        memory_dir=sandbox["memory_dir"],
        action_log=sandbox["action_log"],
        ask=lambda _prompt: "n",
    )
    blob = capsys.readouterr().out + json.dumps(result.state.to_dict())
    assert dummy not in blob
    if sandbox["action_log"].exists():
        assert dummy not in sandbox["action_log"].read_text(encoding="utf-8")
