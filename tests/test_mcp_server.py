"""The stdio MCP server registers read-only tools and does not log actions."""

import json

from errors import AgentError
from mcp_server import PROTOCOL_VERSION, SERVER_NAME, handle_message, invoke_tool, serve, tool_names
import pytest


def test_tools_are_registered():
    response = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = [tool["name"] for tool in response["result"]["tools"]]
    assert names == list(tool_names())
    assert "search_runbooks" in names
    assert "cited_runbook_answer" in names
    assert "read_practice_logs" in names
    assert "propose_action" not in names
    assert "record_simulated_action" not in names


def test_initialize_names_the_server():
    response = handle_message({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}},
    })
    assert response["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert response["result"]["serverInfo"]["name"] == SERVER_NAME


def test_initialized_notification_has_no_response():
    assert handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_search_and_cited_answer_are_read_only(tmp_path):
    hits = invoke_tool("search_runbooks", {"question": "Which checks should I review for a slow dashboard?"})
    assert hits
    assert hits[0]["citation"].startswith("runbooks/")
    excerpts = invoke_tool(
        "cited_runbook_answer",
        {"question": "Which checks should I review for a slow dashboard?"},
    )
    assert excerpts
    assert excerpts[0]["citation"].startswith("runbooks/")
    logs = invoke_tool("read_practice_logs", {"escalation_id": "INC-CLOUDFLARE-01"})
    assert logs["evidence"]
    listed = invoke_tool("list_practice_escalations", {})
    assert any(row["id"] == "INC-CLOUDFLARE-01" for row in listed)
    assert list(tmp_path.iterdir()) == []


def test_unknown_tool_is_an_mcp_error_result():
    response = handle_message({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "record_simulated_action", "arguments": {}},
    })
    body = json.loads(response["result"]["content"][0]["text"])
    assert response["result"]["isError"] is True
    assert body["error"] == "UNKNOWN_TOOL"


def test_serve_round_trip():
    incoming = "\n".join([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        "",
    ]) + "\n"

    class Out:
        def __init__(self):
            self.chunks = []

        def write(self, text):
            self.chunks.append(text)

        def flush(self):
            return None

    out = Out()
    serve(stdin=incoming.splitlines(keepends=True), stdout=out)
    lines = [json.loads(chunk) for chunk in out.chunks]
    assert len(lines) == 1
    assert lines[0]["id"] == 1
    assert "search_runbooks" in [tool["name"] for tool in lines[0]["result"]["tools"]]


def test_invoke_rejects_a_blank_question():
    with pytest.raises(AgentError) as caught:
        invoke_tool("search_runbooks", {"question": "  "})
    assert caught.value.name == "BAD_TOOL_ARGS"
