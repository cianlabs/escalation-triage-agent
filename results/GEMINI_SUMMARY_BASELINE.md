# First live Gemini summary

Both summaries used the same saved evidence from the controlled GitHub Actions
demo. The Gemini result is from one live Gemini 3.1 Flash-Lite replay before
any prompt changes. The saved workflow supplies a value locally and never
makes an HTTP request.

## Scoring

Award one point per criterion. Score each summary independently.

- Outcome. Identify that check-response failed before and passed after.
- Evidence. Identify that the simulated observed value changed from 503 to
  200 and that 200 was the expected value in both versions.
- Uncertainty. Keep the 503 in the simulated check. Avoid implying that a
  service returned it or that there is an external failure to explain.

| Summary | Outcome | Evidence | Uncertainty |
| --- | --- | --- | --- |
| Rules | 1/1 | 1/1 | 1/1 |
| Gemini, first live replay | 1/1 | 0/1 | 0/1 |

Gemini correctly reported the outcome and the two numbers. It then described
the change as modifying the simulated expectation, although the expected
value stayed fixed. It also treated the origin of the 503 as unknown,
although the workflow directly assigned it. Its general caution about
passing runs did not correct that mistake.

[Failed run](https://github.com/cianlabs/escalation-triage-agent/actions/runs/41549968399)
· [Passing run](https://github.com/cianlabs/escalation-triage-agent/actions/runs/41550790225)
· [Before workflow](https://github.com/cianlabs/escalation-triage-agent/blob/773f903cc3c5e7f56974692a541bb2210c5857be/.github/workflows/controlled-failure.yml#L13-L15)
· [After workflow](https://github.com/cianlabs/escalation-triage-agent/blob/53891d56d79cc5511565a90f43394bad5fc04251/.github/workflows/controlled-failure.yml#L13-L15)

## Next cases

These are unscored evaluation scenarios. Capture the evidence and apply the
rubric before changing the prompt. Give both summaries the same snapshot.

| Case | Outcome to report | Evidence to report | Uncertainty to preserve |
| --- | --- | --- | --- |
| Same workflow, different runner | Job failed, then passed | The workflow stayed the same and the reported runner image changed | The runner change is a clue. The evidence does not establish that it caused the recovery. |
| Retry after a dependency download timeout | Job failed, then passed | The failed job reported a timeout. The passing job completed the download. | The evidence does not identify which side of the connection caused the timeout. |
| Workflow edit and application edit in one commit | Job failed, then passed | A workflow line changed and the commit also touched application code, if both facts are in the supplied evidence | The passing run alone does not isolate the change that mattered. |

The first comparison covers one controlled demo and one live model response.
It does not measure performance on fresh public run pairs.
