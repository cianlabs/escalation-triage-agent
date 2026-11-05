# Project notes

Working notes for the approximately 48-hour session spanning November 1–3,
2026. These notes summarize the work recorded in this chat. The dates are
a session window, and the results below are individual experiments.

Repository: cianlabs/escalation-triage-agent

## What we built

### Public GitHub Actions investigation

- Added public GitHub status collection and relevance to a reported problem.
- Added read-only inspection of a specific Actions run and its reported attempt.
- Collected job outcomes, failed steps, and public check annotations.
- Matched annotations to the job and run before displaying them.
- Kept error messages, warnings, and notices distinct.
- Added a next check pointing to the reported failed step.
- Compared two runs from the same repository and highlighted changed job outcomes.
- Compared workflow files at the exact run commits for supported push runs.
- Added a short rule-based triage summary with source evidence below it.
- Reported missing or inconsistent evidence and GitHub access failures.
- Added rate-limit reset times or retry delays when GitHub provided usable headers.
- Added saved-evidence replay to make demonstrations independent of GitHub access.

All investigation actions remained read-only. The reports left confirmed
root cause empty and supplied evidence for human review.

### Controlled before-and-after demo

We created a branch-only GitHub Actions workflow that compared two local
values. It initially set expected=200 and observed=503, then exited with
an error annotation. The user changed observed to 200, and the next run passed.

No HTTP request was made by this check. The 503 was assigned by the script.
This distinction became an important evaluation case for model summaries.

- Failed run: https://github.com/cianlabs/escalation-triage-agent/actions/runs/41549968399
- Passing run: https://github.com/cianlabs/escalation-triage-agent/actions/runs/41550790225
- Demo branch: demo/controlled-http-failure

The comparison showed the failed step, the reported mismatch, the passing
outcome, and the exact observed=503 to observed=200 edit.

### Model summaries and provider experiments

- Added an opt-in model summary beside the default rule-based report.
- Added xAI, OpenAI, and Gemini options for workflow comparison summaries.
- Added safe provider error diagnostics.
- Switched the xAI comparison summary to the Responses API.
- Added a saved comparison replay that could call a real model.
- Added one retry after one second for Gemini HTTP 503 responses.
- Preserved the rule-based report when the model was unavailable.
- Used 1Password CLI references to supply API keys at command runtime.

Provider behavior observed during this work:

| Provider | Observation |
| --- | --- |
| xAI | Returned HTTP 400, including a direct model-listing request. The exact cause remained unknown. |
| OpenAI | Returned HTTP 429. Available API quota or billing was not confirmed. |
| Gemini | Produced usable summaries earlier, then repeatedly returned HTTP 503. A tiny native Google API request also returned 503. |
| Ollama | Ran local Qwen 2.5 3B and 7B and EmbeddingGemma successfully. Answer quality varied substantially. |

The user plans to wait for xAI usage to reset and then test Grok again.
A usage reset resolving the earlier HTTP 400 has not been verified.

### Real public CI cases

We verified two failed/passing pairs from Qwen Code. The workflow files
were unchanged within each pair.

- Artifact download ETIMEDOUT, macOS shard 1/2.
  Failed 37119220504, passed 37142411422.
- Artifact download ENOTFOUND, macOS shard 2/2.
  Failed 35250857883, passed 35352276389.

The evidence identified the failed operation and reported error. It did
not establish the underlying cause of either download failure.

The original Gemini prompt scored 3/3 on the first Qwen pair, compared
with 2/3 for the rules. The rules omitted the timeout from the short
summary while retaining it in the details. Gemini scored 1/3 on the
controlled demo because it misread the simulated value. Updated-prompt
cloud attempts later returned 503 and remained unscored.

## Runbook assistant

### Initial search and cited answers

We selected five existing guides covering customer outages, database
connection pools, Redis memory, rollback, and dashboard performance.

- Wrote ten development questions and expected sources before implementation.
- Added lexical search returning up to three excerpts with line citations.
- Weighted rarer terms more heavily and filtered weak alternatives.
- Added an extractive answer mode for diagnostic checks.
- Expanded it to approval and action questions while preserving human approval.
- Added handling for paging, sign-off language, and cycling Redis nodes.
- Added abstention for unsupported requests such as log storage paths.

| Evaluation stage | Top-three retrieval | Complete cited answers | Unsupported-question abstention |
| --- | --- | --- | --- |
| Initial lexical search | 8/8 | Unscored | 1/2 |
| Initial diagnostic answers | 8/8 | 1/8 | 2/2 |
| Log questions and conditional checks | 8/8 | 3/8 | 2/2 |
| Action and approval rules | 8/8 | 8/8 | 2/2 |
| First fresh questions | 8/8 | 5/8 | 1/2 |
| After fixing those four misses | 8/8 | 8/8 | 2/2 |
| New frozen holdout | 8/8 | 6/8 | 1/2 |

