# escalation-triage-agent

A practice support agent that searches local runbooks, reads synthetic evidence, ranks hypotheses, drafts an update and asks a human before recording a simulated action. It saves each case so an investigation can resume later. Nothing restarts, rolls back, pages anyone or sends a message.

The public incident evaluation is separate from those synthetic workflow fixtures. It uses verified user-impact observations from 30 distinct incidents and calls this repository's unchanged ranking tool.

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

The key is read from the environment and not printed or saved. This uses the live model to choose tools on the same synthetic fixtures; ranking remains deterministic and actions remain simulated. The owner reported one live run on November 1, 2026, against the previous version of the sample. That is not validation of these public incidents. CI uses fake clients and never calls a paid model.

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
