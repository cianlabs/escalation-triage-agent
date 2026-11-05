"""Demo-sized handoff between a triage coordinator and a runbook specialist.

The coordinator owns the request. A runbook question is delegated once to the
specialist, which may call only the read-only MCP tools. A simulated write is
proposed by the coordinator and is recorded only when a human answers y or yes.
The specialist cannot approve, send, or log an action.

Stop reasons:
  RUNBOOK_ANSWERED     the specialist returned at least one cited line
  NO_RUNBOOK_MATCH     the specialist found no supported citation
  APPROVAL_REQUIRED    a proposal is pending and this run did not ask
  TRIAGE_COMPLETE      the human said yes; one simulated line was logged
  ACTION_DENIED        the human did not say yes; nothing was simulated
  MAX_HANDOFFS         another delegation would pass the handoff budget
  NEEDS_CLARIFICATION  the request was neither a question nor a proposal
"""

import argparse
import json
import sys
from dataclasses import dataclass, field

from agent import human_said_yes
from errors import AgentError
from mcp_server import invoke_tool
from sample_data import SAMPLE_ID
from tools import propose_action, record_simulated_action

RUNBOOK_ANSWERED = "RUNBOOK_ANSWERED"
NO_RUNBOOK_MATCH = "NO_RUNBOOK_MATCH"
APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
TRIAGE_COMPLETE = "TRIAGE_COMPLETE"
ACTION_DENIED = "ACTION_DENIED"
MAX_HANDOFFS = "MAX_HANDOFFS"
NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"

MAX_HANDOFF_STEPS = 2
SPECIALIST = "runbook_specialist"
COORDINATOR = "triage_coordinator"


@dataclass
class HandoffState:
    """Plain record of one demo. `approved` from a model is never stored."""

    request: str
    escalation_id: str
    handoffs: list = field(default_factory=list)
    runbook_hits: list = field(default_factory=list)
    excerpts: list = field(default_factory=list)
    pending_approval: dict = None
    stop_reason: str = ""
    simulated: bool = False
    log_line: str = ""

    def as_dict(self):
        return {
            "request": self.request,
            "escalation_id": self.escalation_id,
            "handoffs": list(self.handoffs),
            "runbook_hits": self.runbook_hits,
            "excerpts": self.excerpts,
            "pending_approval": self.pending_approval,
            "stop_reason": self.stop_reason,
            "simulated": self.simulated,
            "log_line": self.log_line,
        }


def _looks_like_question(request):
    text = request.strip().lower()
    if "?" in request:
        return True
    return text.startswith(("what ", "how ", "which ", "where ", "when ", "who ", "why "))


def _delegate(state, max_handoffs):
    """One coordinator step that hands the question to the specialist."""
    if len(state.handoffs) >= max_handoffs:
        state.stop_reason = MAX_HANDOFFS
        return False
    state.handoffs.append({
        "from": COORDINATOR,
        "to": SPECIALIST,
        "reason": "runbook question",
    })
    state.runbook_hits = invoke_tool("search_runbooks", {"question": state.request})
    state.excerpts = invoke_tool("cited_runbook_answer", {"question": state.request})
    state.handoffs.append({
        "from": SPECIALIST,
        "to": COORDINATOR,
        "reason": "cited lookup finished",
        "excerpt_count": len(state.excerpts),
    })
    if len(state.handoffs) > max_handoffs:
        state.stop_reason = MAX_HANDOFFS
        return False
    return True


def _settle(state, proposal, ask, action_log):
    pending = propose_action(
        proposal["kind"],
        proposal["target"],
        proposal["reason"],
        approved=proposal.get("approved"),
    )
    state.pending_approval = pending
    if ask is None:
        state.stop_reason = APPROVAL_REQUIRED
        return state
    answer = ask("Approve this action? (y/n) ")
    if not human_said_yes(answer):
        state.pending_approval = None
        state.simulated = False
        state.stop_reason = ACTION_DENIED
        return state
    state.log_line = record_simulated_action(
        pending,
        state.escalation_id,
        action_log,
        True,
    )
    state.pending_approval = None
    state.simulated = True
    state.stop_reason = TRIAGE_COMPLETE
    return state


def run_handoff(request, *, action=None, ask=None, action_log=None, escalation_id=SAMPLE_ID, max_handoffs=MAX_HANDOFF_STEPS):
    """Run the coordinator. `ask` is called only for a simulated write.

    `action` is an optional dict with kind, target, and reason. A model-supplied
    approved flag on that dict is ignored by propose_action. Pass ask=None to
    leave the proposal pending. The specialist path never calls the action log.
    """
    if not isinstance(request, str):
        raise AgentError("BAD_TOOL_ARGS", "request must be a string.")
    if max_handoffs < 1:
        raise AgentError("BAD_SETTINGS", "max_handoffs must be at least 1.")
    state = HandoffState(request=request.strip(), escalation_id=escalation_id)
    question = _looks_like_question(state.request)
    if question:
        if not _delegate(state, max_handoffs):
            return state
        if action is None:
            state.stop_reason = RUNBOOK_ANSWERED if state.excerpts else NO_RUNBOOK_MATCH
            return state
    if action is not None:
        if action_log is None:
            raise AgentError("BAD_TOOL_ARGS", "action_log is required when proposing an action.")
        return _settle(state, action, ask, action_log)
    if not question:
        state.stop_reason = NEEDS_CLARIFICATION
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", nargs="?", default="", help="A runbook question, if any.")
    parser.add_argument("--propose", choices=("restart", "rollback", "page_oncall"))
    parser.add_argument("--target", help="Practice service or component for --propose.")
    parser.add_argument("--reason", help="Why the simulated action is proposed.")
    parser.add_argument("--escalation", default=SAMPLE_ID)
    parser.add_argument("--defer-approval", action="store_true", help="Save the proposal and do not ask.")
    parser.add_argument("--action-log", default="action.log")
    args = parser.parse_args(argv)
    action = None
    if args.propose or args.target or args.reason:
        if not (args.propose and args.target and args.reason):
            parser.error("--propose, --target, and --reason are used together")
        action = {"kind": args.propose, "target": args.target, "reason": args.reason}
    if not args.request.strip() and action is None:
        parser.error("pass a question, a proposal, or both")
    ask = None if args.defer_approval or action is None else input
    try:
        state = run_handoff(
            args.request,
            action=action,
            ask=ask,
            action_log=args.action_log,
            escalation_id=args.escalation,
        )
    except AgentError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(json.dumps(state.as_dict(), indent=2))
    print(f"Stop reason: {state.stop_reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
