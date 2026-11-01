"""The state object for one escalation, and the JSON file that remembers it.

The model is not the memory. This object is. It records what was checked,
which evidence was found, how the hypotheses ranked, whether a proposal is
waiting, and a short step log. `save_state` writes that object to one JSON
file per escalation. A second run calls `load_state` and continues.

The file is local. It is not a database and it is not shared.
"""

import json
import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from errors import AgentError


# An id becomes a file name. This pattern blocks paths such as "../secrets".
_SAFE_ID = re.compile(r"[A-Za-z0-9_-]+")


@dataclass
class EscalationState:
    """Everything the loop knows about one escalation.

    `checked` is the checklist: runbooks, logs, deploys.
    `evidence` is what the read-only tools found, each row with an id.
    `hypotheses` come from rank_hypotheses. None of them is a confirmed cause.
    `pending_approval` is set by propose_action and cleared when a human answers.
    `settled` is True only after that answer has been recorded.
    `step_log` is the short history a person can read in the JSON file.
    """

    escalation_id: str
    ticket: str
    customer_tier: str
    service: str
    checked: dict = field(default_factory=lambda: {"runbooks": False, "logs": False, "deploys": False})
    evidence: list = field(default_factory=list)
    runbook_hits: list = field(default_factory=list)
    deploys: list = field(default_factory=list)
    hypotheses: list = field(default_factory=list)
    confirmed_root_cause: str | None = None
    customer_draft: str = ""
    pending_approval: dict | None = None
    settlements: list = field(default_factory=list)
    step_log: list = field(default_factory=list)
    steps_used: int = 0
    stop_reason: str = ""
    settled: bool = False

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        """Build a state from JSON. A file that is not this shape is MEMORY_MISMATCH.

        Start from a blank state, then copy the keys that are present. A missing
        key keeps the blank default, so an older file still loads.
        """
        if not isinstance(data, dict):
            raise AgentError("MEMORY_MISMATCH", "the memory file was not a JSON object.")
        escalation_id = data.get("escalation_id")
        if not isinstance(escalation_id, str) or not escalation_id:
            raise AgentError("MEMORY_MISMATCH", "the memory file is missing escalation_id.")
        state = cls(
            escalation_id=escalation_id,
            ticket=data["ticket"] if isinstance(data.get("ticket"), str) else "",
            customer_tier=data["customer_tier"] if isinstance(data.get("customer_tier"), str) else "",
            service=data["service"] if isinstance(data.get("service"), str) else "",
        )
        skip = {"escalation_id", "ticket", "customer_tier", "service"}
        for item in fields(cls):
            if item.name in data and item.name not in skip:
                setattr(state, item.name, data[item.name])
        return state

    @classmethod
    def from_sample(cls, sample):
        """A fresh state for a catalog escalation. Nothing has been checked yet."""
        if not isinstance(sample.get("ticket"), str) or not sample["ticket"].strip():
            raise AgentError("EMPTY_ESCALATION", "the ticket text is empty.")
        return cls(
            escalation_id=sample["id"],
            ticket=sample["ticket"],
            customer_tier=sample["customer_tier"],
            service=sample["service"],
        )


def memory_path(memory_dir, escalation_id):
    """Path to the one JSON file for this escalation. Rejects unsafe ids."""
    if not isinstance(escalation_id, str) or _SAFE_ID.fullmatch(escalation_id) is None:
        raise AgentError(
            "BAD_ESCALATION_ID",
            "the escalation id has characters that are not safe in a file name.",
        )
    return Path(memory_dir) / f"{escalation_id}.json"


def save_state(state, memory_dir):
    """Write the whole state. Pretty-printed so a person can open the file and read it."""
    path = memory_path(memory_dir, state.escalation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def load_state(escalation_id, memory_dir):
    """Load the saved state, or return None when this escalation has no file yet.

    The file has to name the same escalation id. That stops a renamed file
    from being applied to the wrong ticket.
    """
    path = memory_path(memory_dir, escalation_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise AgentError("MEMORY_MISMATCH", f"{path.name} is not valid JSON.")
    state = EscalationState.from_dict(data)
    if state.escalation_id != escalation_id:
        raise AgentError(
            "MEMORY_MISMATCH",
            f"{path.name} is for {state.escalation_id!r}, not {escalation_id!r}.",
        )
    return state


def add_evidence(state, rows):
    """Append evidence rows the state does not already have. Ids are kept unique."""
    seen = {row["id"] for row in state.evidence}
    for row in rows:
        if row["id"] in seen:
            continue
        state.evidence.append(
            {"id": row["id"], "source": row["source"], "observation": row["observation"]}
        )
        seen.add(row["id"])
