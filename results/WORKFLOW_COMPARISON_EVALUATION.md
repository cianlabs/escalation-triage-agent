# Workflow comparison evaluation

The agent compares GitHub Actions runs, links job outcomes and failure
annotations to their sources, and shows changes between the workflow files
at the run commits. It prints a rule-based summary by default. A saved
comparison can also be sent to Gemini without fetching GitHub again.

## Summary quality

Each case awards one point for the outcome, one for using the relevant
evidence accurately, and one for handling uncertainty appropriately.
The rubric is applied to the short summary. Evidence that appears only
in the detailed report does not earn the evidence point.

| Case | Rules | Gemini, original prompt | Gemini, updated prompt |
| --- | --- | --- | --- |
| Controlled HTTP check | 3/3 | 1/3 | Unscored. HTTP 503. |
| Qwen Code artifact download timeout | 2/3 | 3/3 | Unscored. HTTP 503 after retry. |
| Fresh Qwen Code artifact download error | 2/3 | Untested | Unscored. HTTP 503 after retry. |

- **Controlled check.** The rules correctly described the script assigning
  503 before and 200 after, with the expected value fixed at 200. Gemini
  reported the recovery but treated the simulated value as an HTTP
  response whose origin needed explaining. [Failed run](https://github.com/cianlabs/escalation-triage-agent/actions/runs/41549968399) · [Passing run](https://github.com/cianlabs/escalation-triage-agent/actions/runs/41550790225)
- **Qwen timeout.** Gemini named the reported artifact download timeout
  and left its underlying cause open. The rules showed the timeout
  only in the detailed report. [Failed run](https://github.com/QwenLM/qwen-code/actions/runs/37119220504) · [Passing run](https://github.com/QwenLM/qwen-code/actions/runs/37142411422)
- **Fresh Qwen case.** The macOS shard failed during artifact download
  with ENOTFOUND and passed later with the same workflow file. The rules
  reported the recovery and left the cause open, but omitted ENOTFOUND
  from the summary. [Failed run](https://github.com/QwenLM/qwen-code/actions/runs/35250857883) · [Passing run](https://github.com/QwenLM/qwen-code/actions/runs/35352276389)

## Model availability

The fresh comparison completed and printed the rule-based report.
Gemini returned HTTP 503 on the initial call and on the automatic retry.
The CLI reported model unavailability and kept the rule-based report
visible. The saved Qwen timeout replay showed the same behavior.

## Limits

This evaluation covers one controlled workflow and two public pairs from
the same repository. The first two cases guided the prompt change, and
the fresh pair was selected afterward. The updated prompt returned no
summaries on the recorded attempts, so its effect on quality is unknown.
See the [original scoring notes](GEMINI_SUMMARY_BASELINE.md) for the
case-level rubric and replay commands.

To show the controlled case from the repository with saved evidence:

```sh
python agent.py --replay-comparison demo
```
