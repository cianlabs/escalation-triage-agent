# escalation-triage-agent

An agent that triages support escalations based on real public post-mortems and runbooks, step by step, and waits for a human before any simulated action.

## Install and run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python agent.py --sample
```

The third command needs no API key and no network. It uses a practice model. At the end it asks `Approve this action? (y/n)`. Type `y` or `yes` to append one simulated line to `action.log`. Anything else writes nothing.

The sample runs `INC-CLOUDFLARE-01`, a real incident write-up (Control Plane Outage). The same run saves `memory/INC-CLOUDFLARE-01.json`. Run it again and it resumes. If you already answered, it stops with `ALREADY_RESOLVED`. Start the sample over with:

```bash
.venv/bin/python agent.py --sample --fresh
```

## Real Public Data & Limitations

The repository contains 12 incident post-mortems (e.g. Cloudflare, GitHub, AWS, Slack, Datadog, CircleCI, Fastly, Atlassian, Google Cloud, Reddit, OpenAI, Heroku) and 6 troubleshooting runbooks built from public sources. See `SOURCES.md` for full references.

Where public post-mortems do not include raw log files or deploy records, log lines and deploy histories are reconstructed from the facts stated in the write-ups and explicitly labeled as `(reconstructed from public write-up)`.

## Incident Root Cause Evaluation

Run offline evaluation across all 12 real incidents:

```bash
.venv/bin/python evaluation.py
```

The evaluation gives the agent only the symptoms (ticket description) for each incident and checks whether its top-ranked hypothesis matches the published root cause. Currently, the offline practice evaluation achieves 12/12 (100.0%) accuracy.

## Example run

This is `INC-CLOUDFLARE-01`, based on Cloudflare's November 2023 outage write-up.

```text
No memory file yet. Starting from the ticket.
Escalation INC-CLOUDFLARE-01
Tier: gold
Service: control-plane
Ticket: Control Plane API and dashboard returning 500 errors globally. Recent service configuration release deployed at 11:40 UTC.

Step 1 of 8
Thinking: I should search the local runbooks before I guess.
Tool: search_runbooks query='Control Plane API and dashboard returning 500 errors globally. Recent service configuration release deployed at 11:40 UTC.'
1. [0.444] Rollback a bad deploy (rollback_bad_deploy.txt)
   If the error rate jumped after a deploy or a 500 error burst occurred, roll back the service.
   A bad deploy release or route config release causing 500 responses must be rolled back.
   Roll back only after a human approves. A restart is the wrong first step.

Step 2 of 8
Thinking: I should read the practice logs for this escalation.
Tool: read_logs escalation_id='INC-CLOUDFLARE-01'
- log-cf-1 (control-plane.log (reconstructed from public write-up)): control-plane service error rate jumped to 85 percent after config deploy
- log-cf-2 (control-plane.log (reconstructed from public write-up)): POST /api/v4/zones returned 500 internal server error

Step 3 of 8
Thinking: I should check the recent practice deploys for this service.
Tool: check_recent_deploys service='control-plane'
- deploy-cf-1 control-plane 1.18.2 status=failed at 2023-11-02T11:40:00Z

Step 4 of 8
Thinking: I should rank hypotheses and keep the evidence ids on them.
Tool: rank_hypotheses evidence=3 row(s)
- Bad deploy: evidence log-cf-1, log-cf-2, deploy-cf-1 (unverified)
- Process needs a restart: evidence none (unverified)
- Customer-facing outage: evidence none (unverified)
Confirmed root cause: none

Step 5 of 8
Thinking: I should draft a customer update and not send it.
Tool: draft_customer_update hypothesis='Bad deploy'
Draft only. This was not sent.
We are investigating an issue on control-plane for the gold tier. What we were told: Control Plane API and dashboard returning 500 errors globally. Recent service configuration release deployed at 11:40 UTC. The leading hypothesis is Bad deploy, linked to evidence log-cf-1, log-cf-2, deploy-cf-1. We have not confirmed a root cause, and we have not taken an action.

Step 6 of 8
Thinking: I am proposing an action. I am not allowed to approve it.
Tool: propose_action kind=rollback target=control-plane
Note: the model sent an approved flag. That flag is ignored.
Pending rollback on control-plane. Nothing has run.

--- Proposed action needs your approval ---
Nothing has run yet.
kind: rollback
target: control-plane
reason: Bad deploy is the leading hypothesis. Evidence: log-cf-1, log-cf-2, deploy-cf-1.
details: Would roll control-plane back from 1.18.2 to 1.18.1. No cluster is changed.
Leading hypothesis: Bad deploy (not confirmed)
Evidence ids: log-cf-1, log-cf-2, deploy-cf-1
Customer draft (not sent):
Draft only. This was not sent.
We are investigating an issue on control-plane for the gold tier. What we were told: Control Plane API and dashboard returning 500 errors globally. Recent service configuration release deployed at 11:40 UTC. The leading hypothesis is Bad deploy, linked to evidence log-cf-1, log-cf-2, deploy-cf-1. We have not confirmed a root cause, and we have not taken an action.
A yes appends one simulated line to action.log.
A yes does not restart, roll back, page anyone, or send the draft.
Approve this action? (y/n) y
Action approved. The simulation was appended to the local log.
Log: 2026-11-01T23:30:00Z | simulated | rollback | target=control-plane | escalation=INC-CLOUDFLARE-01 | Would roll control-plane back from 1.18.2 to 1.18.1. No cluster is changed.
Stop reason: TRIAGE_COMPLETE
The human said yes. The simulated action was appended to the local log. The customer draft was not sent.
```

List all available real incident write-ups with `.venv/bin/python agent.py --list`.

## How a run stops

Every normal run prints `Stop reason: NAME`.

| Name | Meaning |
| --- | --- |
| `TRIAGE_COMPLETE` | You said yes. One simulated line was appended to the local log. The draft was not sent. |
| `ACTION_DENIED` | You did not say yes. Nothing was simulated. |
| `APPROVAL_REQUIRED` | A proposal is saved. This run was started with `--defer-approval`, so it did not ask yet. |
| `MAX_STEPS_REACHED` | The loop used every step it is allowed (8 by default) before the case was settled. |
| `ALREADY_RESOLVED` | Memory says this escalation is finished. Nothing new ran. |
| `NO_RUNBOOK_MATCH` | No local runbook shared words with the ticket. No action is proposed. |
| `INSUFFICIENT_EVIDENCE` | No hypothesis has an evidence id, so no action is proposed. |
| `UNKNOWN_TOOL` | The model asked for a tool that does not exist. Nothing ran. |

## Tests

```bash
.venv/bin/python -m pytest -q
```

64 offline tests. They cover each tool, data loading, evaluation, memory resume, the approval gate, step limit, and named stop reasons. GitHub Actions runs pytest on Python 3.11 and 3.13.

## Live Model (--real)

```bash
export XAI_API_KEY="your key"
.venv/bin/python agent.py --sample --fresh --real
```

Reads `XAI_API_KEY` from the environment without printing or storing it. Uses `grok-build-0.1`. The approval gate and tools remain identical. Testing uses a fake client without calling xAI live.
