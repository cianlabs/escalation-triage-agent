"""The tools the escalation agent can call.

Five of them only read the fake catalog or the local runbook files.
`propose_action` does not read a live system either. It returns a pending
proposal and writes nothing. The model cannot call `record_simulated_action`.
That function is not in TOOLS. The approval gate in agent.py is the only
caller, and only after a human says yes.

Nothing in this file sends a message, restarts a process, or pages a person.
"""

import re
from datetime import datetime, timezone
from pathlib import Path

from errors import AgentError
from sample_data import get_escalation, list_escalations


# Runbooks live next to this file. Search never leaves this folder.
RUNBOOK_DIR = Path(__file__).resolve().parent / "runbooks"

# Words that show up in almost any sentence. They must not make a runbook
# look relevant. "not" and "will" are here so "will not brew" does not match
# a runbook that merely says "will" or "not".
STOPWORDS = frozenset({
    "the", "and", "for", "are", "was", "you", "our", "how", "what", "not",
    "can", "has", "have", "but", "its", "from", "with", "that", "this", "they",
    "will", "would", "into", "after", "before", "about", "also", "just", "only",
    "please", "when", "says", "looks",
})

# The only write-style actions the agent knows. All three are simulated.
ALLOWED_KINDS = ("restart", "rollback", "page_oncall")

# Keyword ranking, same idea as incident_triage in runbook-copilot.
# A keyword can attach an evidence id to a hypothesis. It does not prove it.
# "error rate" is a phrase. The others are whole words, so "down" does not
# match inside "download".
PATTERNS = (
    {
        "title": "Bad deploy",
        "keywords": ("deploy", "rollback", "500", "error rate"),
        "next_step": "Compare the failed deploy with the previous version, then ask a human before any rollback.",
    },
    {
        "title": "Process needs a restart",
        "keywords": ("oom", "memory", "crash", "killed", "restart"),
        "next_step": "Read the crash line, then ask a human before any restart.",
    },
    {
        "title": "Customer-facing outage",
        "keywords": ("outage", "unavailable", "sev-1", "sev1", "down"),
        "next_step": "Confirm who is affected, then ask a human before paging oncall.",
    },
)


def _words(text):
    """Lowercase words and numbers. "sev-1" becomes "sev" and "1"."""
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _distinctive(text):
    """Words worth matching. Short words and stopwords are left out."""
    return {word for word in _words(text) if len(word) >= 3 and word not in STOPWORDS}


def _sections(path):
    """Split a runbook on its `# ` headings. The heading is the section title."""
    raw = path.read_text(encoding="utf-8")
    sections = []
    for part in re.split(r"(?m)^# ", raw):
        part = part.strip()
        if not part:
            continue
        lines = part.splitlines()
        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        sections.append((title, body))
    if not sections:
        sections.append((path.name, raw.strip()))
    return sections


def _keyword_in(observation, keyword):
    """True when this observation mentions the keyword as its own word or phrase."""
    text = observation.lower()
    if keyword == "error rate":
        return "error rate" in text
    if keyword == "sev-1":
        return "sev-1" in text or re.search(r"\bsev1\b", text) is not None
    return re.search(r"\b" + re.escape(keyword) + r"\b", text) is not None


def _require_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise AgentError("BAD_TOOL_ARGS", f"{label} must be a nonempty string.")
    return value.strip()


def search_runbooks(query):
    """Find up to three local runbook sections that share words with the query.

    This is a word overlap, not embeddings. A score of 0.5 means half of the
    query's distinctive words showed up in that section. No overlap means the
    section is not returned. An empty list means nothing matched.
    """
    if not isinstance(query, str):
        raise AgentError("BAD_TOOL_ARGS", "query must be a string.")
    query_words = _distinctive(query)
    if not query_words or not RUNBOOK_DIR.is_dir():
        return []
    hits = []
    for path in sorted(RUNBOOK_DIR.glob("*.txt")):
        for title, body in _sections(path):
            overlap = query_words & _distinctive(f"{title}\n{body}")
            if not overlap:
                continue
            hits.append({
                "source": path.name,
                "section": title,
                "text": body,
                "score": round(len(overlap) / len(query_words), 3),
                "matched_words": sorted(overlap),
            })
    hits.sort(key=lambda hit: (-hit["score"], hit["source"], hit["section"]))
    return hits[:3]


def read_logs(escalation_id):
    """Return the fake log lines for one practice escalation, as evidence rows."""
    escalation_id = _require_text(escalation_id, "escalation_id")
    escalation = get_escalation(escalation_id)
    evidence = [
        {"id": row["id"], "source": row["source"], "observation": row["observation"]}
        for row in escalation["logs"]
    ]
    return {"evidence": evidence}


