# Connecting clues to possible causes

A customer says the dashboard stopped working. That tells us what hurts. It does not tell us why. The new investigation mode needs a concrete clue before it names a mechanism.

The synthetic example contains a network check reporting a missing route. A route tells computers where to send traffic. If it is missing, they may not be able to talk. The program therefore suggests Network routing failure, cites the route-check observation and asks for a comparison with a working host. It still does not know why the route disappeared. An update happening earlier does not prove it caused the failure.

## Try it

```sh
python agent.py --investigate examples/evidence-ranking/development.json
```

The input file is a JSON object with a nonempty symptom and a list named evidence. Each evidence row needs a unique id, a source and an observation. The checked-in example is synthetic. An empty evidence list is valid and produces an explicit insufficient-evidence answer. Malformed JSON or invalid rows produce a named error.

The symptom is displayed for context. Only observation text drives the rules. File names, source names, ids, retrospective causes and other extra fields do not become causal clues. The output reproduces the supplied observations with its supporting references so a person can check the explanation.

## What it recognizes

Specific clues can suggest memory exhaustion, missing network routes, token rejection, denied storage access, device I/O failure, a database connection limit or a deployment regression. Mere words such as memory, restart, unavailable or HTTP 500 do not select those causes. A deployment alone does not imply a regression; the observation must describe a failure following the change or recovery after rollback. Even that relationship needs independent verification.

These are possible mechanisms, not necessarily the initiating root cause. Memory exhaustion does not establish why memory ran out, and a missing route does not identify which change removed it.

The output has four possible assessments:

| Assessment | Meaning |
| --- | --- |
| insufficient_evidence | No recognized mechanism has a specific supporting clue. Ask for diagnostic evidence. |
| supported_hypothesis | One recognized mechanism has support. Check it independently. |
| competing_hypotheses | Several mechanisms have support. Do not treat list order as proof. |
| conflicting_evidence | A proposed mechanism has both supporting and contradicting observations. Reconcile them. |

Negative observations are attached as counterevidence, not silently discarded. Explicit guesses and instruction-like statements are not treated as observed facts. Each hypothesis remains unverified, each has a missing-evidence note and a next check, and confirmed_root_cause is always empty. This prototype cannot confirm a root cause.

Ordering is deterministic: contradicted hypotheses go after uncontested ones, then evidence-row count and a stable family name break ties. Those counts are not probabilities or independent corroboration; several rows may come from the same underlying source. Multiple supported mechanisms remain competing even when one has more rows.

## Action boundary

The investigation path returns before agent.run_escalation, any model client, saved-state access or approval logic is entered. It cannot propose a restart, rollback or page. Its stop reason is INVESTIGATION_REQUIRED, which means a person should investigate the suggested checks. Suggestions are text and are never executed.

Combining --investigate with --real, --sample, a fixture id, --fresh, --list or --defer-approval is rejected. The older synthetic workflow and its approval tests remain unchanged. No mode switch loads or approves a waiting action.

## How it was checked

The 12 synthetic challenge cases were frozen in commit 700503d before the ranker implementation. A SHA-256 lock detects changes. They include vague failures, specific diagnostic clues, denial, contradictory observations and simultaneous mechanisms. They are authored controlled examples, not hidden or real-world test incidents.

The first implementation matches 11/12. It misses certificate expiry and abstains. The miss remains in the report. No certificate rule was added to make that challenge look perfect. Separate unit tests cover validation, negation scope, speculative text, evidence references, unrecognized impact, CLI errors and the model/memory/action boundary.

```sh
python investigation_eval.py
python investigation_eval.py --check
python evaluation.py --check
python -m pytest -q
```

The existing 30-case public baseline and its score rules are unchanged. A behavior audit runs the new mode on the same exposed user-impact observations: it abstains on all 30 because it finds no recognized diagnostic mechanisms. That is appropriate restraint on those inputs, not proof of correct real-world diagnosis. The old cause-family scores must not be compared with 11/12 on a different synthetic task.

## Limits and next evidence

This remains a small rule-based prototype. It is not general language understanding or causal reasoning by a trained model. It misses unfamiliar wording and unsupported mechanisms. Negation and speculation handling is limited; quoted, historical, conditional, wrong-host or wrong-time statements can still be misclassified. Evidence origin, scope and accuracy need human review. Counterevidence can be incomplete, and absence of a recognized signal does not rule a mechanism out.

Before claiming a diagnosis improvement on real incidents, obtain fresh, independently reviewed diagnostic evidence, define the expected uncertainty behavior and lock the test protocol before further changes. Public postmortem explanations must remain separate from inputs. Do not manufacture logs or copy a known cause into evidence to obtain a passing score.

A useful learning exercise is to run the synthetic example, then replace its evidence with only a generic customer error. Predict the answer before running it. Next add a contradictory route observation and explain why a supported hypothesis should no longer be treated as a single uncontested possibility.
