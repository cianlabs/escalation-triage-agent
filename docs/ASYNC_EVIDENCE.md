# Three checks at the same time

Imagine three helpers checking different rooms. One looks at recent errors, one at recent changes and one at service health. They start together. If one helper gets stuck, the others still return what they found. A missing answer is marked unknown, never healthy.

## Try the simulated examples

```sh
python agent.py --collect-sample complete
python agent.py --collect-sample partial
python agent.py --collect-sample failed
```

Every source is synthetic. No service, log system, deployment system or model is contacted. Small async waits stand in for waiting on an outside service.

- complete: all three checks return observations. The service-health observation says the endpoint is unavailable; a successful check is not a healthy service.
- partial: the errors check returns a missing-route clue, the changes check fails and the health check times out. The clue survives, and the investigation names both unavailable checks.
- failed: errors and changes fail, and health times out. The investigation has no evidence and says it cannot name a likely cause.

Complete and partial demos exit with code 0 after printing the result. The all-failed demo exits 1. Invalid command combinations exit 2. A partial result always includes an incomplete-evidence warning even though the command completed. No demo proposes or performs an action, writes memory, loads a waiting approval or calls the workflow model.

## What async and await mean here

An async function can pause while it waits. await hands control back so another check can make progress. Three checks therefore do not have to wait in a line. This helps with waiting on input and output; it does not make CPU-heavy Python work run in parallel.

EvidenceCheck gives each reader a source name and its own timeout. collect_evidence starts all readers inside an asyncio.TaskGroup. Each reader is wrapped in asyncio.wait_for, so a slow source gets its own deadline. A failed reader returns a failure record instead of discarding other results. If the caller cancels collection, the group cancels and drains its children. If a source cancels itself, that source is marked cancelled and the other sources can still complete.

Timeouts require cooperative async readers. Blocking code can freeze the event loop, and a reader that ignores cancellation can delay shutdown beyond its deadline. The included readers await their waits and support cancellation. This is not a hard limit for arbitrary code.

## Source outcomes

| Status | Meaning |
| --- | --- |
| ok | The check returned valid observations. Those observations may describe an unhealthy service. |
| empty | The check completed without observations. This does not establish health. |
| failed | The check raised an error. No result is available. |
| timeout | The check did not finish before its deadline. The result is unknown. |
| invalid_result | The check returned malformed or duplicate observations. None of that source's rows are used. |
| cancelled | The source cancelled its own check. Its result is unknown. |

Collection status is complete when every check finishes with ok or empty, partial when only some finish, and failed when none finish successfully. These statuses describe evidence collection, not whether the application is healthy or the cause is known.

Output stays in configured source order even when checks finish in a different order. Every evidence id is namespaced with its check name, so recent_errors::1 and service_health::1 are different clues. Each observation retains its source label. Input rows are copied rather than mutated. Unexpected exception messages are not printed because they can contain request details or secrets; only the exception class is shown.

## Connecting collection to investigation

collect_and_investigate passes only the successfully collected observations to the existing investigation function. Failure messages never become diagnostic evidence. Missing checks appear in the message, each hypothesis's missing-evidence notes and the next checks. With no clues, the investigator abstains. A concrete surviving clue can support an unverified hypothesis, but missing sources remain explicit and confirmed_root_cause stays empty.

The simulated example has a missing network route. A previous update is only a timing observation, so the program does not assert that it caused the missing route. The checks are suggestions for a person; they never execute.

The new mode is separate from --investigate file input and the synthetic approval workflow. Combining it with --real, --sample, a fixture id, --fresh, --list, --defer-approval or --investigate is rejected before those paths run.

## Tests and limits

Concurrency is tested using events: each source must start before any source may finish. A sequential collector cannot pass that test. Separate tests check independent deadlines, source failure, malformed results, duplicate ids across sources, empty results, cancellation cleanup, stable ordering, no model/network/memory/action calls in the demos, and incomplete-evidence messages. The existing ranking and evaluation reports reproduce unchanged.

This demonstrates async collection and failure handling, not production reliability or improved diagnostic accuracy. The sample sources are not independent real-world evidence. Before using a real connector, define its read-only scope, credentials, incident window, source provenance and timeout behavior, then test it against failures. The collector accepts reader callbacks; it cannot make arbitrary caller-supplied Python code read-only.

## Your learning exercise

Start with the partial demo. Identify the one clue that arrived and the two checks that did not. Then read _run_check and collect_evidence in evidence_collection.py. Find the await that allows another helper to work and the timeout that stops waiting for one helper. Predict what the failed demo will say before running it.