def check_recent_deploys(service):
    """Return fake deploys for this service, plus one evidence row per deploy.

    The same service name is never shared by two practice escalations, so a
    failed deploy from one ticket cannot leak into another.
    """
    service = _require_text(service, "service")
    deploys = []
    evidence = []
    for escalation in list_escalations():
        for deploy in escalation["deploys"]:
            if deploy["service"] != service:
                continue
            deploys.append(dict(deploy))
            evidence.append({
                "id": deploy["id"],
                "source": f"deploys/{deploy['service']}",
                "observation": deploy["note"],
            })
    return {"service": service, "deploys": deploys, "evidence": evidence}


def rank_hypotheses(evidence):
    """Rank three hypotheses and attach the evidence ids that mention their keywords.

    The ticket text is not evidence. Only the rows passed in are. Every
    hypothesis stays unverified, and confirmed_root_cause stays None.
    This does not propose an action.
    """
    if not isinstance(evidence, list):
        raise AgentError("BAD_TOOL_ARGS", "evidence must be a list.")
    cleaned = []
    seen = set()
    for row in evidence:
        if not isinstance(row, dict) or any(
            not isinstance(row.get(key), str) or not row[key].strip()
            for key in ("id", "source", "observation")
        ):
            raise AgentError(
                "EVIDENCE_INVALID",
                "each evidence row needs a nonempty id, source, and observation.",
            )
        if row["id"] in seen:
            raise AgentError("EVIDENCE_INVALID", f"duplicate evidence id {row['id']!r}.")
        seen.add(row["id"])
        cleaned.append({"id": row["id"], "source": row["source"], "observation": row["observation"]})

    hypotheses = []
    for pattern in PATTERNS:
        matched = [
            row["id"]
            for row in cleaned
            if any(_keyword_in(row["observation"], keyword) for keyword in pattern["keywords"])
        ]
        if matched:
            rationale = "Evidence mentions a related signal. This is not a confirmed cause."
            missing = []
        else:
            rationale = "No supporting evidence in the logs or deploys that were read."
            missing = ["A log line or deploy note that mentions this hypothesis"]
        hypotheses.append({
            "title": pattern["title"],
            "rationale": rationale,
            "supporting_evidence_ids": matched,
            "missing_evidence": missing,
            "next_diagnostic_step": pattern["next_step"],
            "status": "unverified",
        })
    hypotheses.sort(key=lambda item: -len(item["supporting_evidence_ids"]))
    return {
        "hypotheses": hypotheses,
        "confirmed_root_cause": None,
        "action_mode": "simulation_only",
    }


def evidence_is_linked(hypotheses):
    """True when at least one hypothesis carries an evidence id."""
    return any(item.get("supporting_evidence_ids") for item in hypotheses or [])


def _known_evidence_ids(escalation_id):
    escalation = get_escalation(escalation_id)
    return {row["id"] for row in escalation["logs"]} | {row["id"] for row in escalation["deploys"]}


def draft_customer_update(escalation_id, customer_tier, service, symptom, hypothesis_title, evidence_ids):
    """Write a draft and stop. This function does not send the draft.

    Evidence ids the caller invented are dropped. Only ids from this
    escalation's fake logs and deploys are cited.
    """
    escalation_id = _require_text(escalation_id, "escalation_id")
    customer_tier = _require_text(customer_tier, "customer_tier")
    service = _require_text(service, "service")
    symptom = _require_text(symptom, "symptom")
    hypothesis_title = _require_text(hypothesis_title, "hypothesis_title")
    if not isinstance(evidence_ids, list) or any(not isinstance(item, str) for item in evidence_ids):
        raise AgentError("BAD_TOOL_ARGS", "evidence_ids must be a list of strings.")
    known = _known_evidence_ids(escalation_id)
    cited = []
    for evidence_id in evidence_ids:
        if evidence_id in known and evidence_id not in cited:
            cited.append(evidence_id)
    id_text = ", ".join(cited) if cited else "none"
    symptom_text = symptom.strip()
    if symptom_text and not symptom_text.endswith((".", "!", "?")):
        symptom_text += "."
    text = (
        "Draft only. This was not sent.\n"
        f"We are investigating an issue on {service} for the {customer_tier} tier. "
        f"What we were told: {symptom_text} "
        f"The leading hypothesis is {hypothesis_title}, linked to evidence {id_text}. "
        "We have not confirmed a root cause, and we have not taken an action."
    )
    return {"text": text, "sent": False}


def _failed_deploy(service):
    for escalation in list_escalations():
        for deploy in escalation["deploys"]:
            if deploy["service"] == service and deploy["status"] == "failed":
                return deploy
    return None


def _action_details(kind, target):
    """A sentence that says what a yes would simulate. Nothing is done here."""
    if kind == "restart":
        return f"Would restart {target} in the practice environment. No process is signaled."
    if kind == "page_oncall":
        return f"Would page the practice oncall for {target}. Nobody is paged."
    failed = _failed_deploy(target)
    if failed is None:
        return f"Would roll back {target}. No failed deploy is on file. Nothing is changed."
    return (
        f"Would roll {target} back from {failed['version']} to {failed['previous_version']}. "
        "No cluster is changed."
    )


