"""Escalation triage loop.

One practice escalation is walked one step at a time. Each step, a model
picks a tool. The tool result is written onto a state object, and that
object is saved to a JSON file. The next step, and the next run, read that
file. The model is not the memory.

propose_action never runs the action. It stores a pending approval. The
human is asked `Approve this action? (y/n)`. Only the answer y or yes
becomes the boolean True. The simulated action is appended to a local log
only when that boolean is True. A model that says "approved" is ignored.

The practice model is the default. It needs no API key and no network.
`--real` uses grok-build-0.1 and reads XAI_API_KEY from the environment.
The key is never printed and never written into the state file.

Stop reasons (printed as "Stop reason: NAME", also on the result):
  TRIAGE_COMPLETE        - the human said yes; one simulated line was logged
  ACTION_DENIED          - the human did not say yes; nothing was simulated
  APPROVAL_REQUIRED      - a proposal is pending and this run did not ask
  MAX_STEPS_REACHED      - the step budget was used before the case was settled
  ALREADY_RESOLVED       - memory says this case is settled; nothing new ran
  NO_RUNBOOK_MATCH       - no local runbook matched; no action was proposed
  INSUFFICIENT_EVIDENCE  - no hypothesis is linked to an evidence id
  UNKNOWN_TOOL           - the model asked for a tool that does not exist

Named failures (these raise AgentError instead of stopping quietly):
  MISSING_KEY               - --real was used and XAI_API_KEY is not set
  BAD_KEY                   - xAI rejected the key
  MODEL_ERROR               - the model call failed for another reason
  BAD_TOOL_ARGS             - a tool was called with unusable arguments
  UNKNOWN_ESCALATION        - the id is not in the practice catalog
  UNKNOWN_ACTION            - the proposed kind is not restart, rollback, or page_oncall
  NOT_IMPLEMENTED_APPROVAL  - something tried to record an action without boolean True
  EVIDENCE_INVALID          - an evidence row was incomplete or repeated an id
  BAD_ESCALATION_ID         - the id is not safe to use as a file name
  EMPTY_ESCALATION          - the ticket text is empty
  BAD_SETTINGS              - max_steps is below 1
  MEMORY_MISMATCH           - the JSON file is for a different escalation, or not JSON
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from errors import AgentError
from practice_model import PracticeModel
from sample_data import SAMPLE_ID, get_escalation, list_escalations
from state import EscalationState, add_evidence, load_state, memory_path, save_state
from tools import (
    TOOL_SPECS,
    TOOLS,
    call_tool,
    evidence_is_linked,
    record_simulated_action,
)
from turns import ModelTurn

# The optional real model. The practice path does not call this.
MODEL = "grok-build-0.1"
XAI_BASE_URL = "https://api.x.ai/v1"

# The checklist is six tool calls. Eight leaves a little room, then stops
# a model that would keep searching. Tests can pass a smaller max_steps.
MAX_STEPS = 8

ROOT = Path(__file__).resolve().parent
DEFAULT_MEMORY_DIR = ROOT / "memory"
DEFAULT_ACTION_LOG = ROOT / "action.log"

APPROVAL_PROMPT = "Approve this action? (y/n) "

# Why the loop stopped. Always printed, and always stored on the result.
TRIAGE_COMPLETE = "TRIAGE_COMPLETE"
ACTION_DENIED = "ACTION_DENIED"
APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
MAX_STEPS_REACHED = "MAX_STEPS_REACHED"
ALREADY_RESOLVED = "ALREADY_RESOLVED"
NO_RUNBOOK_MATCH = "NO_RUNBOOK_MATCH"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
UNKNOWN_TOOL = "UNKNOWN_TOOL"

STOP_REASONS = (
    TRIAGE_COMPLETE,
    ACTION_DENIED,
    APPROVAL_REQUIRED,
    MAX_STEPS_REACHED,
    ALREADY_RESOLVED,
    NO_RUNBOOK_MATCH,
    INSUFFICIENT_EVIDENCE,
    UNKNOWN_TOOL,
)

# These decisions stick. A second run repeats them and does not call a tool.
# MAX_STEPS_REACHED is not sticky: a later run can continue until the budget
# saved in the file is used up. APPROVAL_REQUIRED is not sticky either: the
# next run asks the human.
STICKY_STOPS = frozenset({NO_RUNBOOK_MATCH, INSUFFICIENT_EVIDENCE, UNKNOWN_TOOL})

STOP_REASON_PLAIN = {
    TRIAGE_COMPLETE: (
        "The human said yes. The simulated action was appended to the local log. "
        "The customer draft was not sent."
    ),
    ACTION_DENIED: (
        "The human did not say yes. Nothing was simulated and the local action log was not written."
    ),
    APPROVAL_REQUIRED: (
        "A proposal is waiting. Nothing has been simulated. A later run can ask the human."
    ),
    MAX_STEPS_REACHED: (
        "The step limit was reached before the escalation was settled. No action was simulated."
    ),
    ALREADY_RESOLVED: (
        "Memory says this escalation is already settled. No tool ran and no second action was recorded."
    ),
    NO_RUNBOOK_MATCH: (
        "No local runbook matched. The agent will not invent a fix or propose an action."
    ),
    INSUFFICIENT_EVIDENCE: (
        "No hypothesis is linked to an evidence id. No action was proposed."
    ),
    UNKNOWN_TOOL: "The model asked for a tool that does not exist. Nothing ran.",
}

SYSTEM_PROMPT = (
    "You triage one fake support escalation. Work one tool at a time. "
    "Search the runbooks, read the logs, check recent deploys, rank hypotheses, "
    "draft a customer update, then propose one action. "
    "Use only evidence ids the tools returned. Do not invent ids. "
    "Do not say a root cause is confirmed. "
    "draft_customer_update only writes a draft. Do not say it was sent. "
    "propose_action does not run anything. You cannot approve it. "
    "Do not send an approved flag. If you claim the action is approved, that claim is ignored. "
    "The human is the only approval."
)


# Set when run_escalation finishes normally. Cleared at the start, so a
# raised AgentError does not leave the previous run's result here.
last_result = None


@dataclass
class RunResult:
    """What one run ended with. `state` is the same object that was saved."""

    stop_reason: str
    state: EscalationState
    summary: str


def human_said_yes(answer):
    """True only when the human typed y or yes.

    "approved", "true", "yep", and an empty answer are all no.
    A value that is not even a string is no.
    """
    if not isinstance(answer, str):
        return False
    return answer.strip().lower() in {"y", "yes"}


def make_client():
    """Build the xAI client. The key stays in the client. It is not returned or printed."""
    key = os.environ.get("XAI_API_KEY", "").strip()
    if not key:
        raise AgentError(
            "MISSING_KEY",
            "XAI_API_KEY is not set in this terminal. The practice model needs no key.",
        )
    from openai import OpenAI  # imported here so the practice path does not need the package

    return OpenAI(api_key=key, base_url=XAI_BASE_URL, timeout=60, max_retries=0)


def ask_model(client, messages, tools):
    """One model call. Failures become named errors. The exception text is not kept.

    Some client errors quote the request. The request can contain the key,
    so the message we raise names the exception type only.
    """
    try:
        completion = client.chat.completions.create(model=MODEL, messages=messages, tools=tools)
        return completion.choices[0].message
    except Exception as exc:
        if type(exc).__name__ == "AuthenticationError":
            raise AgentError("BAD_KEY", "xAI rejected the key. Check XAI_API_KEY in this terminal.")
        raise AgentError("MODEL_ERROR", f"the model call failed ({type(exc).__name__}).")


def _opening_message(state):
    """Show the real model the saved state. The state has no secrets in it."""
    return (
        "Triage this one practice escalation. Use the state below. "
        "Do not repeat a check that is already true. Do not invent evidence ids.\n\n"
        + json.dumps(state.to_dict(), indent=2)
    )


def _assistant_dict(message):
    """Turn a client message into the dict the next API call expects."""
    content = getattr(message, "content", None)
    calls = getattr(message, "tool_calls", None) or []
    payload = {"role": "assistant", "content": content}
    if calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
            }
            for call in calls
        ]
    return payload


def _turn_from_message(message):
    """Read the first tool call, or treat the reply as text the loop will not trust."""
    calls = getattr(message, "tool_calls", None) or []
    thought = (getattr(message, "content", None) or "").strip()
    if not calls:
        return ModelTurn(kind="text", text=thought, thought=thought)
    call = calls[0]
    raw = call.function.arguments or "{}"
    try:
        arguments = json.loads(raw)
    except json.JSONDecodeError:
        raise AgentError("BAD_TOOL_ARGS", "the model tool arguments were not valid JSON.")
    if not isinstance(arguments, dict):
        raise AgentError("BAD_TOOL_ARGS", "the model tool arguments were not a JSON object.")
    return ModelTurn(
        kind="tool",
        name=call.function.name,
        arguments=arguments,
        thought=thought,
        text=thought,
        call_id=getattr(call, "id", "") or "",
    )


class RealModel:
    """grok-build-0.1. The JSON state is still the memory. This chat is not saved.

    A resumed run starts a new chat and shows the model the saved state.
    Tests pass a fake client, so this class can be exercised with no network.
    """

    def __init__(self, client):
        self.client = client
        self.messages = None
        self.pending_call_id = None
        self.last_was_text = False
        self.calls = 0

    def next_turn(self, state, last_result=None):
        self.calls += 1
        if self.messages is None:
            self.messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _opening_message(state)},
            ]
        elif last_result is not None and self.pending_call_id:
            self.messages.append({
                "role": "tool",
                "tool_call_id": self.pending_call_id,
                "content": last_result,
            })
            self.pending_call_id = None
        elif self.last_was_text:
            self.messages.append({
                "role": "user",
                "content": (
                    "That text was not an approval and it did not settle the escalation. "
                    "Call a tool. The step limit will stop you if you do not."
                ),
            })
        message = ask_model(self.client, self.messages, TOOL_SPECS)
        self.messages.append(_assistant_dict(message))
        turn = _turn_from_message(message)
        self.last_was_text = turn.kind == "text"
        if turn.kind == "tool":
            self.pending_call_id = turn.call_id
        return turn


def _check_max_steps(max_steps):
    # bool is a subclass of int. True would otherwise sneak through as 1.
    if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 1:
        raise AgentError("BAD_SETTINGS", "max_steps must be an integer of at least 1.")


def _brief(text, limit=90):
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _describe_call(turn):
    args = turn.arguments or {}
    if turn.name == "search_runbooks":
        return f"search_runbooks query={_brief(args.get('query', ''))!r}"
    if turn.name == "read_logs":
        return f"read_logs escalation_id={args.get('escalation_id')!r}"
    if turn.name == "check_recent_deploys":
        return f"check_recent_deploys service={args.get('service')!r}"
    if turn.name == "rank_hypotheses":
        rows = args.get("evidence") or []
        count = len(rows) if isinstance(rows, list) else "?"
        return f"rank_hypotheses evidence={count} row(s)"
    if turn.name == "draft_customer_update":
        return f"draft_customer_update hypothesis={args.get('hypothesis_title')!r}"
    if turn.name == "propose_action":
        return f"propose_action kind={args.get('kind')} target={args.get('target')}"
    return turn.name or "unknown"


def _print_banner(state):
    print("Data: synthetic practice fixture; not a real incident.")
    print(f"Escalation {state.escalation_id}")
    print(f"Tier: {state.customer_tier}")
    print(f"Service: {state.service}")
    print(f"Ticket: {state.ticket}")
    print()


def _print_step(state, max_steps, turn):
    print(f"Step {state.steps_used} of {max_steps}")
    if turn.thought:
        print(f"Thinking: {turn.thought}")
    if turn.kind == "text":
        print("The model did not call a tool.")
    else:
        print(f"Tool: {_describe_call(turn)}")


def _display_path(path):
    """Show a path relative to the current directory when that stays readable."""
    path = Path(path)
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def _print_tool_result(name, result):
    if name == "search_runbooks":
        if not result:
            print("No runbook section matched.")
            return
        for index, hit in enumerate(result, 1):
            print(f"{index}. [{hit['score']:.3f}] {hit['section']} ({hit['source']})")
            for line in hit["text"].splitlines() or [""]:
                print(f"   {line}")
        return
    if name == "read_logs":
        for row in result["evidence"]:
            print(f"- {row['id']} ({row['source']}): {row['observation']}")
        return
    if name == "check_recent_deploys":
        if not result["deploys"]:
            print("No practice deploys for this service.")
            return
        for deploy in result["deploys"]:
            print(
                f"- {deploy['id']} {deploy['service']} {deploy['version']} "
                f"status={deploy['status']} at {deploy['at']}"
            )
        return
    if name == "rank_hypotheses":
        for hypothesis in result["hypotheses"]:
            ids = ", ".join(hypothesis["supporting_evidence_ids"]) or "none"
            print(f"- {hypothesis['title']}: evidence {ids} ({hypothesis['status']})")
        print("Confirmed root cause: none")
        return
    if name == "draft_customer_update":
        print(result["text"])


def _announce(result, earlier=None, resumed_decision=False):
    print(f"Stop reason: {result.stop_reason}")
    print(result.summary)
    if earlier:
        print(f"Earlier stop reason saved in memory: {earlier}")
    if resumed_decision:
        print("Loaded the earlier decision from memory. No new tool was called.")


def finish_run(state, reason, memory_dir):
    """Save the stop reason and print it. Settled is only for a human answer."""
    state.stop_reason = reason
    if reason in (TRIAGE_COMPLETE, ACTION_DENIED):
        state.settled = True
    save_state(state, memory_dir)
    result = RunResult(reason, state, STOP_REASON_PLAIN[reason])
    _announce(result)
    return result


def _apply_tool_result(state, name, result):
    """Copy a read-only tool result onto the state. This does not approve anything."""
    if name == "search_runbooks":
        state.checked["runbooks"] = True
        state.runbook_hits = result
        state.step_log.append(f"search_runbooks: {len(result)} hit(s)")
    elif name == "read_logs":
        state.checked["logs"] = True
        add_evidence(state, result["evidence"])
        state.step_log.append(f"read_logs: {len(result['evidence'])} evidence row(s)")
    elif name == "check_recent_deploys":
        state.checked["deploys"] = True
        state.deploys = result["deploys"]
        add_evidence(state, result["evidence"])
        state.step_log.append(f"check_recent_deploys: {len(result['deploys'])} deploy(s)")
    elif name == "rank_hypotheses":
        state.hypotheses = result["hypotheses"]
        state.confirmed_root_cause = result["confirmed_root_cause"]
        top = result["hypotheses"][0]
        ids = ",".join(top["supporting_evidence_ids"]) or "none"
        state.step_log.append(f"rank_hypotheses: {top['title']} [{ids}]")
    elif name == "draft_customer_update":
        state.customer_draft = result["text"]
        state.step_log.append("draft_customer_update: draft stored, not sent")
    else:
        raise AgentError("UNKNOWN_TOOL", f"{name} is not a read-only tool the loop can apply.")


def _ensure_draft(state):
    """Fill the customer draft from the leading hypothesis if the model skipped it.

    This is still local text. It is not a model step, and it is not sent.
    """
    if state.customer_draft:
        return
    top = state.hypotheses[0]
    result = call_tool(
        "draft_customer_update",
        {
            "escalation_id": state.escalation_id,
            "customer_tier": state.customer_tier,
            "service": state.service,
            "symptom": state.ticket,
            "hypothesis_title": top["title"],
            "evidence_ids": list(top["supporting_evidence_ids"]),
        },
    )
    state.customer_draft = result["text"]
    state.step_log.append("draft_customer_update: draft stored, not sent")
    print("The loop wrote a customer draft before asking. It was not sent.")
    print(result["text"])
    print()


def approval_gate(state, ask, action_log):
    """Show the proposal and ask the human. Return True only for y or yes.

    Nothing in the state, the draft, or the model's last sentence is read
    as a yes. The only input that matters is the answer to this prompt.
    """
    proposal = state.pending_approval
    top = state.hypotheses[0] if state.hypotheses else None
    print()
    print("--- Proposed action needs your approval ---")
    print("Nothing has run yet.")
    print(f"kind: {proposal['kind']}")
    print(f"target: {proposal['target']}")
    print(f"reason: {proposal['reason']}")
    print(f"details: {proposal['details']}")
    if top is not None:
        ids = ", ".join(top["supporting_evidence_ids"]) or "none"
        print(f"Leading hypothesis: {top['title']} (not confirmed)")
        print(f"Evidence ids: {ids}")
    print("Customer draft (not sent):")
    print(state.customer_draft or "(no draft)")
    print(f"A yes appends one simulated line to {_display_path(action_log)}.")
    print("A yes does not restart, roll back, page anyone, or send the draft.")
    try:
        answer = ask(APPROVAL_PROMPT)
    except EOFError:
        # A closed pipe is not a yes.
        answer = ""
    return human_said_yes(answer)


def settle_proposal(state, said_yes, action_log, memory_dir):
    """Record the simulation only when said_yes is the boolean True.

    Passing the string "yes" or "approved" does not record a line, because
    those values are not True. The gate is what turns a human answer into
    a boolean before it calls this function.
    """
    proposal = state.pending_approval
    if not isinstance(proposal, dict):
        raise AgentError("BAD_SETTINGS", "there is no pending proposal to settle.")
    if said_yes is not True:
        state.settlements.append({
            "decision": "denied",
            "kind": proposal["kind"],
            "target": proposal["target"],
            "simulated": False,
        })
        state.step_log.append(f"human denied {proposal['kind']} {proposal['target']}")
        state.pending_approval = None
        print("Action denied. Nothing was simulated.")
        return finish_run(state, ACTION_DENIED, memory_dir)
    line = record_simulated_action(
        proposal,
        state.escalation_id,
        action_log,
        approved=True,
    )
    state.settlements.append({
        "decision": "approved",
        "kind": proposal["kind"],
        "target": proposal["target"],
        "simulated": True,
        "log_line": line,
    })
    state.step_log.append(f"human approved; simulated {proposal['kind']} {proposal['target']}")
    state.pending_approval = None
    print("Action approved. The simulation was appended to the local log.")
    print(f"Log: {line}")
    return finish_run(state, TRIAGE_COMPLETE, memory_dir)


def _ask_and_settle(state, ask, action_log, memory_dir):
    said_yes = approval_gate(state, ask, action_log)
    return settle_proposal(state, said_yes, action_log, memory_dir)


def _handle_proposal(state, arguments, ask, action_log, memory_dir, defer_approval):
    """Store a pending proposal, or refuse it when no evidence id is linked.

    The approved flag is removed here, before the tool runs. The tool removes
    it again. Neither place treats it as permission.
    """
    arguments = dict(arguments or {})
    claimed = arguments.pop("approved", None)
    if claimed is not None:
        print("Note: the model sent an approved flag. That flag is ignored.")
    if not evidence_is_linked(state.hypotheses):
        state.step_log.append("propose_action refused: no evidence-linked hypothesis")
        print("No evidence-linked hypothesis, so the proposal was not stored.")
        return finish_run(state, INSUFFICIENT_EVIDENCE, memory_dir)
    _ensure_draft(state)
    try:
        proposal = call_tool("propose_action", arguments)
    except AgentError as err:
        state.step_log.append(f"propose_action failed: {err.name}")
        save_state(state, memory_dir)
        raise
    if proposal.get("status") != "pending" or "approved" in proposal:
        raise AgentError(
            "NOT_IMPLEMENTED_APPROVAL",
            "propose_action tried to mark itself approved.",
        )
    state.pending_approval = proposal
    state.step_log.append(f"propose_action: pending {proposal['kind']} {proposal['target']}")
    save_state(state, memory_dir)
    print(f"Pending {proposal['kind']} on {proposal['target']}. Nothing has run.")
    if defer_approval:
        return finish_run(state, APPROVAL_REQUIRED, memory_dir)
    return _ask_and_settle(state, ask, action_log, memory_dir)


def _return(result):
    global last_result
    last_result = result
    return result


def run_escalation(
    escalation_id,
    model=None,
    ask=input,
    memory_dir=DEFAULT_MEMORY_DIR,
    action_log=DEFAULT_ACTION_LOG,
    defer_approval=False,
    max_steps=None,
    use_real=False,
    client=None,
):
    """Run one escalation until a stop reason.

    Pass `model` in tests. With no model, the practice model is used.
    `use_real=True` builds a RealModel. It reads XAI_API_KEY unless `client`
    is passed. `ask` is the prompt function. Tests pass a fake. The terminal
    uses input.
    """
    global last_result
    last_result = None
    if max_steps is None:
        max_steps = MAX_STEPS
    _check_max_steps(max_steps)
    memory_dir = Path(memory_dir)
    action_log = Path(action_log)

    sample = get_escalation(escalation_id)
    if model is None and use_real:
        model = RealModel(client or make_client())
    elif model is None:
        model = PracticeModel()

    loaded = load_state(escalation_id, memory_dir)
    if loaded is None:
        state = EscalationState.from_sample(sample)
        print("No memory file yet. Starting from the ticket.")
    else:
        state = loaded
        print(f"Loaded memory for {state.escalation_id}. Steps already used: {state.steps_used}.")
    _print_banner(state)

    if state.settled:
        result = RunResult(ALREADY_RESOLVED, state, STOP_REASON_PLAIN[ALREADY_RESOLVED])
        _announce(result, earlier=state.stop_reason)
        return _return(result)

    if state.stop_reason in STICKY_STOPS:
        result = RunResult(state.stop_reason, state, STOP_REASON_PLAIN[state.stop_reason])
        _announce(result, resumed_decision=True)
        return _return(result)

    if state.pending_approval:
        print("A proposal is already waiting. No new tool was called.")
        if defer_approval:
            return _return(finish_run(state, APPROVAL_REQUIRED, memory_dir))
        return _return(_ask_and_settle(state, ask, action_log, memory_dir))

    last_tool_result = None
    while True:
        if state.steps_used >= max_steps:
            return _return(finish_run(state, MAX_STEPS_REACHED, memory_dir))
        turn = model.next_turn(state, last_tool_result)
        state.steps_used += 1
        _print_step(state, max_steps, turn)
        if turn.kind == "text":
            snippet = _brief(turn.text or "", 160)
            state.step_log.append(f"model text ignored: {snippet or '(empty)'}")
            save_state(state, memory_dir)
            print(f"The model wrote text. It is not an approval: {snippet or '(empty)'}")
            print()
            last_tool_result = json.dumps({"ignored_text": True})
            continue
        if turn.kind != "tool":
            raise AgentError("MODEL_ERROR", "the model returned a turn the loop does not understand.")
        if not isinstance(turn.arguments, dict):
            raise AgentError("BAD_TOOL_ARGS", f"{turn.name} arguments were not an object.")
        if turn.name not in TOOLS:
            state.step_log.append(f"unknown tool: {turn.name}")
            return _return(finish_run(state, UNKNOWN_TOOL, memory_dir))
        if turn.name == "propose_action":
            return _return(
                _handle_proposal(
                    state,
                    turn.arguments,
                    ask,
                    action_log,
                    memory_dir,
                    defer_approval,
                )
            )
        try:
            tool_result = call_tool(turn.name, turn.arguments)
        except AgentError as err:
            state.step_log.append(f"{turn.name} failed: {err.name}")
            save_state(state, memory_dir)
            raise
        _apply_tool_result(state, turn.name, tool_result)
        _print_tool_result(turn.name, tool_result)
        print()
        save_state(state, memory_dir)
        if turn.name == "search_runbooks" and not tool_result:
            return _return(finish_run(state, NO_RUNBOOK_MATCH, memory_dir))
        if turn.name == "rank_hypotheses" and not evidence_is_linked(tool_result["hypotheses"]):
            return _return(finish_run(state, INSUFFICIENT_EVIDENCE, memory_dir))
        last_tool_result = json.dumps(tool_result)


def main(argv=None, ask=input):
    """Command-line entry. Returns a process exit code."""
    parser = argparse.ArgumentParser(
        description="Triage one fake support escalation. Every proposed action waits for a human.",
    )
    parser.add_argument(
        "escalation_id",
        nargs="?",
        help="Practice id, such as ESC-1001. Omit this to run the sample.",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help=f"Run {SAMPLE_ID}, the checkout 500s sample.",
    )
    parser.add_argument("--workflow-run", metavar="URL", help="Read one public GitHub Actions run and its jobs. No keys or actions.")
    parser.add_argument("--problem", help="Describe a problem locally to compare with current GitHub component status.")
    parser.add_argument("--component", choices=("actions", "git", "api", "pages", "packages", "codespaces", "copilot", "issues", "pull-requests", "webhooks"), help="Explicit GitHub service for --problem.")
    parser.add_argument("--github-status", action="store_true", help="Read GitHub public status alongside two labeled simulated checks. No model or actions.")
    parser.add_argument("--collect-sample", choices=("complete", "partial", "failed"), help="Collect three simulated sources concurrently, then investigate without actions.")
    parser.add_argument("--investigate", metavar="JSON_FILE", help="Read evidence and suggest checks; no model, memory or action approval.")
    parser.add_argument("--list", action="store_true", help="Print the practice escalations and exit.")
    parser.add_argument(
        "--real",
        action="store_true",
        help="Use grok-build-0.1. Reads XAI_API_KEY from the environment and does not print it.",
    )
    parser.add_argument(
        "--defer-approval",
        action="store_true",
        help="Save the pending proposal and stop, instead of asking in this run.",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Delete saved memory for this escalation before starting.",
    )
    parser.add_argument("--memory-dir", default=str(DEFAULT_MEMORY_DIR))
    parser.add_argument("--action-log", default=str(DEFAULT_ACTION_LOG))
    parser.add_argument("--max-steps", type=int, default=MAX_STEPS)
    args = parser.parse_args(argv)

    if args.workflow_run:
        if args.github_status or args.problem is not None or args.component or args.collect_sample or args.investigate or args.real or args.sample or args.escalation_id or args.list or args.fresh or args.defer_approval:
            parser.error('--workflow-run is a separate read-only mode; do not combine it with workflow options.')
        from workflow_inspection import inspect_public_run, render_run
        try:
            result = inspect_public_run(args.workflow_run)
            print(render_run(result))
        except AgentError as err:
            print(str(err), file=sys.stderr)
            return 1
        return 0 if result['complete'] else 1

    if (args.problem is not None or args.component is not None) and not args.github_status:
        parser.error('--problem and --component require --github-status.')
    if args.problem is not None and not args.problem.strip():
        parser.error('--problem must not be empty.')
    if args.component is not None and args.problem is None:
        parser.error('--component requires --problem.')

    if args.github_status:
        if args.collect_sample or args.investigate or args.real or args.sample or args.escalation_id or args.list or args.fresh or args.defer_approval:
            parser.error('--github-status is a separate read-only mode; do not combine it with workflow options.')
        from github_status import run_github_collection
        from evidence_collection import render_collection
        result = run_github_collection(problem=args.problem, component=args.component) if args.problem is not None else run_github_collection()
        print(render_collection(result))
        return 0 if result['github_status']['state'] == 'reported' else 1

    if args.collect_sample:
        if args.investigate or args.real or args.sample or args.escalation_id or args.list or args.fresh or args.defer_approval:
            parser.error('--collect-sample is a separate simulated read-only mode; do not combine it with workflow options.')
        from evidence_collection import run_simulated_collection, render_collection
        result = run_simulated_collection(args.collect_sample)
        print(render_collection(result))
        return 1 if result['collection']['status'] == 'failed' else 0

    if args.investigate:
        if args.real or args.sample or args.escalation_id or args.list or args.fresh or args.defer_approval:
            parser.error('--investigate is a separate read-only mode; do not combine it with workflow options.')
        from evidence_ranker import investigate_file, render_investigation
        try:
            print(render_investigation(investigate_file(args.investigate)))
        except AgentError as err:
            print(str(err), file=sys.stderr)
            return 1
        return 0

    if args.list:
        for escalation in list_escalations():
            print(
                f"{escalation['id']}  {escalation['customer_tier']:6}  "
                f"{escalation['service']:16}  {escalation['title']}"
            )
        return 0
    if args.sample and args.escalation_id:
        parser.error("Pass an escalation id or --sample, not both.")
    if args.escalation_id is None:
        if not args.sample:
            print(f"No escalation id given. Using the practice sample {SAMPLE_ID}.")
        escalation_id = SAMPLE_ID
    else:
        escalation_id = args.escalation_id

    try:
        _check_max_steps(args.max_steps)
        if args.fresh:
            path = memory_path(args.memory_dir, escalation_id)
            if path.exists():
                path.unlink()
        run_escalation(
            escalation_id,
            ask=ask,
            memory_dir=args.memory_dir,
            action_log=args.action_log,
            defer_approval=args.defer_approval,
            max_steps=args.max_steps,
            use_real=args.real,
        )
    except AgentError as err:
        print(str(err), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