The sets used to guide fixes became regression cases. Their improved
scores did not establish generalization to new wording.

### Model answers

Added optional Gemini and local Ollama answers using the same retrieved
lines. Model citations must refer to supplied evidence IDs.

A valid citation ID alone did not establish that the line supported the
generated claim. The local model sometimes repeated a citation as its
answer, cited the wrong line, invented checks, or claimed supplied
information was missing.

Changes and experiments included:

- Rejecting citation-only responses.
- Explicitly separating answer text from citation IDs.
- Asking the model to identify the exact requested detail.
- Rendering missing details before related guidance.
- Constraining Ollama output with a JSON schema and allowed citation IDs.
- Removing a queue-depth prompt example after the model copied it into unrelated answers.

The local 3B model handled the approval-form regression after a prompt
change. It stated that the Redis guide requires approval but gives no form.
Broader supported-answer performance remained weak.

## Semantic retrieval

Created a separate corpus of 15 practice guides, including snapshots of
the original five and ten synthetic guides written for the experiment.
Questions and expected guide IDs were committed before scoring.

Used local EmbeddingGemma with cosine similarity. The 0.3 cutoff was
explored on development questions and then held fixed for a new holdout.

| Development measure | Keyword | Embeddings | Embeddings with 0.3 cutoff |
| --- | --- | --- | --- |
| Expected guide in top three | 12/15 | 15/15 | 15/15 |
| Extra results | 11 | 30 | 12 |

| Fresh holdout measure | Keyword | Embeddings | Embeddings with 0.3 cutoff |
| --- | --- | --- | --- |
| Expected guide in top three | 6/8 | 8/8 | 8/8 |
| Extra results across all questions | 16 | 28 | 7 |
| Unsupported questions returning no results | 1/4 | 0/4 | 1/4 |

Extra results count returned guides beyond the expected guide. All returned
guides count as extra for questions marked unsupported. Some extras are
topically related. A similarity score does not establish that a passage
contains the requested command, number, address, date, or file path.

Connected semantic retrieval to optional local model answers and moved
the corpus into individual text files so citations refer to real lines.

## Answer reliability experiments

The following scores use different sets or runs. Compare within each row
or experiment, rather than treating them as one continuous accuracy metric.

| Experiment | Result |
| --- | --- |
| First semantic answer pipeline | 8/8 retrieval, 1/8 complete supported answers, 2/4 unsupported questions handled, 7/11 model responses rejected. |
| Schema plus removal of copied prompt example | 3/8 complete supported answers, 3/4 unsupported questions handled, 1/11 response rejected. |
| Timed Qwen 3B comparison run | 4/8 complete supported answers, 3/4 unsupported questions handled. |
| Timed Qwen 7B comparison run | 0/8 complete supported answers, 4/4 unsupported questions handled. |
| Original prompt on eight new questions | 3/6 complete supported answers, 2/2 missing details handled. |
| Candidate prompt on the same questions | 1/6 complete supported answers, 2/2 missing details handled. Candidate rejected as the default. |
| Whole-set evidence selection | Required lines covered on 3/6 supported questions, abstention on 2/2 unsupported questions. |
| Independent line labels | Required lines covered on 1/6 regression questions and 0/2 fresh supported questions; abstention on all four unsupported questions. |

Whole-set selection asks for line IDs and displays their text verbatim.
Independent labeling asks the model to classify each line as supports,
context, or irrelevant. That smaller-decision experiment performed worse.

Single-run local model outputs varied. The larger model was not reliably
better. The first timed 3B request overlapped a model download, so timing
results do not establish a speed advantage.

## Current conclusions

- Retrieval is stronger than answer generation on these small corpora.
- Semantic retrieval finds guides for paraphrases keyword search misses.
- Filtering reduces extra results but cannot verify answerability.
- A model can produce valid JSON and valid citation IDs while making an unsupported claim.
- Verbatim excerpts prevent generated wording and citation mismatches, but selecting the right excerpts is still difficult for the tested model.
- Strong abstention scores must be read alongside supported-answer coverage.
- Failed experiments were recorded rather than presented as improvements.
- Cloud model availability failures were recorded separately from answer quality.
- Synthetic guides and repeated development questions limit what these results establish.

## Where the work is recorded

- results/WORKFLOW_COMPARISON_EVALUATION.md
- results/GEMINI_SUMMARY_BASELINE.md
- results/RUNBOOK_RETRIEVAL_PLAN.md
- results/RUNBOOK_FRESH_EVALUATION.md
- results/RUNBOOK_HOLDOUT.md
- results/SEMANTIC_RETRIEVAL.md
- results/SEMANTIC_HOLDOUT.md
- results/SEMANTIC_ANSWERS.md
- results/QWEN_MODEL_COMPARISON.md
- results/ANSWER_DESIGN_EXPERIMENT.md
- results/EVIDENCE_SELECTION.md
- results/LINE_LABEL_EXPERIMENT.md

