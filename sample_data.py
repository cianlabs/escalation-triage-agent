"""Practice escalations. Every row in this file is fake.

There are no real customers, no production logs, and no credentials here.
The tools only read this catalog. They never reach a live system.

Each escalation is one support ticket plus the fake logs and deploys the
agent is allowed to look at. The notes on each id say what a practice run
is expected to do with it.
"""

import copy

from errors import AgentError


# The escalation `python agent.py --sample` runs.
SAMPLE_ID = "ESC-1001"


# ESC-1001 is the sample used by `python agent.py --sample`.
# The logs and the failed deploy support "Bad deploy", so the proposal is a rollback.
# ESC-1002 supports "Process needs a restart".
# ESC-1003 shares no words with the local runbooks, so the run stops early.
# ESC-1004 matches a runbook, but the logs and deploys support no hypothesis.
# ESC-1005 supports "Customer-facing outage", so the proposal is to page oncall.
ESCALATIONS = {
    "ESC-1001": {
        "id": "ESC-1001",
        "title": "Checkout 500s after a deploy",
        "customer_tier": "gold",
        "service": "checkout-api",
        "ticket": (
            "Checkout returns 500 after the 14:05 deploy. "
            "Error rate jumped. Please roll back if the new version is bad."
        ),
        "logs": [
            {
                "id": "log-1",
                "source": "checkout-api.log",
                "observation": "checkout-api error rate jumped to 40 percent after the deploy",
            },
            {
                "id": "log-2",
                "source": "checkout-api.log",
                "observation": "POST /checkout returned 500",
            },
        ],
        "deploys": [
            {
                "id": "deploy-1",
                "service": "checkout-api",
                "version": "2.4.1",
                "previous_version": "2.4.0",
                "status": "failed",
                "at": "2026-04-02T14:05:00Z",
                "note": "error rate jumped right after the deploy of 2.4.1",
            }
        ],
    },
    "ESC-1002": {
        "id": "ESC-1002",
        "title": "Image worker keeps crashing",
        "customer_tier": "silver",
        "service": "image-worker",
        "ticket": (
            "The image worker keeps crashing. Memory looks exhausted. "
            "The runbook says when to restart it."
        ),
        "logs": [
            {
                "id": "log-1",
                "source": "image-worker.log",
                "observation": "image-worker memory exhausted and the oom killer fired",
            },
            {
                "id": "log-2",
                "source": "image-worker.log",
                "observation": "process crash recorded for image-worker",
            },
        ],
        "deploys": [
            {
                "id": "deploy-1",
                "service": "image-worker",
                "version": "3.2.0",
                "previous_version": "3.1.4",
                "status": "succeeded",
                "at": "2026-03-28T09:00:00Z",
                "note": "image-worker release 3.2.0 finished cleanly",
            }
        ],
    },
    "ESC-1003": {
        "id": "ESC-1003",
        "title": "Coffee machine is beeping",
        "customer_tier": "bronze",
        "service": "coffee-machine",
        "ticket": "The office coffee machine is beeping and will not brew.",
        "logs": [
            {
                "id": "log-1",
                "source": "coffee-machine.log",
                "observation": "practice note: reservoir sensor beep, not a production service",
            }
        ],
        "deploys": [
            {
                "id": "deploy-1",
                "service": "coffee-machine",
                "version": "0.0.1",
                "previous_version": "0.0.0",
                "status": "succeeded",
                "at": "2026-01-01T00:00:00Z",
                "note": "practice firmware finished cleanly",
            }
        ],
    },
    "ESC-1004": {
        "id": "ESC-1004",
        "title": "Dashboard feels slow",
        "customer_tier": "silver",
        "service": "dashboard",
        "ticket": "The dashboard feels a bit slow today.",
        "logs": [
            {
                "id": "log-1",
                "source": "dashboard.log",
                "observation": "dashboard home page responded in 120 ms during a practice check",
            }
        ],
        "deploys": [
            {
                "id": "deploy-1",
                "service": "dashboard",
                "version": "1.8.0",
                "previous_version": "1.7.2",
                "status": "succeeded",
                "at": "2026-04-01T11:00:00Z",
                "note": "dashboard release 1.8.0 finished cleanly",
            }
        ],
    },
    "ESC-1005": {
        "id": "ESC-1005",
        "title": "Checkout is down for customers",
        "customer_tier": "gold",
        "service": "checkout-web",
        "ticket": "Checkout is down for every gold customer. This is a sev-1 outage.",
        "logs": [
            {
                "id": "log-1",
                "source": "checkout-web.log",
                "observation": "checkout-web health check failed and the service is unavailable",
            },
            {
                "id": "log-2",
                "source": "checkout-web.log",
                "observation": "sev-1 outage: checkout is down for customers",
            },
        ],
        "deploys": [
            {
                "id": "deploy-1",
                "service": "checkout-web",
                "version": "9.1.0",
                "previous_version": "9.0.5",
                "status": "succeeded",
                "at": "2026-04-02T08:00:00Z",
                "note": "checkout-web release 9.1.0 finished cleanly",
            }
        ],
    },
}


def list_escalations():
    """Every practice escalation, in catalog order. Each one is a copy."""
    return [copy.deepcopy(item) for item in ESCALATIONS.values()]


def get_escalation(escalation_id):
    """One practice escalation, or UNKNOWN_ESCALATION if the id is not in the catalog.

    Returns a deep copy so a tool cannot edit the catalog by accident.
    """
    try:
        raw = ESCALATIONS[escalation_id]
    except KeyError:
        known = ", ".join(ESCALATIONS)
        raise AgentError(
            "UNKNOWN_ESCALATION",
            f"no practice escalation named {escalation_id!r}. Known ids: {known}.",
        )
    return copy.deepcopy(raw)
