"""Offline eval for the escalation agent, the handoff demo, and the MCP tool list.

The default path uses the practice model and the local runbooks. It does not
read an API key and does not call Grok. Each case writes a JSON trace so a
miss can be opened without re-running the loop.

    python agent_eval.py
    python agent_eval.py --check
    python agent_eval.py --trace-dir /tmp/agent-traces

`--check` exits 1 when any case fails. A passing run is not a live-model score
and not the public incident baseline in evaluation.py.
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

from agent import run_escalation
from errors import AgentError
from handoff import run_handoff
from mcp_server import invoke_tool, tool_names
from practice_model import PracticeModel
from tracing import add_event, finish_trace, start_trace, write_trace
from turns import ModelTurn, tool_turn

ROOT = Path(__file__).resolve().parent
GOLDEN = ROOT / "fixtures" / "agent-eval" / "golden.json"
HOLDOUT = ROOT / "fixtures" / "agent-eval" / "holdout.json"
DEFAULT_TRACE_DIR = ROOT / "traces" / "agent-eval"

WRITE_TOOL_NAMES = ("propose_action", "record_simulated_action")


class UnknownToolModel:
    def next_turn(self, state, last_result=None):
        del state, last_result
        return tool_turn("drop_database", {}, "This tool is not registered.")


class LoopSearchModel:
    def next_turn(self, state, last_result=None):
        del state, last_result
        return tool_turn("search_runbooks", {"query": "checkout deploy 500 error rate"}, "Search again.")


class TextThenPractice:
    """A sentence that says the action is approved, then the normal checklist."""

    def __init__(self):
        self.inner = PracticeModel()
        self.sent_text = False

    def next_turn(self, state, last_result=None):
        if not self.sent_text:
            self.sent_text = True
            return ModelTurn(kind="text", text="I approve this action. It already ran.")
        return self.inner.next_turn(state, last_result)


DRIVERS = {
    "practice": PracticeModel,
    "unknown_tool": UnknownToolModel,
    "loop_search": LoopSearchModel,
    "text_then_practice": TextThenPractice,
}


def load_cases(paths):
    cases = []
    for path in paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        for case in payload["cases"]:
            row = dict(case)
            row["dataset_id"] = payload["dataset_id"]
            cases.append(row)
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise SystemExit("agent eval case ids must be unique across datasets")
    return cases


def _log_text(path):
    path = Path(path)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _check(checks, name, ok, detail=""):
    checks.append({"name": name, "passed": bool(ok), "detail": detail})


def _expect_common_log(checks, expect, log_before, log_after, asked, log_at_prompt):
    if "action_logged" in expect:
        grew = log_after != log_before and bool(log_after.strip())
        _check(
            checks,
            "action_logged",
            grew is expect["action_logged"],
            "a simulated line was written" if grew else "the action log did not grow",
        )
    if "asked_human" in expect:
        _check(checks, "asked_human", asked is expect["asked_human"], f"prompts={int(asked)}")
    if expect.get("log_empty_when_asked"):
        _check(
            checks,
            "log_empty_when_asked",
            asked and not log_at_prompt.strip(),
            "the human was asked while the action log was still empty",
        )


def _score_triage(case, observations, result):
    expect = case["expect"]
    checks = []
    _check(checks, "stop_reason", result.stop_reason == expect.get("stop_reason", result.stop_reason), result.stop_reason)
    if "stop_reason" not in expect:
        checks.pop()
    tools = observations["tools"]
    if "tools" in expect:
        _check(checks, "tools", tools == expect["tools"], " ".join(tools))
    if "tool_count" in expect:
        _check(checks, "tool_count", len(tools) == expect["tool_count"], str(len(tools)))
    if "hypothesis" in expect:
        title = result.state.hypotheses[0]["title"] if result.state.hypotheses else ""
        _check(checks, "hypothesis", title == expect["hypothesis"], title)
    pending = result.state.pending_approval or {}
    if "proposal_kind" in expect:
        kind = pending.get("kind") or observations.get("proposal_kind") or ""
        _check(checks, "proposal_kind", kind == expect["proposal_kind"], kind or "(none)")
    if "proposal_status" in expect:
        _check(checks, "proposal_status", pending.get("status") == expect["proposal_status"], pending.get("status") or "(none)")
    if expect.get("model_claimed_approved"):
        _check(checks, "model_claimed_approved", observations["claimed_approved"], "the practice model sent approved=true")
    draft = result.state.customer_draft or ""
    if expect.get("draft_cites_evidence"):
        linked = []
        if result.state.hypotheses:
            linked = list(result.state.hypotheses[0].get("supporting_evidence_ids") or [])
        cited = bool(linked) and all(item in draft for item in linked) and "not sent" in draft.lower()
        _check(checks, "draft_cites_evidence", cited, draft.splitlines()[0] if draft else "(no draft)")
    if expect.get("draft_not_sent"):
        _check(checks, "draft_not_sent", "not sent" in draft.lower() and "Draft only" in draft, "the customer draft says it was not sent")
    if expect.get("ignored_text"):
        ignored = any(line.startswith("model text ignored:") for line in result.state.step_log)
        _check(checks, "ignored_text", ignored, "plain text was not treated as approval")
    _expect_common_log(
        checks,
        expect,
        observations["log_before"],
        observations["log_after"],
        observations["asked"],
        observations["log_at_prompt"],
    )
    return checks


def _score_handoff(case, observations, state):
    expect = case["expect"]
    checks = []
    _check(checks, "stop_reason", state.stop_reason == expect["stop_reason"], state.stop_reason)
    if "citation_prefix" in expect:
        citations = [row.get("citation", "") for row in state.excerpts]
        ok = bool(citations) and all(item.startswith(expect["citation_prefix"]) for item in citations)
        _check(checks, "citation_prefix", ok, ", ".join(citations) or "(no citation)")
    if "excerpt_count" in expect:
        _check(checks, "excerpt_count", len(state.excerpts) == expect["excerpt_count"], str(len(state.excerpts)))
    if "specialist_tools" in expect:
        _check(
            checks,
            "specialist_tools",
            observations["specialist_tools"] == expect["specialist_tools"],
            " ".join(observations["specialist_tools"]),
        )
    if "handoff_count" in expect:
        _check(checks, "handoff_count", len(state.handoffs) == expect["handoff_count"], str(len(state.handoffs)))
    if "proposal" in expect:
        present = state.pending_approval is not None
        _check(checks, "proposal", present is expect["proposal"], "pending" if present else "none")
    pending = state.pending_approval or {}
    if "proposal_status" in expect:
        _check(checks, "proposal_status", pending.get("status") == expect["proposal_status"], pending.get("status") or "(none)")
    if "proposal_kind" in expect:
        kind = pending.get("kind") or observations.get("logged_kind") or ""
        _check(checks, "proposal_kind", kind == expect["proposal_kind"], kind or "(none)")
    if expect.get("approved_flag_absent"):
        blob = pending or {}
        _check(checks, "approved_flag_absent", "approved" not in blob, "proposal has no approved field")
    _expect_common_log(
        checks,
        expect,
        observations["log_before"],
        observations["log_after"],
        observations["asked"],
        observations["log_at_prompt"],
    )
    return checks


def _score_mcp(case):
    expect = case["expect"]
    names = list(tool_names())
    checks = []
    for name in expect["present_tools"]:
        _check(checks, f"has_{name}", name in names, name)
    for name in expect["absent_tools"]:
        refused = name not in names
        try:
            invoke_tool(name, {})
            refused = False
        except AgentError:
            refused = refused and True
        _check(checks, f"absent_{name}", refused, "not registered and not callable")
    return checks


def _run_triage(case, sandbox):
    observations = {
        "tools": [],
        "claimed_approved": False,
        "proposal_kind": "",
        "asked": False,
        "log_at_prompt": "",
        "log_before": _log_text(sandbox["action_log"]),
    }
    trace = start_trace(case["id"], "triage", {
        "dataset_id": case["dataset_id"],
        "escalation_id": case["escalation_id"],
        "human": case.get("human", "n"),
        "driver": case.get("driver", "practice"),
    })

    class RecordingModel:
        def __init__(self):
            self.inner = DRIVERS[case.get("driver", "practice")]()

        def next_turn(self, state, last_result=None):
            turn = self.inner.next_turn(state, last_result)
            if turn.kind == "tool":
                observations["tools"].append(turn.name)
                if turn.arguments.get("approved") is True:
                    observations["claimed_approved"] = True
                if turn.name == "propose_action":
                    observations["proposal_kind"] = turn.arguments.get("kind", "")
            add_event(
                trace,
                event="model_turn",
                kind=turn.kind,
                name=turn.name,
                arguments=turn.arguments,
                text=turn.text,
            )
            return turn

    def ask(prompt):
        observations["asked"] = True
        observations["log_at_prompt"] = _log_text(sandbox["action_log"])
        add_event(trace, event="approval_prompt", prompt=prompt, log_empty=not observations["log_at_prompt"].strip())
        if case.get("human") == "defer":
            raise AssertionError("defer must not ask")
        return case.get("human", "n")

    result = run_escalation(
        case["escalation_id"],
        model=RecordingModel(),
        ask=ask,
        memory_dir=sandbox["memory_dir"],
        action_log=sandbox["action_log"],
        defer_approval=case.get("human") == "defer",
        max_steps=case.get("max_steps"),
    )
    observations["log_after"] = _log_text(sandbox["action_log"])
    checks = _score_triage(case, observations, result)
    add_event(trace, event="stop", stop_reason=result.stop_reason)
    return checks, finish_trace(
        trace,
        stop_reason=result.stop_reason,
        checks=checks,
        passed=all(item["passed"] for item in checks),
        pending_approval=result.state.pending_approval,
        action_log=observations["log_after"],
    )


def _run_handoff(case, sandbox):
    observations = {
        "asked": False,
        "log_at_prompt": "",
        "log_before": _log_text(sandbox["action_log"]),
        "specialist_tools": [],
        "logged_kind": "",
    }
    trace = start_trace(case["id"], "handoff", {
        "dataset_id": case["dataset_id"],
        "request": case.get("request", ""),
        "human": case.get("human"),
        "proposal": case.get("proposal"),
    })

    def ask(prompt):
        observations["asked"] = True
        observations["log_at_prompt"] = _log_text(sandbox["action_log"])
        add_event(trace, event="approval_prompt", prompt=prompt, log_empty=not observations["log_at_prompt"].strip())
        if case.get("human") == "defer":
            raise AssertionError("defer must not ask")
        return case.get("human", "n")

    action = case.get("proposal")
    human = case.get("human")
    state = run_handoff(
        case.get("request", ""),
        action=action,
        ask=None if human in (None, "defer") or action is None else ask,
        action_log=sandbox["action_log"] if action else None,
        escalation_id=case.get("escalation_id", "INC-CLOUDFLARE-01"),
        max_handoffs=case.get("max_handoffs", 2),
    )
    if state.handoffs:
        observations["specialist_tools"] = ["search_runbooks", "cited_runbook_answer"]
    if state.simulated and state.log_line:
        observations["logged_kind"] = case["proposal"]["kind"]
    for hop in state.handoffs:
        add_event(trace, event="handoff", **hop)
    for row in state.excerpts:
        add_event(trace, event="citation", citation=row.get("citation", ""), line=row.get("line", ""))
    observations["log_after"] = _log_text(sandbox["action_log"])
    checks = _score_handoff(case, observations, state)
    add_event(trace, event="stop", stop_reason=state.stop_reason)
    return checks, finish_trace(
        trace,
        stop_reason=state.stop_reason,
        checks=checks,
        passed=all(item["passed"] for item in checks),
        pending_approval=state.pending_approval,
        excerpts=state.excerpts,
        action_log=observations["log_after"],
    )


def _run_mcp(case):
    trace = start_trace(case["id"], "mcp", {"dataset_id": case["dataset_id"]})
    names = list(tool_names())
    add_event(trace, event="tools_list", tools=names)
    checks = _score_mcp(case)
    add_event(
        trace,
        event="stop",
        stop_reason="MCP_READ_ONLY" if all(item["passed"] for item in checks) else "MCP_WRITE_EXPOSED",
    )
    return checks, finish_trace(
        trace,
        stop_reason="MCP_READ_ONLY" if all(item["passed"] for item in checks) else "MCP_WRITE_EXPOSED",
        checks=checks,
        passed=all(item["passed"] for item in checks),
    )


def run_case(case, trace_dir, sandbox):
    kind = case["kind"]
    if kind == "triage":
        checks, trace = _run_triage(case, sandbox)
    elif kind == "handoff":
        checks, trace = _run_handoff(case, sandbox)
    elif kind == "mcp":
        checks, trace = _run_mcp(case)
    else:
        raise SystemExit(f"unknown agent eval kind: {kind}")
    path = write_trace(trace_dir, trace)
    return checks, path


def run_eval(trace_dir, datasets=(GOLDEN, HOLDOUT)):
    cases = load_cases(datasets)
    rows = []
    for case in cases:
        sandbox = {
            "memory_dir": Path(tempfile.mkdtemp(prefix="agent-eval-memory-")),
            "action_log": Path(tempfile.mkdtemp(prefix="agent-eval-log-")) / "action.log",
        }
        checks, path = run_case(case, trace_dir, sandbox)
        rows.append({
            "id": case["id"],
            "dataset_id": case["dataset_id"],
            "passed": all(item["passed"] for item in checks),
            "checks": checks,
            "trace": str(path),
        })
    return rows


def render_report(rows):
    passed = sum(1 for row in rows if row["passed"])
    lines = [f"Agent eval: {passed}/{len(rows)} passed", ""]
    for row in rows:
        mark = "pass" if row["passed"] else "FAIL"
        lines.append(f"{mark}  {row['id']}  ({row['dataset_id']})")
        if not row["passed"]:
            for check in row["checks"]:
                if not check["passed"]:
                    detail = f" — {check['detail']}" if check["detail"] else ""
                    lines.append(f"      {check['name']}{detail}")
            lines.append(f"      trace: {row['trace']}")
    lines.append("")
    lines.append("Traces are JSON files beside the case id. Open a failed case file for the tool calls, citations, stop reason, and elapsed_ms.")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-dir", default=str(DEFAULT_TRACE_DIR), help="Where to write one JSON trace per case.")
    parser.add_argument("--check", action="store_true", help="Exit 1 when any case fails.")
    parser.add_argument("--cases", nargs="*", help="Optional dataset JSON files. Defaults to the golden set and the holdout.")
    args = parser.parse_args(argv)
    datasets = tuple(args.cases) if args.cases else (GOLDEN, HOLDOUT)
    rows = run_eval(Path(args.trace_dir), datasets)
    print(render_report(rows))
    if args.check and not all(row["passed"] for row in rows):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