Relevant later PRs include #45–#46 for retrieval, #47–#48 for the full
semantic answer path, #50–#51 for model and prompt comparisons, and
#52–#53 for evidence selection experiments. Merge status should be
checked on GitHub. PR #53 was prepared at the end of these experiments.

The latest recorded full local test run passed 438 tests.

## Resume plan

1. Wait for the user's xAI usage reset.
2. Run a tiny Grok request with the intended key to confirm access.
3. If it fails, diagnose that request before running the full evaluation.
4. Once a cloud model responds, freeze a precise task, retrieved passages,
   prompt and scoring rubric.
5. Compare the cloud model with the existing local model and a baseline
   that simply displays retrieved source text.
6. Report complete answers, citation support, missing-detail handling,
   availability, latency and cost separately.
7. Use fresh questions for the final test and keep the earlier sets for regression checks.

The user requested this notes file after deciding to wait for Grok.
No new model run was required to write these notes.

## November 5 update

### Repeatable evaluation

PR #54 added saved-run reports, review templates tied to the exact
responses and question set, and capture provenance for future runs.
The completed 7B review was preserved in PR #55.

| Reviewed saved run | Complete answers | Grounded responses | Missing details handled |
| --- | --- | --- | --- |
| Qwen 3B | 4/8 | 7/11 usable responses | 3/3 reviewed, with one failed case unscored |
| Qwen 7B | 0/8 | 6/12 | 4/4 |

The 3B run had 11/12 usable responses. The 7B run had 12/12. The reviewer
judgments were proposed by the assistant with case-level reasons for
human review. They are not an independent benchmark.

### Cloud diagnostics

The user tested a new Google key through 1Password. AI Studio returned
OK with Gemini 3.8 Flash. A model metadata lookup returned HTTP 200,
and one tiny native generation request also returned HTTP 200 using
the terminal's normal HTTP configuration.

Later tests returned HTTP 503, including native requests with and without
JSON mode. Full runbook answers also failed after a retry. This did not
establish JSON mode, the compatibility endpoint, or free-tier access as
the cause. Cloud answer quality remains unscored for those failed calls.

PR #56 prepared native Gemini generation with status-only error handling.
PR #57 added explicit OpenAI model selection for runbook answers. The live
OpenAI attempt returned HTTP 429. The user's API billing screen showed
a zero-dollar credit balance, and the user chose to wait for xAI usage
to reset instead of buying API credits.

### Local browser interface

PR #58 added Runbook desk, served locally by python runbook_ui.py at
http://127.0.0.1:8765. PR #59 corrected the status shown when a model
returns an unusable response.

The page supports keyword search over five guides, semantic search over
15 practice guides, visible source lines, clickable citation highlighting,
the existing rule-based answer, and an optional local Qwen comparison.
The user verified supported dashboard guidance and abstention on a missing
pooler-log location. A local model reply failed answer or citation validation;
the rules and retrieved passages stayed visible.

The local interface's full test suite passed 450 tests, and CI passed.
It runs without cloud API keys. Semantic search and model comparisons
require their local Ollama models.

### Demo wrap-up

The walkthrough uses a supported dashboard question, a question asking
for an absent pooler-log path, and a live local-model comparison.
The visual walkthrough is assembled from captured browser screenshots.
It is a sequence of observed UI states, and does not show continuous
screen activity.

Next, confirm a tiny Grok request after xAI usage resets. If access works,
capture the same T01–T12 question set. The runner, CLI and local page now
have that Grok path. No live call was made here, and no answer-quality
score was added. Cloud failures remain availability results and receive
no answer-quality score.

### Grok HTTP 410

A paid-key smoke run of the Redis approval-form question printed the
rule-based fallback and then `MODEL_ERROR` with `APIStatusError` and HTTP
410. The Responses call was sending `search_parameters` with `mode` set to
`off`. xAI's OpenAPI schema for `POST /v1/responses` says live search has
been removed and that requests which set `search_parameters` fail with
HTTP 410 Gone. The field is omitted now. `web_search` and `x_search` are
also omitted, and `tool_choice` stays `none`, so search stays off without
the removed field. No live xAI call was made for this change.

### Grok HTTP 400

The same smoke command, after that change, printed the rule-based fallback
and then `MODEL_ERROR` with `BadRequestError`, HTTP 400, and provider code
unavailable. The Responses call was still sending `max_tool_calls` set to
0. The current `ModelRequest` schema does not list that field. `max_turns`
is the agentic-turn field, and this path does not send it. `tool_choice`
`none`, temperature 0, and `reasoning.effort` `low` are in the schema; the
reasoning guide lists `low` for grok-4.7. `max_tool_calls` is omitted now.
A rejected call includes the provider message from the error body when one
is present, with key text removed. The raw exception text stays hidden.
No live xAI call was made for this change.
