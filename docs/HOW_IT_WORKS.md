# How the escalation agent works

This page is for someone new to the code. Read it with `agent.py` open.

The agent handles one fake support escalation. It walks a checklist of tools. It keeps what it learned in a state object. It saves that object to a JSON file after every step. When it wants to restart, roll back, or page someone, it stops and asks a human. Only `y` or `yes` lets a simulated line get appended to a local log.

## The picture

```mermaid
flowchart TD
    startNode([Start]) --> loadMem[Load memory JSON]
    loadMem -->|already settled| already([Stop: ALREADY_RESOLVED])
    loadMem -->|sticky stop| sticky([Stop: the saved reason])
    loadMem -->|proposal waiting| gate[Ask the human]
    loadMem -->|still working| budget{Steps left?}
    budget -->|no| maxed([Stop: MAX_STEPS_REACHED])
    budget -->|yes| model[Practice or real model picks one tool]
    model -->|unknown name| unknown([Stop: UNKNOWN_TOOL])
    model -->|plain text| ignore[Ignore the text]
    ignore --> budget
    model -->|search_runbooks| search[Search local runbooks]
    search -->|nothing| nomatch([Stop: NO_RUNBOOK_MATCH])
    search -->|hits| save[Save state]
    model -->|read_logs or deploys or draft| save
    model -->|rank_hypotheses| rank[Link evidence ids]
    rank -->|no ids linked| thin([Stop: INSUFFICIENT_EVIDENCE])
    rank -->|linked| save
    model -->|propose_action| pending[Store a pending approval]
    pending -->|defer| wait([Stop: APPROVAL_REQUIRED])
    pending -->|ask now| gate
    gate -->|y or yes| sim[Append one line to the local log]
    sim --> done([Stop: TRIAGE_COMPLETE])
    gate -->|anything else| denied([Stop: ACTION_DENIED])
    save --> budget
```

Follow one arrow at a time. The sample ticket `ESC-1001` takes the long path: search, logs, deploys, rank, draft, propose, then the human question.

## A walk through ESC-1001

The ticket says checkout started returning 500 after a deploy. The customer tier is gold. The service name is `checkout-api`. All of that is fake, in `sample_data.py`.

1. **Search.** `search_runbooks` counts how many distinctive words from the ticket appear in each local runbook. "Rollback a bad deploy" shares most of them, so it comes back first. A section that shares one word can still come back lower down. An empty list is the only search that stops the run.
2. **Logs.** `read_logs` copies the fake log lines onto the state as evidence. Each line has an id, such as `log-1`.
3. **Deploys.** `check_recent_deploys` does the same for the fake deploy of `checkout-api` 2.4.1. That deploy is marked failed. Its evidence id is `deploy-1`.
4. **Hypotheses.** `rank_hypotheses` keeps three fixed hypotheses. A keyword in an observation attaches that evidence id to a hypothesis. The checkout lines mention deploy, error rate, and 500, so "Bad deploy" gets `log-1`, `log-2`, and `deploy-1`. Every hypothesis stays `unverified`. `confirmed_root_cause` stays empty. The ticket sentence itself is not evidence.
5. **Draft.** `draft_customer_update` writes a paragraph into the state. The first line is "Draft only. This was not sent." Invented evidence ids are dropped.
6. **Propose.** `propose_action` returns a pending rollback from 2.4.1 to 2.4.0. It does not change a cluster. The practice model also sends `approved=true`. The loop prints that the flag was ignored.
7. **Ask.** The terminal shows the proposal, the evidence ids, and the draft, then `Approve this action? (y/n)`.
8. **Settle.** `y` appends one line to `action.log` and stops with `TRIAGE_COMPLETE`. Any other answer stops with `ACTION_DENIED` and writes no line.

## The state is the memory

`EscalationState` in `state.py` is a small object with:

- `checked` — whether runbooks, logs, and deploys have been read
- `evidence` — the rows collected so far
- `hypotheses` — the ranked list, with evidence ids
- `customer_draft` — the unsent text
- `pending_approval` — the proposal, or empty
- `settlements` — what the human decided
- `step_log` — short lines you can read in the JSON
- `steps_used` — how many model calls this escalation has spent

