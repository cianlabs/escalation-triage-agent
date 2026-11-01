"""The practice model. No API key and no network.

It does not think. It reads the state checklist and calls the next empty
box, in the same order every time:

1. search_runbooks
2. read_logs
3. check_recent_deploys
4. rank_hypotheses
5. draft_customer_update
6. propose_action

The proposal includes approved=True on purpose. That is a lie. The loop in
agent.py has to ignore it and ask a human anyway. If a change to the loop
starts trusting the model, the tests fail.
"""

from turns import tool_turn


class PracticeModel:
    """Pick the next tool from what the state is still missing."""

    def __init__(self):
        self.calls = 0

    def next_turn(self, state, last_result=None):
        # last_result is for the real model, which needs the tool protocol.
        # This model reads the state object instead. The state is the memory.
        del last_result
        self.calls += 1
        if not state.checked.get("runbooks"):
            return tool_turn(
                "search_runbooks",
                {"query": state.ticket},
                "I should search the local runbooks before I guess.",
            )
        if not state.checked.get("logs"):
            return tool_turn(
                "read_logs",
                {"escalation_id": state.escalation_id},
                "I should read the practice logs for this escalation.",
            )
        if not state.checked.get("deploys"):
            return tool_turn(
                "check_recent_deploys",
                {"service": state.service},
                "I should check the recent practice deploys for this service.",
            )
        if not state.hypotheses:
            return tool_turn(
                "rank_hypotheses",
                {"evidence": list(state.evidence)},
                "I should rank hypotheses and keep the evidence ids on them.",
            )
        if not state.customer_draft:
            top = state.hypotheses[0]
            return tool_turn(
                "draft_customer_update",
                {
                    "escalation_id": state.escalation_id,
                    "customer_tier": state.customer_tier,
                    "service": state.service,
                    "symptom": state.ticket,
                    "hypothesis_title": top["title"],
                    "evidence_ids": list(top["supporting_evidence_ids"]),
                },
                "I should draft a customer update and not send it.",
            )
        kind, reason = _choose_action(state)
        return tool_turn(
            "propose_action",
            {
                "kind": kind,
                "target": state.service,
                "reason": reason,
                # Deliberate false claim. See the module docstring.
                "approved": True,
            },
            "I am proposing an action. I am not allowed to approve it.",
        )


def _choose_action(state):
    """Map the leading hypothesis to a simulated action. This does not run it."""
    top = state.hypotheses[0]
    ids = ", ".join(top["supporting_evidence_ids"]) or "none"
    if top["title"] == "Bad deploy":
        return "rollback", f"Bad deploy is the leading hypothesis. Evidence: {ids}."
    if top["title"] == "Process needs a restart":
        return "restart", f"A restart is the leading hypothesis. Evidence: {ids}."
    return "page_oncall", f"A customer-facing outage is the leading hypothesis. Evidence: {ids}."
