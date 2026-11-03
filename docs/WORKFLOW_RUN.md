# Inspect one public workflow run

```sh
python agent.py --workflow-run https://github.com/cianlabs/escalation-triage-agent/actions/runs/41376006131
```

Replace the URL with a public GitHub Actions run page. The program reads that specific run and its jobs. It does not use the provider's overall status to explain an individual run, and it does not use practice clues. The URL must be a normal HTTPS github.com run URL, without query strings, fragments, credentials, job suffixes or attempt suffixes. Private repositories and authenticated requests are not supported.

Think of looking at a parcel tracker. It can tell you that a parcel is waiting, moving or delivered. A waiting label alone does not explain why it is waiting. The same distinction applies to workflow status.

## What is reported

The output shows the run URL, collection start time, run creation and update times, reported attempt, each job's status and conclusion, detail-source URLs and any reported deployment gates. Run creation time is not presented as time spent in a queue. The program does not decide that a queued run is stuck based on its age.

- A queued, pending, requested, waiting or in-progress run keeps its reported state. Waiting alone does not prove that a person needs to approve it.
- A pending deployment with required reviewers is reported as pending deployment review. It may be one blocker, not the reason every job is waiting.
- A pending deployment without reported required reviewers is reported as protection, which can involve a timer or another rule. The configured timer is not a calculated remaining wait.
- A completed run shows its actual conclusion: success, failure, cancelled, timed out or another recognized GitHub outcome. Failure is an outcome, not a diagnosis.
- Missing, inaccessible, malformed or unrecognized information remains unknown. No default healthy state is invented.

The suggested next step is to open that run and inspect the relevant job or gate. This command downloads no logs and executes no suggestions. It does not approve, rerun, cancel, restart or change anything, and it leaves confirmed root cause empty.

## Avoiding mixed attempts and stale snapshots

The first request identifies the current run attempt. Jobs are fetched from the endpoint for that exact attempt, rather than mixing jobs from earlier retries. Job ids must be unique and belong to the requested run. Returned attempt ids, when present, must match.

Jobs are paginated with 100 per page, up to five pages. A limit, missing page, duplicate job or inconsistent response is explicitly incomplete. Remaining jobs are unknown. The program constructs its own fixed-host page requests and never follows response links or redirects to other destinations.

For unfinished runs, job and pending-deployment requests start concurrently. Completed runs skip the pending-gates request rather than guessing there is a current approval wait. After details arrive, the run is fetched again. If its attempt, state, conclusion or update timestamp changed, the output says snapshot uncertain. If the recheck fails, consistency is unknown. This catches detectable changes; the API requests are not an atomic snapshot and cannot establish that nothing changed between them.

A complete collection exits 0 even when the workflow itself failed. Unknown, partial or uncertain collection exits 1. Invalid mode combinations exit 2. Exit codes describe collection completeness, not whether a workflow succeeded.

## Read-only request boundary

The input URL is validated before network access. Requests are constructed only under api.github.com for that owner, repository and run id. A fresh async HTTP client sends only GET, with no token, account cookies or request body. It ignores environment proxies, uses normal certificate verification, follows no redirects and performs no automatic retries. No model is called, and no saved case or waiting action is loaded.

Each HTTP request has a four-second transport timeout and a five-second total request deadline. The optional detail requests use the same bounded readers. HTTP 403 or 404 does not establish that the run is missing: it may be private, inaccessible or rate-limited. Response and exception bodies are not printed. A public repository identity, positive run id and attempt, consistent status and conclusion, and timezone-aware timestamps must be verified before run details are accepted.

See GitHub's [workflow run documentation](https://docs.github.com/en/rest/actions/workflow-runs#get-a-workflow-run), [job documentation](https://docs.github.com/en/rest/actions/workflow-jobs) and [pending deployment documentation](https://docs.github.com/en/rest/actions/workflow-runs#get-pending-deployments-for-a-workflow-run).

## Validation and limits

A manual public-run read succeeded on November 1, 2026, Pacific time and reported two completed successful test jobs. Tests remain offline with MockTransport. They cover run states and conclusions, required-review versus other protection, missing gate access, pagination and its cap, malformed data, cross-run and cross-attempt records, races and failed rechecks, URL validation, request restrictions, and CLI isolation from models, memory and actions. Existing ranking reports reproduce unchanged.

This does not fetch logs, inspect workflow configuration, verify available runners, identify a failing command, or establish a root cause. Queues can involve capacity or concurrency, and approvals can involve other mechanisms not visible through pending deployments. The output must remain uncertain about those reasons.

## Learning exercise

Choose a public run URL and locate the run state, job states and attempt number in the output. Explain why a completed failure is different from an unknown API response. Then find the second run request in inspect_run and explain how it helps avoid combining a new retry with old job details.

