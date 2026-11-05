"""Read-only MCP server for local runbook lookup and practice triage reads.

Speak newline-delimited JSON-RPC 2.0 on stdin and stdout, which is the MCP
stdio transport. The process exposes search and cited-answer lookup over the
local guides, plus two read-only practice helpers. It does not propose, log,
or send anything. A model flag such as approved is not a tool here.

    python mcp_server.py

Point an MCP client at that command. No API key is read.
"""

import json
import sys

from errors import AgentError
from runbook_search import answer, search
from sample_data import list_escalations
from tools import read_logs

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "escalation-triage-runbooks"
SERVER_VERSION = "0.1.0"

_TOOLS = (
    {
        "name": "search_runbooks",
        "description": (
            "Search the local practice runbooks. Read-only. "
            "Returns up to three scored passages with citations."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The runbook question."},
            },
            "required": ["question"],
            "additionalProperties": False,
        },
    },
    {
        "name": "cited_runbook_answer",
        "description": (
            "Quote a supported check or approval line from the best matching local guide. "
            "Read-only. An empty list means the guides do not support an answer."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The runbook question."},
            },
            "required": ["question"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_practice_logs",
        "description": (
            "Read synthetic log rows for one practice escalation id. "
            "Read-only. These rows are fixtures, not customer data."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "escalation_id": {"type": "string"},
            },
            "required": ["escalation_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_practice_escalations",
        "description": "List synthetic practice escalation ids, services, and symptoms. Read-only.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
)


def tool_names():
    return tuple(tool["name"] for tool in _TOOLS)


def _require_question(arguments):
    question = arguments.get("question") if isinstance(arguments, dict) else None
    if not isinstance(question, str) or not question.strip():
        raise AgentError("BAD_TOOL_ARGS", "question must be a non-empty string.")
    return question


def invoke_tool(name, arguments=None):
    """Run one registered read-only tool and return a JSON-ready value."""
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise AgentError("BAD_TOOL_ARGS", "tool arguments must be an object.")
    if name == "search_runbooks":
        question = _require_question(arguments)
        return [
            {"score": score, "citation": citation, "passage": passage}
            for score, citation, passage in search(question)
        ]
    if name == "cited_runbook_answer":
        question = _require_question(arguments)
        hits = search(question)
        return [{"citation": citation, "line": line} for citation, line in answer(question, hits)]
    if name == "read_practice_logs":
        escalation_id = arguments.get("escalation_id")
        return read_logs(escalation_id)
    if name == "list_practice_escalations":
        return [
            {"id": row["id"], "service": row["service"], "ticket": row["ticket"]}
            for row in list_escalations()
        ]
    known = ", ".join(tool_names())
    raise AgentError("UNKNOWN_TOOL", f"no MCP tool named {name!r}. Known tools: {known}.")


def _text_result(payload, is_error=False):
    return {
        "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
        "isError": is_error,
    }


def handle_message(message):
    """Answer one JSON-RPC message. Notifications return None."""
    if not isinstance(message, dict):
        return _error(None, -32600, "Invalid Request")
    method = message.get("method")
    msg_id = message.get("id", None)
    has_id = "id" in message
    params = message.get("params") or {}
    if not isinstance(params, dict):
        return _error(msg_id, -32602, "Invalid params")

    if method == "initialize":
        return _result(msg_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return _result(msg_id, {})
    if method == "tools/list":
        return _result(msg_id, {"tools": list(_TOOLS)})
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            payload = invoke_tool(name, arguments)
        except AgentError as exc:
            return _result(msg_id, _text_result({"error": exc.name, "message": str(exc)}, is_error=True))
        return _result(msg_id, _text_result(payload))
    if not has_id:
        return None
    return _error(msg_id, -32601, f"Method not found: {method}")


def _result(msg_id, result):
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id, code, message):
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def serve(stdin=None, stdout=None):
    """Read one JSON object per line and write one response per request."""
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    for line in stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response = _error(None, -32700, "Parse error")
        else:
            response = handle_message(message)
        if response is None:
            continue
        stdout.write(json.dumps(response) + "\n")
        stdout.flush()


if __name__ == "__main__":
    serve()
