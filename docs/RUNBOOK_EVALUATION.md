# Repeatable runbook evaluation

Use one command to report on saved answers without a model or network call:

```sh
python runbook_model_eval.py --replay results/qwen3b-comparison-responses.json --reviews results/qwen3b-comparison-reviews.json
```

This reports the recorded model, response availability, citation ID checks,
reviewed completeness, claim support, missing-detail handling and command time.
The report includes the question, saved answer and reviewer reason for each case.
The reviewed 3B example has 4/8 complete answers, 7/11 grounded usable responses,
and 3/3 reviewed missing-detail cases, with one failed case left unscored.
Availability is 11/12. The failure remains visible in that denominator.

## Review another saved run

```sh
python runbook_model_eval.py --replay results/qwen7b-comparison-responses.json --review-template /tmp/qwen7b-reviews.json --output /tmp/qwen7b-report.md
```

Read the report and source passages, then edit the template. Use true, false
or null for complete, grounded and missing_detail. Add a reason for the
judgment. Null means pending. Complete applies to supported questions.
Missing_detail applies to unsupported questions. Grounded checks the whole
answer, including contradictions in its missing-information statements.
An answer that explicitly withholds all unsupported details and makes no
unsupported claims may pass grounded even when it contains no citation.

```sh
python runbook_model_eval.py --replay results/qwen7b-comparison-responses.json --reviews /tmp/qwen7b-reviews.json --output /tmp/qwen7b-reviewed.md
```

The template is tied to the saved run and question set by hashes. Changed
answers require a new review file. Generating a template never replaces an
existing file.

## Capture a local run

```sh
python runbook_model_eval.py --model qwen2.5:3b --output /tmp/new-run.json
python runbook_model_eval.py --replay /tmp/new-run.json --review-template /tmp/new-reviews.json
```

New captures checkpoint after every question using an atomic file replacement.
They record the model tag, available local model digest, prompt hash, answer
code hash, corpus hash, question-set hash, embedding model and cutoff.
The finished capture also prints a report with quality scores pending review.
Use --questions to select another fixed question file for capture and replay.

Older saved result lists are supported. Their missing provenance stays unknown.
Citation checks verify that IDs exist in the current fixed corpus. Human review
must establish whether those lines support the claims. Review old snapshots
against their recorded evidence before deciding whether a citation is valid.

A successful process exit with output is counted as usable and is not an
automatic correctness score. Failed and absent responses remain unscored for
quality. Every quality summary shows its reviewed denominator and pending count.
API cost is unrecorded. Capture currently supports local Ollama runs; replay
works with the existing saved local runs. A cloud capture adapter can use the
same versioned results format when xAI access is available.

## Reviewed 7B baseline

The saved Qwen 7B answers now have proposed reviewer judgments and reasons
in results/qwen7b-comparison-reviews.json. Reproduce the report with:

```sh
python runbook_model_eval.py --replay results/qwen7b-comparison-responses.json --reviews results/qwen7b-comparison-reviews.json
```

All twelve responses were usable. Completeness scored 0/8, whole-response
grounding scored 6/12, and missing-detail handling scored 4/4. T02 and T04
made true statements about absent specifics but still omitted the available
diagnostic guidance. This distinction explains why a response may pass
grounding and fail completeness.

These judgments were proposed by the assistant and are supplied for
human review. They include evaluation of the complete response, including
claims that evidence is missing and omitted approval requirements.

Use this saved baseline for the planned Grok comparison after xAI access
resets. First confirm a tiny request succeeds, then capture cloud responses
using a fixed question set, retrieval evidence, prompt and scoring rubric.
No new Grok answer or quality score is recorded here.

## OpenAI runbook trial

Set OPENAI_API_KEY in the terminal, then select an OpenAI model explicitly:

```sh
python runbook_search.py --model-answer --openai-model gpt-6-luna 'What approval form must I file before I restart Redis?'
```

Add --semantic to use the same 15-guide semantic corpus as the local
model experiments. This requires the local embedding server.
The default five-guide lexical search can run the first cloud trial
without that dependency.

The OpenAI option uses the Responses API with store=false, the same
answer prompt and citation validator. It prints a labeled rule-based
fallback on provider errors. The live OpenAI result still needs verification.
