# MCP server and multi-agent handoff

Both pieces are local and offline. They do not call Grok, OpenAI, Gemini, or Ollama. Grok remains the default cloud model for `runbook_search.py --model-answer`. These commands do not change that path.

## MCP server

`mcp_server.py` speaks newline-delimited JSON-RPC 2.0 on stdin and stdout (MCP stdio). It uses the Python standard library. No extra package and no API key.

```sh
python mcp_server.py
```

Registered tools, all read-only:

| Tool | What it returns |
| --- | --- |
| `search_runbooks` | Up to three scored passages from `runbook_search.search`, with citations |
| `cited_runbook_answer` | A supported check or approval line from `runbook_search.answer`, or an empty list |
| `read_practice_logs` | Synthetic log rows for one practice escalation id |
| `list_practice_escalations` | Practice ids, services, and ticket text |

`propose_action` and `record_simulated_action` are not MCP tools. A client cannot approve or log an action through this server.

A client sends one JSON object per line. Example:

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"demo","version":"0"}}}
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"cited_runbook_answer","arguments":{"question":"What approval form must I file before I restart Redis?"}}}
```

`initialize` answers with protocol `2024-11-05` and server name `escalation-triage-runbooks`. `notifications/initialized` has no response line.

## Multi-agent handoff

`handoff.py` is a two-role demo, not a new agent framework.

- The triage coordinator owns the request and the stop reason.
- A question is delegated to the runbook specialist. The specialist may call only `search_runbooks` and `cited_runbook_answer` through `invoke_tool`.
- The specialist returns the citations to the coordinator and stops. It never proposes or logs an action.
- A proposal stays with the coordinator. `propose_action` always returns status `pending`. An `approved` flag on the proposal is ignored.
- The simulated line is appended only when the human answers `y` or `yes`, using the same `human_said_yes` check as `agent.py`. Any other answer writes nothing.
- `--defer-approval` leaves the proposal pending and does not ask.
- The handoff budget is two messages (out and back). A smaller budget stops with `MAX_HANDOFFS` before a write.

Question only:

```sh
python handoff.py "What approval form must I file before I restart Redis?"
```

A question the guides can quote stops as `RUNBOOK_ANSWERED`. A question the citer refuses, such as a password rotation, stops as `NO_RUNBOOK_MATCH`. The Redis restart line still requires human approval and does not name a form.

Proposal only, asking the human:

```sh
python handoff.py --propose rollback --target checkout-api --reason "practice bad deploy" --escalation INC-CLOUDFLARE-01 --action-log /tmp/practice-action.log
```

Question and proposal together: the coordinator asks the specialist first, then still waits for a human yes before the simulated log line.

```sh
python handoff.py --defer-approval --propose restart --target checkout-api --reason "practice only" "Which checks should I review for a slow dashboard?"
```

Stop reasons printed as `Stop reason: NAME`: `RUNBOOK_ANSWERED`, `NO_RUNBOOK_MATCH`, `APPROVAL_REQUIRED`, `TRIAGE_COMPLETE`, `ACTION_DENIED`, `MAX_HANDOFFS`, `NEEDS_CLARIFICATION`.

Nothing in this demo restarts a process, rolls back a deploy, pages anyone, or sends the customer draft. Practice escalation text stays the synthetic fixtures already in the repository.
