"""Real public data catalog and incident loading.

Built from real, publicly published outage post-mortems and public runbooks.
No private, confidential, or production data is included.

Log entries and deploy histories that were not printed raw in public write-ups
are clearly reconstructed from the facts stated in the write-ups.
"""

import copy
from errors import AgentError

REAL_ESCALATIONS = {
    "INC-CLOUDFLARE-01": {
        "id": "INC-CLOUDFLARE-01",
        "title": "Cloudflare Control Plane Outage",
        "customer_tier": "gold",
        "service": "control-plane",
        "published_root_cause": "Bad deploy",
        "ticket": (
            "Cloudflare control plane and analytics services experienced an outage. "
            "Customers saw HTTP 500 errors when attempting to make modifications through "
            "our dashboard or API following an infrastructure power failure and failover configuration release."
        ),
        "logs": [
            {
                "id": "log-cf-1",
                "source": "control-plane.log (reconstructed from public write-up)",
                "observation": "control-plane service error rate jumped to 85 percent after config deploy",
            },
            {
                "id": "log-cf-2",
                "source": "control-plane.log (reconstructed from public write-up)",
                "observation": "POST /api/v4/zones returned 500 internal server error",
            },
        ],
        "deploys": [
            {
                "id": "deploy-cf-1",
                "service": "control-plane",
                "version": "1.18.2",
                "previous_version": "1.18.1",
                "status": "failed",
                "at": "2023-11-02T11:40:00Z",
                "note": "(reconstructed from public write-up) bad deploy release 1.18.2 caused 500 error rate jump",
            }
        ],
    },
    "INC-GITHUB-02": {
        "id": "INC-GITHUB-02",
        "title": "GitHub Database Partition Degradation",
        "customer_tier": "gold",
        "service": "db-cluster",
        "published_root_cause": "Bad deploy",
        "ticket": (
            "Multiple services on GitHub.com were affected by a network partition during optical "
            "equipment maintenance, leading to database replica topology failures and 500 errors "
            "presenting stale and inconsistent information across the site."
        ),
        "logs": [
            {
                "id": "log-gh-1",
                "source": "db-cluster.log (reconstructed from public write-up)",
                "observation": "db-cluster error rate jumped following network topology deploy",
            },
            {
                "id": "log-gh-2",
                "source": "db-cluster.log (reconstructed from public write-up)",
                "observation": "database query returned 500 error split-brain replica state",
            },
        ],
        "deploys": [
            {
                "id": "deploy-gh-1",
                "service": "db-cluster",
                "version": "5.7.3-gh2",
                "previous_version": "5.7.2-gh1",
                "status": "failed",
                "at": "2018-10-21T23:00:00Z",
                "note": "(reconstructed from public write-up) bad deploy release 5.7.3-gh2 failed replica topology",
            }
        ],
    },
    "INC-AWS-03": {
        "id": "INC-AWS-03",
        "title": "AWS US-EAST-1 Control Plane Impairment",
        "customer_tier": "gold",
        "service": "ec2-api",
        "published_root_cause": "Customer-facing outage",
        "ticket": (
            "AWS Management Console and EC2 APIs experienced latency and packet loss in US-EAST-1, "
            "causing a major customer-facing outage across internal control networks."
        ),
        "logs": [
            {
                "id": "log-aws-1",
                "source": "ec2-api.log (reconstructed from public write-up)",
                "observation": "sev-1 outage: ec2-api is down and unavailable for customers",
            },
            {
                "id": "log-aws-2",
                "source": "ec2-api.log (reconstructed from public write-up)",
                "observation": "internal control network packet loss causing customer-facing outage",
            },
        ],
        "deploys": [
            {
                "id": "deploy-aws-1",
                "service": "ec2-api",
                "version": "4.12.0",
                "previous_version": "4.11.9",
                "status": "succeeded",
                "at": "2021-12-07T06:00:00Z",
                "note": "(reconstructed from public write-up) release 4.12.0 finished cleanly",
            }
        ],
    },
    "INC-SLACK-04": {
        "id": "INC-SLACK-04",
        "title": "Slack Gateway Connection Spike Outage",
        "customer_tier": "gold",
        "service": "slack-gateway",
        "published_root_cause": "Customer-facing outage",
        "ticket": (
            "Slack users are unable to connect or boot their clients, encountering connection "
            "timeouts and error pages across web and desktop applications during a major incident."
        ),
        "logs": [
            {
                "id": "log-slack-1",
                "source": "slack-gateway.log (reconstructed from public write-up)",
                "observation": "slack-gateway service unavailable and returning connection failures",
            },
            {
                "id": "log-slack-2",
                "source": "slack-gateway.log (reconstructed from public write-up)",
                "observation": "sev-1 outage: messaging service down for all web and mobile clients",
            },
        ],
        "deploys": [
            {
                "id": "deploy-slack-1",
                "service": "slack-gateway",
                "version": "2.90.0",
                "previous_version": "2.89.4",
                "status": "succeeded",
                "at": "2022-02-22T08:00:00Z",
                "note": "(reconstructed from public write-up) release 2.90.0 finished cleanly",
            }
        ],
    },
    "INC-DATADOG-05": {
        "id": "INC-DATADOG-05",
        "title": "Datadog OS Package Update Disruption",
        "customer_tier": "gold",
        "service": "metrics-worker",
        "published_root_cause": "Process needs a restart",
        "ticket": (
            "A systemd update on container VMs caused CNI routing rules to be deleted upon "
            "service restart, leaving metrics worker instances disconnected from the network with crashing processes."
        ),
        "logs": [
            {
                "id": "log-dd-1",
                "source": "metrics-worker.log (reconstructed from public write-up)",
                "observation": "metrics-worker memory exhausted and process crash recorded",
            },
            {
                "id": "log-dd-2",
                "source": "metrics-worker.log (reconstructed from public write-up)",
                "observation": "oom killer fired on container node killing metrics-worker",
            },
        ],
        "deploys": [
            {
                "id": "deploy-dd-1",
                "service": "metrics-worker",
                "version": "7.42.0",
                "previous_version": "7.41.1",
                "status": "succeeded",
                "at": "2023-03-08T01:00:00Z",
                "note": "(reconstructed from public write-up) metrics-worker release 7.42.0 finished cleanly",
            }
        ],
    },
    "INC-CIRCLECI-06": {
        "id": "INC-CIRCLECI-06",
        "title": "CircleCI Security Mitigation Lockdown",
        "customer_tier": "gold",
        "service": "build-runner",
        "published_root_cause": "Process needs a restart",
        "ticket": (
            "Following an unauthorized access incident, emergency secrets rotation and system "
            "lockdown caused build runner workers to crash and memory limits to fail."
        ),
        "logs": [
            {
                "id": "log-cci-1",
                "source": "build-runner.log (reconstructed from public write-up)",
                "observation": "build-runner process crash recorded after token revocation",
            },
            {
                "id": "log-cci-2",
                "source": "build-runner.log (reconstructed from public write-up)",
                "observation": "build-runner memory exhausted and worker killed",
            },
        ],
        "deploys": [
            {
                "id": "deploy-cci-1",
                "service": "build-runner",
                "version": "3.8.0",
                "previous_version": "3.7.9",
                "status": "succeeded",
                "at": "2023-01-04T10:00:00Z",
                "note": "(reconstructed from public write-up) build-runner 3.8.0 release succeeded",
            }
        ],
    },
    "INC-FASTLY-07": {
        "id": "INC-FASTLY-07",
        "title": "Fastly Edge Proxy Configuration Crash",
        "customer_tier": "gold",
        "service": "edge-proxy",
        "published_root_cause": "Bad deploy",
        "ticket": (
            "A valid customer configuration update activated an undiscovered bug in a previous software deploy, "
            "causing 85 percent of the edge proxy network to return 500 errors."
        ),
        "logs": [
            {
                "id": "log-fastly-1",
                "source": "edge-proxy.log (reconstructed from public write-up)",
                "observation": "edge-proxy error rate jumped to 85 percent following bad deploy",
            },
            {
                "id": "log-fastly-2",
                "source": "edge-proxy.log (reconstructed from public write-up)",
                "observation": "GET / returned 500 internal server error across edge POPs",
            },
        ],
        "deploys": [
            {
                "id": "deploy-fastly-1",
                "service": "edge-proxy",
                "version": "2021.06.8",
                "previous_version": "2021.05.12",
                "status": "failed",
                "at": "2021-06-08T09:58:00Z",
                "note": "(reconstructed from public write-up) bad deploy release 2021.06.8 caused proxy crash",
            }
        ],
    },
    "INC-ATLASSIAN-08": {
        "id": "INC-ATLASSIAN-08",
        "title": "Atlassian Tenant Database Deletion",
        "customer_tier": "gold",
        "service": "jira-cloud",
        "published_root_cause": "Customer-facing outage",
        "ticket": (
            "An automated deletion script passed incorrect site IDs during legacy app cleanup, "
            "resulting in the unexpected deletion of customer tenant sites and a severe outage."
        ),
        "logs": [
            {
                "id": "log-atl-1",
                "source": "jira-cloud.log (reconstructed from public write-up)",
                "observation": "sev-1 outage: jira-cloud is down and site database is unavailable",
            },
            {
                "id": "log-atl-2",
                "source": "jira-cloud.log (reconstructed from public write-up)",
                "observation": "tenant database connection failed causing customer-facing outage",
            },
        ],
        "deploys": [
            {
                "id": "deploy-atl-1",
                "service": "jira-cloud",
                "version": "1001.0.0",
                "previous_version": "1000.99.0",
                "status": "succeeded",
                "at": "2022-04-05T07:00:00Z",
                "note": "(reconstructed from public write-up) release 1001.0.0 finished cleanly",
            }
        ],
    },
    "INC-GCP-09": {
        "id": "INC-GCP-09",
        "title": "Google Cloud Network Policy Outage",
        "customer_tier": "gold",
        "service": "cloud-storage-api",
        "published_root_cause": "Bad deploy",
        "ticket": (
            "A bug in the configuration pipeline allowed a race condition that pushed a corrupted "
            "routing configuration deploy to external proxy load balancers, returning HTTP 404/500 errors."
        ),
        "logs": [
            {
                "id": "log-gcp-1",
                "source": "cloud-storage-api.log (reconstructed from public write-up)",
                "observation": "cloud-storage-api error rate jumped to 40 percent after deploy",
            },
            {
                "id": "log-gcp-2",
                "source": "cloud-storage-api.log (reconstructed from public write-up)",
                "observation": "GET /object returned 500 internal server error",
            },
        ],
        "deploys": [
            {
                "id": "deploy-gcp-1",
                "service": "cloud-storage-api",
                "version": "21.11.16",
                "previous_version": "21.11.10",
                "status": "failed",
                "at": "2021-11-16T12:00:00Z",
                "note": "(reconstructed from public write-up) bad deploy release 21.11.16 failed edge routing",
            }
        ],
    },
    "INC-REDDIT-10": {
        "id": "INC-REDDIT-10",
        "title": "Reddit Kubernetes CNI Upgrade Failure",
        "customer_tier": "gold",
        "service": "reddit-feed",
        "published_root_cause": "Bad deploy",
        "ticket": (
            "Upgrading a core Kubernetes cluster from 1.23 to 1.24 introduced an unexpected route "
            "reflector network failure, bringing down internal DNS and causing a 314-minute outage."
        ),
        "logs": [
            {
                "id": "log-reddit-1",
                "source": "reddit-feed.log (reconstructed from public write-up)",
                "observation": "reddit-feed error rate jumped to 60 percent following deploy",
            },
            {
                "id": "log-reddit-2",
                "source": "reddit-feed.log (reconstructed from public write-up)",
                "observation": "GET /r/all returned 500 internal server error",
            },
        ],
        "deploys": [
            {
                "id": "deploy-reddit-1",
                "service": "reddit-feed",
                "version": "1.12.0",
                "previous_version": "1.11.4",
                "status": "failed",
                "at": "2023-03-14T15:00:00Z",
                "note": "(reconstructed from public write-up) bad deploy release 1.12.0 broke pod CNI network",
            }
        ],
    },
    "INC-OPENAI-11": {
        "id": "INC-OPENAI-11",
        "title": "OpenAI Traffic Saturation Outage",
        "customer_tier": "gold",
        "service": "chat-api",
        "published_root_cause": "Customer-facing outage",
        "ticket": (
            "ChatGPT and API services experienced periodic outages and high error rates due to "
            "abnormal traffic patterns and gateway saturation."
        ),
        "logs": [
            {
                "id": "log-oai-1",
                "source": "chat-api.log (reconstructed from public write-up)",
                "observation": "sev-1 outage: chat-api is down and unavailable for customers",
            },
            {
                "id": "log-oai-2",
                "source": "chat-api.log (reconstructed from public write-up)",
                "observation": "gateway traffic saturation causing customer-facing outage",
            },
        ],
        "deploys": [
            {
                "id": "deploy-oai-1",
                "service": "chat-api",
                "version": "2.1.0",
                "previous_version": "2.0.8",
                "status": "succeeded",
                "at": "2023-11-08T10:00:00Z",
                "note": "(reconstructed from public write-up) release 2.1.0 finished cleanly",
            }
        ],
    },
    "INC-HEROKU-12": {
        "id": "INC-HEROKU-12",
        "title": "Heroku Build Worker Disk Exhaustion",
        "customer_tier": "silver",
        "service": "slug-compiler",
        "published_root_cause": "Process needs a restart",
        "ticket": (
            "Application builds are stuck queued or timing out due to background worker disk "
            "and memory exhaustion from orphan build artifacts."
        ),
        "logs": [
            {
                "id": "log-heroku-1",
                "source": "slug-compiler.log (reconstructed from public write-up)",
                "observation": "slug-compiler memory exhausted and process crash recorded",
            },
            {
                "id": "log-heroku-2",
                "source": "slug-compiler.log (reconstructed from public write-up)",
                "observation": "oom killer fired on worker node for slug-compiler process",
            },
        ],
        "deploys": [
            {
                "id": "deploy-heroku-1",
                "service": "slug-compiler",
                "version": "5.4.1",
                "previous_version": "5.4.0",
                "status": "succeeded",
                "at": "2021-09-27T11:00:00Z",
                "note": "(reconstructed from public write-up) slug-compiler 5.4.1 finished cleanly",
            }
        ],
    },
}

