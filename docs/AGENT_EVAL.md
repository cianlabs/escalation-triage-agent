# Agent eval set and traces

This scores the escalation triage agent on synthetic fixtures. It is separate from `evaluation.py`, which scores the public incident ranker, and from `runbook_model_eval.py`, which can call a live model.

The default run is offline. It uses `PracticeModel`, the local runbook files, and the in-process handoff and MCP helpers. It does not read `XAI_API_KEY`. Grok remains the default cloud model for `runbook_search.py --model-answer` and is not called here.

## What is scored

Golden cases live in `fixtures/agent-eval/golden.json`. A smaller locked set lives in `fixtures/agent-eval/holdout.json`. Both are synthetic. Neither file contains customer data.

| Area | What a pass means |
| --- | --- |
| Tool choice | The practice model calls the checklist tools in order, or a scripted model stops on an unknown tool or the step budget. |
| Stop reason | The printed stop reason matches the case, including deny, defer, approve, no runbook, insufficient evidence, and handoff limits. |
| Citations | A runbook handoff quotes a line whose citation starts with the expected guide. A triage draft names the evidence ids the ranker linked. |
| Human gate | `propose_action` stays `pending`. The action log is still empty when the human is asked. `y` or `yes` appends one simulated line. `n`, `no`, and the word `approved` do not. `--defer` does not ask. |
| MCP | `propose_action` and `record_simulated_action` are not registered and cannot be invoked. |

A model flag named `approved` is still ignored. The specialist only searches and cites.

## Run it

```sh
python agent_eval.py
python agent_eval.py --check
python agent_eval.py --trace-dir /tmp/agent-eval-traces
```

`--check` exits 1 when any case fails. CI runs `python agent_eval.py --check --trace-dir /tmp/agent-eval-traces` from `.github/workflows/tests.yml` on Python 3.11 and 3.13. The report prints `pass` or `FAIL` per case id. A failure also prints the check name and the trace path.

An offline run of the committed files prints `Agent eval: 20/20 passed`: 15/15 on `agent-eval-golden-v1` and 5/5 on `agent-eval-holdout-v1`. That is the practice model. `agent.py --real` is optional, needs `XAI_API_KEY`, and is outside CI.

## Inspect a trace

Each case writes `<trace-dir>/<case-id>.json`. The default directory is `traces/agent-eval/`, which is gitignored. A trace includes:

- `input` — the synthetic case fields that were run
- `events` — model turns (tool name and arguments), approval prompts, handoff hops, and citations
- `stop_reason`
- `elapsed_ms` — wall time for that case
- `checks` — each scored assertion
- `pending_approval` and `action_log` when those apply

Open the failed case file first. The events list is the tool sequence. `log_empty` on an `approval_prompt` event shows the gate had not written yet.

## Known gaps

- The practice model is a fixed checklist. This set does not score Grok's tool choice. A live `--real` run still needs `XAI_API_KEY` and is outside CI.
- Handoff citations are the extractive citer, not a graded model answer.
- Public incident family scores stay in `evaluation.py`. Do not mix the two denominators.
- Do not edit an expected stop reason to absorb a regression. Add a new dataset id if the contract changes.