`save_state` writes `memory/<escalation id>.json` after a step. One file holds one escalation. `ESC-1002` gets its own file and does not overwrite `ESC-1001`.

A second run calls `load_state`. If the checklist is half done, the practice model skips the boxes that are already filled. If a proposal is waiting, the second run asks the human and does not call the model again. If the case is already settled, the second run stops with `ALREADY_RESOLVED` and does not record a second action.

`--fresh` deletes that file so you can start the same ticket over.

## The approval boolean

This is the part to be able to say out loud.

`propose_action` never runs anything. It is not even able to write the log. The function that writes the log is `record_simulated_action`, and it is not in the tool list the model can call.

`record_simulated_action` writes a line only when `approved is True`. In Python, `True` is a boolean. The string `"yes"`, the string `"true"`, and the string `"approved"` are not that boolean, so they do not write a line.

`human_said_yes` is the only function that turns a typed answer into that boolean, and only for `y` or `yes`. `settle_proposal` checks `said_yes is True` again, so a bug that passed the word `"yes"` through would still deny.

Text from the model is stored on the step log as ignored. It is not read as a yes.

## The step limit

`MAX_STEPS` in `agent.py` is 8. The checklist uses 6 model calls. The question to the human is not a model call.

Before every model call the loop looks at `state.steps_used`. When that number has reached the limit, the loop does not call the model. It stops with `MAX_STEPS_REACHED`. The count is saved in the JSON file, so a later run continues from that number instead of resetting it. Raise `--max-steps` if you want more room on a later run.

## Stop reasons

The loop prints `Stop reason: NAME` and stores the name on the result.

| Name | When it happens |
| --- | --- |
| `TRIAGE_COMPLETE` | The human said yes. One simulated line is in the local log. The draft was not sent. |
| `ACTION_DENIED` | The human did not say yes. The action log gained no line. |
| `APPROVAL_REQUIRED` | A proposal is saved and this run was told not to ask yet (`--defer-approval`). |
| `MAX_STEPS_REACHED` | The step budget was used before the case was settled. |
| `ALREADY_RESOLVED` | The JSON file says this case is finished. Nothing new ran. |
| `NO_RUNBOOK_MATCH` | Search returned nothing. No fix is invented. `ESC-1003` does this. |
| `INSUFFICIENT_EVIDENCE` | Hypotheses were ranked and none has an evidence id, or a proposal arrived before any id was linked. `ESC-1004` does this. |
| `UNKNOWN_TOOL` | The model named a tool that is not in the registry. Nothing ran. |

`NO_RUNBOOK_MATCH`, `INSUFFICIENT_EVIDENCE`, and `UNKNOWN_TOOL` stick. The next run repeats them and does not call a tool. `--fresh` clears that.

Crashes use a different kind of name, on `AgentError`. Examples: `MISSING_KEY`, `UNKNOWN_ESCALATION`, `UNKNOWN_ACTION`, `NOT_IMPLEMENTED_APPROVAL`, `BAD_TOOL_ARGS`, `EVIDENCE_INVALID`. Those are listed at the top of `agent.py`.

## The two models

`PracticeModel` in `practice_model.py` is the default. It looks at `checked`, `hypotheses`, and `customer_draft` and calls the next empty box. It needs no key and no network. It sends `approved=true` with the proposal on purpose, so the demo always shows the loop ignoring that claim.

`RealModel` is `--real`. It calls `grok-build-0.1` at `https://api.x.ai/v1`. `make_client` reads `XAI_API_KEY` from the environment. The key is not printed and is not written into the JSON file. The chat transcript is not saved. On a resumed run the new chat is shown the saved state. That is the memory.

## Where each part lives

| File | What it is |
| --- | --- |
| `agent.py` | The loop, the approval gate, the real-model switch, and the command line |
| `practice_model.py` | The offline checklist model |
| `tools.py` | The six tools, plus the log writer the model cannot call |
| `state.py` | The state object and the JSON file |
| `sample_data.py` | Five fake escalations |
| `turns.py` | The small note a model hands the loop |
| `runbooks/` | Four short practice runbooks |
| `errors.py` | Named failures |
| `tests/` | Offline pytest |