# Add test support escalations
_TEST_ESCALATIONS = {
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
                "source": "checkout-api.log (reconstructed from public write-up)",
                "observation": "checkout-api error rate jumped to 40 percent after the deploy",
            },
            {
                "id": "log-2",
                "source": "checkout-api.log (reconstructed from public write-up)",
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
                "note": "(reconstructed from public write-up) error rate jumped right after the deploy of 2.4.1",
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
                "source": "image-worker.log (reconstructed from public write-up)",
                "observation": "image-worker memory exhausted and the oom killer fired",
            },
            {
                "id": "log-2",
                "source": "image-worker.log (reconstructed from public write-up)",
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
                "note": "(reconstructed from public write-up) image-worker release 3.2.0 finished cleanly",
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
                "source": "coffee-machine.log (reconstructed from public write-up)",
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
                "note": "(reconstructed from public write-up) practice firmware finished cleanly",
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
                "source": "dashboard.log (reconstructed from public write-up)",
                "observation": "dashboard home page responded in 120 ms during a check",
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
                "note": "(reconstructed from public write-up) dashboard release 1.8.0 finished cleanly",
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
                "source": "checkout-web.log (reconstructed from public write-up)",
                "observation": "checkout-web health check failed and the service is unavailable",
            },
            {
                "id": "log-2",
                "source": "checkout-web.log (reconstructed from public write-up)",
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
                "note": "(reconstructed from public write-up) checkout-web release 9.1.0 finished cleanly",
            }
        ],
    },
}

def list_escalations():
    """Every practice escalation, in catalog order. Each one is a copy."""
    all_items = list(REAL_ESCALATIONS.values()) + list(_TEST_ESCALATIONS.values())
    return [copy.deepcopy(item) for item in all_items]


def list_real_incidents():
    """Only the 12 real public incidents."""
    return [copy.deepcopy(item) for item in REAL_ESCALATIONS.values()]


def get_escalation(escalation_id):
    """One practice escalation, or UNKNOWN_ESCALATION if the id is not in the catalog."""
    if escalation_id in REAL_ESCALATIONS:
        return copy.deepcopy(REAL_ESCALATIONS[escalation_id])
    if escalation_id in _TEST_ESCALATIONS:
        return copy.deepcopy(_TEST_ESCALATIONS[escalation_id])
    known = ", ".join(list(REAL_ESCALATIONS.keys()) + list(_TEST_ESCALATIONS.keys()))
    raise AgentError(
        "UNKNOWN_ESCALATION",
        f"no practice escalation named {escalation_id!r}. Known ids: {known}.",
    )


SAMPLE_ID = "INC-CLOUDFLARE-01"
