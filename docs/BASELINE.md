# Public incident baseline

Deterministic ranking tool on public user-impact observations. Diagnosis metrics measure broad cause families, not exact mechanisms or verified root causes. Four cautious cases are scored separately.

| Overall top-1 | Overall top-3 | Vague symptom top-1 | Correctly cautious |
| --- | --- | --- | --- |
| 10/26 (38.5%) | 11/26 (42.3%) | 3/13 (23.1%) | 4/4 (100.0%) |

The existing Bad deploy title maps to change regression. Process needs a restart is a remedy, and Customer-facing outage is impact; neither earns cause credit. The top-3 score is a vocabulary-coverage ceiling because the tool always returns the same three titles. Caution measures restraint and valid output structure, not hypothesis relevance. Vague cases have equally sparse evidence; the ranker ignores the symptom itself.

10 top-1 hits have no supporting evidence. The frozen ranker keeps Bad deploy first when evidence counts tie. Those hits are guesses, not evidence of successful investigation.

## Missed incidents

- PUB-01 (Installation token integer overflow): Top three cannot express integer overflow; source mechanism: Installation token integer overflow.
- PUB-02 (Database primary crash during failover): Top three cannot express database failure; source mechanism: Database primary crash during failover.
- PUB-05 (Actions SQL infrastructure failure): Top three cannot express database failure; source mechanism: Actions SQL infrastructure failure.
- PUB-06 (Check suite integer overflow in GraphQL library): Top three cannot express integer overflow; source mechanism: Check suite integer overflow in GraphQL library.
- PUB-08 (Hosted compute authentication provider outage): Top three cannot express dependency outage; source mechanism: Hosted compute authentication provider outage.
- PUB-09 (Datadog regional connectivity failure): Correct broad cause family is present, but not ranked first.
- PUB-12 (Atlassian site deletion): Top three cannot express operator deletion; source mechanism: Deletion script receives site IDs instead of app IDs.
- PUB-13 (Poor query and retries overload MySQL primary): Top three cannot express query overload; source mechanism: Poor query and retries overload MySQL primary.
- PUB-16 (AWS Kinesis thread limit exhaustion): Top three cannot express resource limit; source mechanism: Front-end fleet exceeds operating system thread limit.
- PUB-17 (Pages serving node stops accepting builds): Top three cannot express build node failure; source mechanism: Pages serving node stops accepting builds.
- PUB-19 (GitHub network partition and database topology divergence): Top three cannot express network partition; source mechanism: Network partition triggers incompatible database failover topology.
- PUB-20 (Memcached amplification DDoS): Top three cannot express ddos; source mechanism: Memcached amplification DDoS.
- PUB-26 (Traffic surge congests Cloudflare AWS interconnect): Top three cannot express network congestion; source mechanism: Traffic surge congests Cloudflare AWS interconnect.
- PUB-27 (Abuse remediation disables production R2 gateway): Top three cannot express operator disablement; source mechanism: Abuse remediation disables production R2 gateway.
- PUB-28 (Third party storage outage breaks Workers KV): Top three cannot express storage dependency; source mechanism: Third party storage outage breaks Workers KV.
- PUB-30 (Maintenance command removes excess S3 servers): Top three cannot express capacity removal; source mechanism: Maintenance command removes excess S3 servers.

## All incidents

| Incident | Kind | Top-1 | Top-3 | Caution |
| --- | --- | --- | --- | --- |
| PUB-01 | diagnosis | miss | miss | not scored |
| PUB-02 | diagnosis | miss | miss | not scored |
| PUB-03 | cautious | not scored | not scored | pass |
| PUB-04 | cautious | not scored | not scored | pass |
| PUB-05 | diagnosis | miss | miss | not scored |
| PUB-06 | diagnosis | miss | miss | not scored |
| PUB-07 | diagnosis | pass | pass | not scored |
| PUB-08 | diagnosis | miss | miss | not scored |
| PUB-09 | diagnosis | miss | pass | not scored |
| PUB-10 | diagnosis | pass | pass | not scored |
| PUB-11 | diagnosis | pass | pass | not scored |
| PUB-12 | diagnosis | miss | miss | not scored |
| PUB-13 | diagnosis | miss | miss | not scored |
| PUB-14 | diagnosis | pass | pass | not scored |
| PUB-15 | diagnosis | pass | pass | not scored |
| PUB-16 | diagnosis | miss | miss | not scored |
| PUB-17 | diagnosis | miss | miss | not scored |
| PUB-18 | diagnosis | pass | pass | not scored |
| PUB-19 | diagnosis | miss | miss | not scored |
| PUB-20 | diagnosis | miss | miss | not scored |
| PUB-21 | diagnosis | pass | pass | not scored |
| PUB-22 | diagnosis | pass | pass | not scored |
| PUB-23 | cautious | not scored | not scored | pass |
| PUB-24 | diagnosis | pass | pass | not scored |
| PUB-25 | cautious | not scored | not scored | pass |
| PUB-26 | diagnosis | miss | miss | not scored |
| PUB-27 | diagnosis | miss | miss | not scored |
| PUB-28 | diagnosis | miss | miss | not scored |
| PUB-29 | diagnosis | pass | pass | not scored |
| PUB-30 | diagnosis | miss | miss | not scored |
