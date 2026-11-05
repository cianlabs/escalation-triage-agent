# escalation-triage-agent

A practice support agent that searches local runbooks, reads synthetic evidence, ranks hypotheses, drafts an update and asks a human before recording a simulated action. It saves each case so an investigation can resume later. Nothing restarts, rolls back, pages anyone or sends a message.

The public incident evaluation is separate from those synthetic workflow fixtures. It uses verified user-impact observations from 30 distinct incidents and calls this repository's unchanged ranking tool.

## Local runbook workspace

Run `python runbook_ui.py` from the repository, then open
[Runbook desk](http://127.0.0.1:8765). Ask a question, inspect the ranked
source passages, and click a citation to highlight its exact line.
Keyword search and rule-based answers work without an API key.
Semantic search uses local Ollama embeddings. Optional comparisons can use
a local Qwen model or xAI Grok. See [setup and scope](docs/RUNBOOK_UI.md)
and the [three-case walkthrough](docs/LOCAL_DEMO_WALKTHROUGH.md).

## Grok runbook answers

Grok is the default cloud model for runbook answers. OpenAI, Gemini and
local Ollama remain available when you name them. A failed Grok call stops.
It does not try another provider.

The model id comes from the xAI models guide, which recommends `grok-4.7`
for chat. Pass another id with `--xai-model` if you want a different model
listed for your key. This path does not assume `grok-build-0.1`. That name
is still the separate `--real` triage default below.

A Grok chat subscription and the xAI API can share an account, but xAI's
account FAQ says their billing is separate. Chat billing is managed at
grok.com. API calls are billed from xAI Console credits or the monthly
invoice. This program reads `XAI_API_KEY` from the environment only. It
does not read a key from a file, a browser login, or the page, and it does
not print or save the key.

Each runbook call uses the Responses API at `https://api.x.ai/v1/responses`
with `store` false, temperature 0, reasoning effort `low`, at most 800
visible output tokens, a 90 second timeout, and one retry only after HTTP
429 or 503. Reasoning tokens are not part of the 800 token cap. Twelve
frozen questions therefore allow at most 24 model calls. Offline tests do
not make those calls.

Do not send Live Search `search_parameters` on this path. The current xAI
OpenAPI schema for `POST /v1/responses` says live search has been removed
and that a request which sets that field fails with HTTP 410 Gone. That
includes a body that only sets `mode` to `off`. Search stays off because
the call does not include the `web_search` or `x_search` tools.

Do not send `tool_choice` on this path. A live smoke run returned
`Invalid request content: A tool_choice was set on the request but no tools
were specified.` The call had set `tool_choice` to `none` and had sent no
tools. The field is omitted. Do not send `max_tool_calls` either.
`ModelRequest` does not define that field.
The schema's agentic-turn cap is `max_turns`, and this path does not send
that either. `store` false, temperature 0, and `reasoning.effort` `low`
are defined. The reasoning guide lists `low` for `grok-4.7`; the default
is `high`. A rejected call prints the provider's error message when the
response body includes one. It does not print the API key or the raw
client exception, which can quote the request.

The commands below are for a later run in your own terminal. No live Grok
result is recorded in this repository. `pytest` checks routing, citations,
errors, saved-run metadata and the safety guards. A passing test is not an
answer-quality score.

One smoke question, on the five local guides, before spending a full run.
This question is not one of the T01–T12 comparison cases:

```sh
export XAI_API_KEY='paste the xAI Console key here'
.venv/bin/python runbook_search.py --model-answer --xai-model grok-4.7 'What approval form must I file before I restart Redis?'
```

Unset the variable when you are finished. Do not commit the key or paste
it into a saved file.

Then capture the same frozen semantic questions used for the Qwen
comparison, `fixtures/semantic/holdout.json` (T01–T12). Retrieval still
uses the local `embeddinggemma` model and the 0.3 cutoff. If that server
is down, the case fails and Grok is not called. There is no keyword or
Gemini substitute.

```sh
ollama pull embeddinggemma
.venv/bin/python runbook_model_eval.py --xai-model grok-4.7 --questions fixtures/semantic/holdout.json --output /tmp/grok-semantic-holdout.json
.venv/bin/python runbook_model_eval.py --replay /tmp/grok-semantic-holdout.json --questions fixtures/semantic/holdout.json --review-template /tmp/grok-reviews.json
```

The saved file records the provider, model id, dataset path, dataset id
`semantic-holdout-t01-t12`, and the question-file SHA-256. Review the
answers against the guides. Do not change the prompt, cutoff or scorer to
make this holdout look better. These questions already guided earlier
prompt edits. Leave the capture outside the repository until a person
reviews it. See [the evaluation notes](docs/RUNBOOK_EVALUATION.md).

## Inspect a specific public Actions run

```sh
.venv/bin/python agent.py --workflow-run https://github.com/cianlabs/escalation-triage-agent/actions/runs/41376006131
```

Use a public workflow-run URL to read its current state, jobs and any reported pending deployment gates. Queued does not mean stuck, and waiting does not automatically mean human approval. Jobs are tied to the reported attempt, and a second run read detects changes during collection. Missing or partial details stay unknown. No logs are downloaded, no credentials or models are used, no actions run and no cause is confirmed.

A complete read exits 0 even when the workflow failed; incomplete collection exits 1. See [examples, request boundaries and the learning exercise](docs/WORKFLOW_RUN.md).

For a portfolio demo, run `python agent.py --replay-comparison demo` from
the repository. The [workflow comparison evaluation](results/WORKFLOW_COMPARISON_EVALUATION.md)
shows where the rules and Gemini helped, and how the CLI handled model
unavailability.

## Read GitHub public status

```sh
.venv/bin/python agent.py --github-status
```

One real helper reads GitHub's public status API alongside two clearly labeled simulated checks. The live observation keeps its source URL, fetch time and status-page update time. Practice clues are displayed separately and excluded from investigating the real status. No model, account key, saved-memory or action path is used.

A failed, slow or malformed response means unknown, never healthy. GitHub's reported rollup describes provider impact and does not prove the cause or health of your service. The command exits 0 when it obtains a valid report, even if that report says major impact, and 1 when the live result is unknown. See [the source, failure rules and learning exercise](docs/GITHUB_STATUS.md).

## Is GitHub status relevant to my problem?

```sh
.venv/bin/python agent.py --github-status --problem 'GitHub Actions jobs are stuck in the queue'
```

The agent checks Actions specifically. A degraded Actions report is possibly related, not a confirmed cause. An operational report means no reported issue, not that your failure is ruled out. An unrelated outage is not blamed for the problem. If the service is unclear, add --component actions or choose another supported service. Historical problems get a warning that current status cannot answer for the earlier incident.

Your problem stays local; one fixed public summary request supplies the component data. Practice evidence remains excluded and no action runs. [Read the relevance rules and examples](docs/GITHUB_STATUS.md#compare-status-with-a-specific-problem).

## Collect three simulated sources concurrently

```sh
.venv/bin/python agent.py --collect-sample partial
```

Recent errors, recent changes and service health start together. Each check has its own timeout. The partial demo keeps a missing-route clue while clearly reporting a failed changes check and a timed-out health check. A failed, empty or missing check never becomes a healthy signal. Missing evidence stays visible in the investigation and next checks; the cause remains unconfirmed.

Use complete for three returned results or failed for no available results. All sources are simulated, and this mode never enters a model, saved-memory, approval or action path. The all-failed demo exits 1; a partial result exits 0 with explicit warnings. Read [the simple async explanation and learning exercise](docs/ASYNC_EVIDENCE.md).

## Investigate concrete evidence

A new, separate investigation mode looks for specific mechanism clues and explains why each might matter. It can suggest a routing failure from a missing route, or an authentication failure from a rejected token. Generic error pages and unavailable services are insufficient evidence. Negated or speculative clues do not become support, and conflicting observations remain visible.

```sh
.venv/bin/python agent.py --investigate examples/evidence-ranking/development.json
```

The example is synthetic. It reports a missing route and returns an unverified network-routing hypothesis, the exact supporting clue and a suggested comparison with a healthy host. It does not claim that an operating-system update caused the problem just because one happened earlier.

This mode is read-only and uses deterministic rules, not a live model. It never enters the workflow approval path, reads saved cases, writes memory or proposes an action. It always leaves the confirmed root cause empty. Without a concrete clue it says it does not have enough evidence instead of ranking a default guess. Existing workflow commands remain available separately.

The frozen synthetic challenge matches 11/12 expected behaviors; certificate expiry remains a visible miss. All 30 existing public user-impact records yield insufficient evidence in this mode. Neither number establishes general incident-diagnosis accuracy. The original baseline below is unchanged. See [the explanation and input format](docs/EVIDENCE_RANKING.md) and [the full synthetic challenge results](docs/INVESTIGATION_CHALLENGE.md).

## Public incident baseline

| Overall top-1 | Overall top-3 | Vague symptom top-1 | Correctly cautious |
| --- | --- | --- | --- |
| 10/26 (38.5%) | 11/26 (42.3%) | 3/13 (23.1%) | 4/4 (100.0%) |

These are broad cause-family scores, not exact root-cause accuracy. The four cautious cases have no single cause label and are excluded from diagnosis denominators. Fifteen symptoms use vague customer language; two of those are cautious, leaving 13 for vague diagnosis accuracy. [Every miss and its reason](docs/BASELINE.md) is reported, and [full predictions](results/baseline.json) are committed.

The 30 incidents come from 26 first-party pages. Every [source](SOURCES.md) was fetched, read and returned HTTP 200. A successful HTTP response alone was not enough: empty status pages and a report for the wrong incident were excluded or corrected. All observations are paraphrased. No log line, release version or deployment history was invented for this evaluation.

The old 12/12 claim is withdrawn. That evaluation ranked invented logs and deployment notes, despite describing itself as symptoms-only. It also treated remedies and customer impact as published root causes. It is not comparable to the new baseline.

## Install and evaluate

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python evaluation.py
```

Evaluation is offline, needs no key and executes no actions. It measures the ranking component, not the whole agent loop or a live model. It calls the existing rank_hypotheses function on the allowlisted public observations; labels and retrospective explanations never cross that boundary.

```sh
.venv/bin/python evaluation.py --check
.venv/bin/python evaluation.py --write
.venv/bin/python verify_sources.py
```

`--check` reproduces the committed report and predictions. `--write` records them. `verify_sources.py` explicitly goes online to re-fetch every citation and find its named section. It does not replace a person checking what the page says. Fetch receipts are in incidents/source_checks.json. CI runs tests and reproduces the baseline offline on Python 3.11 and 3.13.

## Try the synthetic workflow

```sh
.venv/bin/python agent.py --sample --fresh
```

The default is the deterministic practice model. It uses synthetic fixtures, including invented logs and deploy records. Historical INC-prefixed ids such as INC-CLOUDFLARE-01 are retained so existing commands and saved-state filenames still work; they do not identify real evidence. The banner explicitly labels them synthetic.

The workflow searches, reads logs, checks deployments, ranks hypotheses, drafts an update and proposes an action. Only a human typing `y` or `yes` appends one simulated line to action.log. Other answers write no action. Model approval claims are ignored. The draft is never sent.

```sh
.venv/bin/python agent.py --sample --fresh --defer-approval
.venv/bin/python agent.py --sample
.venv/bin/python agent.py --list
```

The first command saves a pending proposal without asking. The second resumes that proposal and asks for a human decision. A settled case stops with ALREADY_RESOLVED and does not duplicate its action. `--list` lists synthetic workflow fixtures, not public benchmark incidents. Public cases are loaded by incident_data.py and evaluation.py.

## Optional live model

```sh
export XAI_API_KEY='your key'
.venv/bin/python agent.py --sample --fresh --real
```

The key is read from the environment and not printed or saved. `--real` still requests `grok-build-0.1` for tool choice on the synthetic escalation. Runbook answers use `grok-4.7` unless `--xai-model` says otherwise. Ranking remains deterministic and actions remain simulated. The owner reported one live triage run on November 1, 2026, against the previous version of the sample. That is not a runbook score and not validation of these public incidents. CI uses fake clients and never calls a paid model.

## Tests

```sh
.venv/bin/python -m pytest -q
```

Tests cover tools, memory, approval, step limits, named stops, model adapters, source receipts, dataset loading, input isolation, top-k scoring and caution failures. The old tests that required a perfect 12/12 score were replaced with checks for the corrected evaluation. Existing workflow tests remain in place.

## Limits

The ranker returns three fixed titles. Only Bad deploy describes a cause family, mapped to change regression; Process needs a restart describes a remedy and Customer-facing outage describes impact. Neither earns cause credit. The top-3 score is therefore a vocabulary-coverage ceiling, not strong ranking performance. All 10 top-1 hits have no supporting evidence: the ranker keeps Bad deploy first when evidence counts tie. These are guesses, not successful investigations. No ranking rules were tuned for this set.

The ranker reads evidence observations, not the symptom text. Vague accuracy is a subset score, not a controlled test of wording. A case can earn broad family credit without identifying its specific mechanism. Sparse user observations usually cannot prove a cause.

The caution score checks multiple unverified hypotheses, valid evidence references, an explicitly empty confirmed cause and simulation-only output. It does not establish that the hypotheses are useful. Always returning unverified hypotheses can pass all four cautious cases.

This is a small selected set, weighted toward GitHub and Cloudflare. Retrospective labels come from postmortems, but the agent sees much less information. These 30 cases have now been inspected and are not a hidden test set. Before changing ranking, collect and lock a fresh set for independent testing. Do not tune the scorer or labels to make a new version look better.

The CLI runbooks are simplified synthetic prompts, not verified operational procedures. The public evaluation does not use them. The CLI remains a local simulation, not a production incident-response service.

See [how it works](docs/HOW_IT_WORKS.md) for the input boundary, label rules and next learning exercise.

For failed runs, the inspector also shows failed steps and available public error annotations. See the [real failed-run example](docs/WORKFLOW_RUN.md#try-a-real-failed-run).
