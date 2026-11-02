# Evidence-ranking synthetic challenge

These are authored synthetic examples, frozen in a separate commit before implementation. They are not real incidents, a hidden test set, or an estimate of production accuracy. They check specific mechanism recognition and uncertainty behavior.

Matched expected behavior: 11/12.

A match requires the expected uncertainty state and, when one is specified, the expected leading mechanism. A specific clue can support an unverified hypothesis but never a confirmed cause. Conflicting clues must remain conflicting. Generic impact alone must produce insufficient evidence.

| Case | Expected behavior | Actual behavior | Result |
| --- | --- | --- | --- |
| CH-01 | insufficient_evidence | insufficient_evidence | pass |
| CH-02 | insufficient_evidence | insufficient_evidence | pass |
| CH-03 | supported_hypothesis: network_routing_failure | supported_hypothesis: network_routing_failure | pass |
| CH-04 | supported_hypothesis: database_connection_limit | supported_hypothesis: database_connection_limit | pass |
| CH-05 | supported_hypothesis: authentication_failure | supported_hypothesis: authentication_failure | pass |
| CH-06 | supported_hypothesis: storage_access_failure | supported_hypothesis: storage_access_failure | pass |
| CH-07 | insufficient_evidence | insufficient_evidence | pass |
| CH-08 | conflicting_evidence: memory_exhaustion | conflicting_evidence: memory_exhaustion | pass |
| CH-09 | supported_hypothesis: deployment_regression | supported_hypothesis: deployment_regression | pass |
| CH-10 | supported_hypothesis: storage_io_failure | supported_hypothesis: storage_io_failure | pass |
| CH-11 | supported_hypothesis: certificate_expiry | insufficient_evidence | miss |
| CH-12 | competing_hypotheses | competing_hypotheses: memory_exhaustion | pass |

## Misses

- CH-11: Expected certificate_expiry; the current rules returned insufficient_evidence. Leave this miss visible rather than changing the challenge.

On the existing 30 exposed public user-impact records, this mode returns insufficient evidence for 30. This is a behavior audit, not an accuracy score: the records usually lack diagnostic clues. No retrospective cause labels enter the new ranker.

The original public ranking baseline and scorer remain unchanged. A new real-world comparison still needs fresh, independently reviewed diagnostic evidence and a locked evaluation protocol. User-impact-only observations generally do not contain mechanism clues.