## Try a real failed run

```sh
python agent.py --workflow-run https://github.com/cli/cli/actions/runs/41072491583
```

For failed jobs, the inspector shows failed steps when GitHub supplies them. It also shows public check annotations after matching the check to the job and run. Errors, warnings, and notices are labeled separately. If some details are unavailable, the report preserves the known run outcome and marks collection incomplete.

In this example, the failed step is Run Dependabot. A public annotation reports an updater error. The detailed log requires repository write access, so the underlying cause stays unconfirmed. The inspector reads public metadata only.

## Compare two runs

Pass the earlier run first and the later run second. Both must be distinct
public run URLs from the same repository.

```sh
python agent.py --compare-runs https://github.com/cianlabs/escalation-triage-agent/actions/runs/41549968399 https://github.com/cianlabs/escalation-triage-agent/actions/runs/41550790225
```

The demo shows `check-response` changing from failure to success and includes
the earlier run's reported mismatch. Jobs are paired by exact name when it is
unique in both runs. The command reads public run evidence and leaves the
cause unconfirmed. For push runs with the same workflow path, it shows a bounded diff of the files at the two run commits. If either file is unavailable, the run evidence is still shown. A file diff alone does not verify a fix.

The triage summary highlights jobs that failed before and passed after. For
the simulated HTTP demo, it connects the reported mismatch to the matching
assignment change. When the evidence does not line up, it reports the outcome
change and leaves the explanation open.

If GitHub blocks a run, job list, deployment gate or run recheck, the
comparison puts access guidance near the top. It shows a retry delay or
UTC reset time when GitHub provides usable rate-limit headers. A bare
HTTP 403 leaves the reason unknown. The report still marks affected
collection incomplete.

To replay the comparison without GitHub access, run
`python -m pytest -q tests/test_workflow_comparison_cli.py`.
The tests run the CLI with simulated API responses for a matching workflow
edit, an unchanged file, and a rate-limited job request.

### Comparison summary baseline

Run `python -m pytest -qs tests/test_workflow_comparison_cli.py -k baseline`
to print the scores. Outcome checks whether the report shows the job moving
from failure to success. Explanation checks the summary against wording set
before replaying each case.

| Simulated case | Outcome | Explanation |
| --- | --- | --- |
| Edit matches the reported mismatch | 1/1 | 1/1 |
| Only a comment changes | 1/1 | 1/1 |
| Timeout and dependency version both change | 1/1 | 1/1 |
| Total | 3/3 | 3/3 |

These three examples use the same simulated job. They measure how the
current summary handles these examples and leave performance on other
workflows open.

### Harder summary cases

Run `python -m pytest -qs tests/test_workflow_comparison_cli.py -k harder`
to replay these three simulated cases with the existing summary rules.
Explanation scoring checks the summary against the expected wording,
including whether it calls out missing evidence.

| Case | Outcome | Explanation | What the summary missed |
| --- | --- | --- | --- |
| Two jobs recover | 1/1 | 0/1 | It grouped the jobs and omitted the matching evidence for check-response. |
| Matching numbers in a comment | 1/1 | 1/1 | It left the explanation open. |
| Workflow file unavailable | 1/1 | 0/1 | The report flagged the missing file below the summary, which gave only a generic explanation. |
| Total | 3/3 | 1/3 | |

These cases use simulated GitHub responses. The scores apply to these
examples and their expected wording.

With the per-job summary, the same three cases score 3/3 for outcomes
and 3/3 for explanations, up from 1/3 for explanations in the baseline
above. The summary separates recovered jobs and calls out an unavailable
workflow comparison. The comment-only case still leaves the cause open.
These are the cases used to guide the change.

### Try a model-written summary

Add `--model-summary` to the comparison command with `XAI_API_KEY` already
set in your terminal. This opt-in sends bounded public job details,
annotations and workflow differences to the same xAI model used by the
practice agent's real mode. It prints a separate experimental summary
after the rule-based report. The model call has no tools and may incur
API charges. The source links identify evidence the model cited. They
do not verify that its claims follow from that evidence.

### Replay the demo without GitHub

Run `python agent.py --replay-comparison` to use a saved snapshot of the
public demo evidence, with unrelated notices omitted. Add `--model-summary` with `XAI_API_KEY` set to send
that snapshot to xAI. Replay makes no GitHub requests. Without the model
flag, it runs offline.

To use OpenAI for the saved demo, set `OPENAI_API_KEY` in your terminal and run:

```sh
python agent.py --replay-comparison --model-summary --summary-provider openai
```

This sends the same saved public evidence to GPT-5.6 Terra via the Responses
API. The provider defaults to xAI when the option is omitted.
