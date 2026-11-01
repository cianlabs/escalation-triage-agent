# escalation-triage-agent

An agent that triages one fake support escalation, step by step, and waits for a human before any simulated action.

## Install and run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python agent.py --sample
```

The third command needs no API key and no network. It uses a practice model. At the end it asks `Approve this action? (y/n)`. Type `y` or `yes` to append one simulated line to `action.log`. Anything else writes nothing.

The same run saves `memory/ESC-1001.json`. Run it again and it resumes. If you already answered, it stops with `ALREADY_RESOLVED`. Start the sample over with:

```bash
.venv/bin/python agent.py --sample --fresh
```

## Example run

This is `ESC-1001`, a made-up checkout failure. The `y` on the prompt line is what you type. The practice model sends `approved=true` with the proposal. The loop ignores that flag and still asks.

```text
No memory file yet. Starting from the ticket.
Escalation ESC-1001
Tier: gold
Service: checkout-api
Ticket: Checkout returns 500 after the 14:05 deploy. Error rate jumped. Please roll back if the new version is bad.

Step 1 of 8
Thinking: I should search the local runbooks before I guess.
Tool: search_runbooks query='Checkout returns 500 after the 14:05 deploy. Error rate jumped. Please roll back if the...'
1. [0.917] Rollback a bad deploy (rollback_bad_deploy.txt)
   If the error rate jumped after a deploy, roll back the service.
   A burst of 500 responses on checkout is a sign the new version is bad.
   Roll back only after a human approves. A restart is the wrong first step.
2. [0.083] Customer-facing outage (customer_outage.txt)
   Page oncall when checkout is down or unavailable for a customer.
   A sev-1 outage needs a human.
   Do not change the service until that human approves a specific action.

Step 2 of 8
Thinking: I should read the practice logs for this escalation.
Tool: read_logs escalation_id='ESC-1001'
- log-1 (checkout-api.log): checkout-api error rate jumped to 40 percent after the deploy
- log-2 (checkout-api.log): POST /checkout returned 500

Step 3 of 8
Thinking: I should check the recent practice deploys for this service.
Tool: check_recent_deploys service='checkout-api'
- deploy-1 checkout-api 2.4.1 status=failed at 2026-04-02T14:05:00Z

Step 4 of 8
Thinking: I should rank hypotheses and keep the evidence ids on them.
Tool: rank_hypotheses evidence=3 row(s)
- Bad deploy: evidence log-1, log-2, deploy-1 (unverified)
- Process needs a restart: evidence none (unverified)
- Customer-facing outage: evidence none (unverified)
Confirmed root cause: none

Step 5 of 8
Thinking: I should draft a customer update and not send it.
Tool: draft_customer_update hypothesis='Bad deploy'
Draft only. This was not sent.
We are investigating an issue on checkout-api for the gold tier. What we were told: Checkout returns 500 after the 14:05 deploy. Error rate jumped. Please roll back if the new version is bad. The leading hypothesis is Bad deploy, linked to evidence log-1, log-2, deploy-1. We have not confirmed a root cause, and we have not taken an action.

Step 6 of 8
Thinking: I am proposing an action. I am not allowed to approve it.
Tool: propose_action kind=rollback target=checkout-api
Note: the model sent an approved flag. That flag is ignored.
Pending rollback on checkout-api. Nothing has run.

--- Proposed action needs your approval ---
Nothing has run yet.
kind: rollback
target: checkout-api
reason: Bad deploy is the leading hypothesis. Evidence: log-1, log-2, deploy-1.
details: Would roll checkout-api back from 2.4.1 to 2.4.0. No cluster is changed.
Leading hypothesis: Bad deploy (not confirmed)
Evidence ids: log-1, log-2, deploy-1
Customer draft (not sent):
Draft only. This was not sent.
We are investigating an issue on checkout-api for the gold tier. What we were told: Checkout returns 500 after the 14:05 deploy. Error rate jumped. Please roll back if the new version is bad. The leading hypothesis is Bad deploy, linked to evidence log-1, log-2, deploy-1. We have not confirmed a root cause, and we have not taken an action.
A yes appends one simulated line to action.log.
A yes does not restart, roll back, page anyone, or send the draft.
Approve this action? (y/n) y
Action approved. The simulation was appended to the local log.
Log: 2026-11-01T22:51:45Z | simulated | rollback | target=checkout-api | escalation=ESC-1001 | Would roll checkout-api back from 2.4.1 to 2.4.0. No cluster is changed.
Stop reason: TRIAGE_COMPLETE
The human said yes. The simulated action was appended to the local log. The customer draft was not sent.
```

The timestamp on the log line is the time of the run. Typing `n` instead ends like this, and `action.log` is not created:

```text
Approve this action? (y/n) n
Action denied. Nothing was simulated.
Stop reason: ACTION_DENIED
The human did not say yes. Nothing was simulated and the local action log was not written.
```

Other practice tickets: `ESC-1002` (restart), `ESC-1005` (page oncall), `ESC-1003` (no runbook match), `ESC-1004` (no evidence linked, so no proposal). List them with `.venv/bin/python agent.py --list`.

To save a proposal and answer it on a second run:

```bash
.venv/bin/python agent.py --sample --defer-approval
.venv/bin/python agent.py --sample
```

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

`NO_RUNBOOK_MATCH`, `INSUFFICIENT_EVIDENCE`, and `UNKNOWN_TOOL` stick. The next run repeats them. `--fresh` clears the memory file.

Bad inputs raise `AgentError` and print a name such as `MISSING_KEY`, `UNKNOWN_ESCALATION`, `UNKNOWN_ACTION`, or `NOT_IMPLEMENTED_APPROVAL`. The full list is at the top of `agent.py`.

A longer walkthrough and a diagram are in [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md).

## Tests

```bash
.venv/bin/python -m pytest -q
```

The tests use the practice model and a fake client. They need no API key and they make no network calls. GitHub Actions runs the same command on Python 3.11 and 3.13.

## Optional real model

```bash
export XAI_API_KEY="your key"
.venv/bin/python agent.py --sample --fresh --real
```

Set the key in the terminal. Do not put it in a file. The flag calls `grok-build-0.1`. The key is not printed and is not written into the memory file. Without the flag, the practice model is used even if the key is set.

## Deliberately not built

- Live tickets, live logs, and real credentials. The five escalations in `sample_data.py` are made up.
- A real restart, rollback, page, or customer send. A yes appends one line to `action.log` and stops there.
- A web page. The gate is the terminal prompt.
- Embeddings or a score cutoff. Search is word overlap. One shared word can still return a section. The loop stops for search only when nothing matches.
- A saved chat transcript. The JSON state is the memory. `--real` starts a new chat and shows it that state.
- An eval harness or a regression floor. Those live in the separate copilot-evals repo.
- The live model in CI. The workflow runs the offline tests only.