def propose_action(kind, target, reason, approved=None):
    """Create a pending proposal. Do not run it and do not write the action log.

    `approved` is accepted so a model can pass it, and then it is ignored.
    It is not copied onto the result. Status is always "pending".
    """
    if not isinstance(kind, str) or kind not in ALLOWED_KINDS:
        known = ", ".join(ALLOWED_KINDS)
        raise AgentError(
            "UNKNOWN_ACTION",
            f"{kind!r} is not a simulated action. Known actions: {known}.",
        )
    target = _require_text(target, "target")
    reason = _require_text(reason, "reason")
    # `approved` is deliberately unused. A comment here is the lesson:
    # the model does not get to decide that the human said yes.
    del approved
    return {
        "status": "pending",
        "kind": kind,
        "target": target,
        "reason": " ".join(reason.split()),
        "details": _action_details(kind, target),
    }


def record_simulated_action(proposal, escalation_id, log_path, approved):
    """Append one simulated line to the local log.

    `approved` must be the boolean True. The string "yes", the string "true",
    and the string "approved" are not True, so they do not write a line.
    The approval gate is what passes True, after a human answers y or yes.
    """
    if approved is not True:
        raise AgentError(
            "NOT_IMPLEMENTED_APPROVAL",
            "A simulated action is recorded only when approved is the boolean True.",
        )
    if not isinstance(proposal, dict) or proposal.get("status") != "pending":
        raise AgentError("BAD_TOOL_ARGS", "record_simulated_action expected a pending proposal.")
    for key in ("kind", "target", "details"):
        if not isinstance(proposal.get(key), str) or not proposal[key].strip():
            raise AgentError("BAD_TOOL_ARGS", f"the pending proposal is missing {key}.")
    escalation_id = _require_text(escalation_id, "escalation_id")
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = (
        f"{stamp} | simulated | {proposal['kind']} | target={proposal['target']} "
        f"| escalation={escalation_id} | {proposal['details']}"
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return line


# What the model is allowed to call. record_simulated_action is not here.
TOOLS = {
    "search_runbooks": search_runbooks,
    "read_logs": read_logs,
    "check_recent_deploys": check_recent_deploys,
    "rank_hypotheses": rank_hypotheses,
    "draft_customer_update": draft_customer_update,
    "propose_action": propose_action,
}


TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "search_runbooks",
            "description": "Search the local practice runbooks. Read-only. Returns up to three sections.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Words from the ticket."}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_logs",
            "description": "Read the fake logs for one practice escalation. Read-only.",
            "parameters": {
                "type": "object",
                "properties": {"escalation_id": {"type": "string"}},
                "required": ["escalation_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_recent_deploys",
            "description": "Read fake deploys for one service. Read-only.",
            "parameters": {
                "type": "object",
                "properties": {"service": {"type": "string"}},
                "required": ["service"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rank_hypotheses",
            "description": (
                "Rank hypotheses from evidence rows already read. "
                "Keep the evidence ids. Do not confirm a root cause. Do not propose an action."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "evidence": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Rows with id, source, and observation. Do not invent ids.",
                    }
                },
                "required": ["evidence"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_customer_update",
            "description": "Write a customer update as draft text. Never send it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "escalation_id": {"type": "string"},
                    "customer_tier": {"type": "string"},
                    "service": {"type": "string"},
                    "symptom": {"type": "string"},
                    "hypothesis_title": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "escalation_id",
                    "customer_tier",
                    "service",
                    "symptom",
                    "hypothesis_title",
                    "evidence_ids",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_action",
            "description": (
                "Propose restart, rollback, or page_oncall. "
                "This does not run the action. A human must approve it. "
                "Do not send an approved flag. If you do, it is ignored."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["restart", "rollback", "page_oncall"]},
                    "target": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["kind", "target", "reason"],
            },
        },
    },
]


def call_tool(name, arguments=None):
    """Call one tool by name.

    An approved key is removed before the call, so it cannot change the result.
    Unknown names raise UNKNOWN_TOOL. The loop turns that into a stop reason
    before it gets here. Direct callers still get the named error.
    """
    if name not in TOOLS:
        known = ", ".join(TOOLS)
        raise AgentError("UNKNOWN_TOOL", f"no tool named {name!r}. Known tools: {known}.")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise AgentError("BAD_TOOL_ARGS", f"{name} arguments were not an object.")
    cleaned = dict(arguments)
    cleaned.pop("approved", None)
    try:
        return TOOLS[name](**cleaned)
    except TypeError:
        raise AgentError("BAD_TOOL_ARGS", f"{name} was called with keys {sorted(cleaned)}.")
    except AgentError:
        raise
