# Runbook assistant evaluation

The first assistant will search five existing guides: customer outage,
database connection pool, Redis memory, rollback after a bad deployment,
and slow dashboard. It will return a short answer with a file and passage
citation when the guides support an answer. For questions outside that
scope, it will say what the guides do not cover. The assistant is read-only.

| ID | Question | Expected source | Evidence the answer must include |
| --- | --- | --- | --- |
| R01 | Customers can't use the service at all. Who should I bring in? | runbooks/customer_outage.txt | Page the on-call engineer after human approval. |
| R02 | The service is down. Can I change it while waiting for approval? | runbooks/customer_outage.txt | Wait for a human to approve a specific action before changing the service. |
| R03 | The database says there are too many connections. Which logs should I look at? | runbooks/db_connection_pool.txt | Check the connection pooler service logs. |
| R04 | Can I bounce the database connection pooler straight away? | runbooks/db_connection_pool.txt | Restart requires human approval. |
| R05 | Our cache is running out of space. What settings and metrics should I inspect? | runbooks/redis_memory.txt | Inspect memory eviction settings and keyspace metrics. |
| R06 | Users started seeing lots of 500s right after a release. Should I restart first? | runbooks/rollback_bad_deploy.txt | The guide calls for a rollback after human approval. It says a restart is the wrong first step. |
| R07 | The dashboard takes ages to load. What should I check before touching anything? | runbooks/slow_dashboard.txt | Review connection pool limits, query performance, and pooler status. |
| R08 | Redis reports maxmemory. Can I restart its nodes without asking? | runbooks/redis_memory.txt | Restart requires human approval. |
| R09 | Which command rotates our production TLS certificate? | None | The guides do not specify a certificate rotation procedure. |
| R10 | How do I cancel a deployment that's stuck waiting for a reviewer? | None | The guides do not explain how to cancel a pending deployment. A rollback after a bad release addresses a different situation. |

## How to score

- Retrieval on R01–R08. Count whether the expected file and the relevant
  passage are among the first three results. Report the score out of eight.
- Answer grounding on R01–R08. Count answers that cover the required evidence,
  cite the supporting passage, and avoid unsupported instructions. Report
  the score out of eight.
- Abstention on R09–R10. Count answers that clearly say the guides lack the
  requested procedure and avoid proposing one. Report the score out of two.

These questions were written from the guides before implementation. They
are development cases. A separate set of questions will be needed to
measure performance after tuning.

## First lexical baseline

Run `python runbook_search.py 'What should I check if Redis hits maxmemory?'`
from the repository. The search ranks guides by the number of distinct
question words they share, after removing common words. Each short guide
is one passage. Positive matches include exact file and line citations.

| Measure | Score |
| --- | --- |
| Expected passage in the top three | 8/8 |
| Abstention on unsupported questions | 1/2 |
| Answer grounding | Unscored. This version returns excerpts. |

R09 produced no hits. R10 surfaced the outage guide on the shared word
waiting, even though the guide gives no cancellation procedure. This is
the only miss under the retrieval and abstention measures above. These
are development questions, and the corpus is small.

## Rarity-weighted search

Shared words now carry more weight when they appear in fewer guides.
Results below half the best score are omitted.

| Measure | Original | Rarity-weighted |
| --- | --- | --- |
| Expected passage in the top three | 8/8 | 8/8 |
| Abstention on unsupported questions | 1/2 | 1/2 |
| Excerpts returned across the ten questions | 23 | 12 |
| Excerpts returned for the Redis maxmemory example | 3 | 1 |

The Redis example retains just the Redis guide. R10 still surfaces the
outage guide because it shares the word waiting and has no stronger
match to compare against. A relative cutoff reduces weak alternatives
when there is a strong match. These scores use the development set.

## Cited diagnostic answers

Use `python runbook_search.py --answer 'What should I check if Redis hits maxmemory?'`.
This mode quotes explicit diagnostic checks from the top guide when the
question shares a subject term with its title. If there is no qualifying
guide or the qualifying guides tie, it abstains. Search mode still shows
the ranked excerpts.

| Measure | Development score |
| --- | --- |
| Expected passage in top three | 8/8 |
| Complete grounded answer | 1/8 |
| Abstention on unsupported questions | 2/2 |

R05 was complete. R07 cited query performance and pooler status but omitted
connection pool limits. R01–R04, R06, and R08 got no answer. The mode only
extracts explicit checks, and its word matching can miss paraphrases.
R09 and R10 both got abstentions. Two additional spot checks returned
a cited answer for Redis metrics and abstained on TLS certificate rotation.

## Log questions and checks inside sentences

The answer mode now accepts log questions and recognizes checks after an
opening condition. The log answer quotes the diagnostic clause and omits
the instruction to clear idle backends.

| Development measure | Previous | Updated |
| --- | --- | --- |
| Expected passage in top three | 8/8 | 8/8 |
| Complete grounded answer | 1/8 | 3/8 |
| Abstention on unsupported questions | 2/2 | 2/2 |

R03, R05, and R07 are complete. R01, R02, R04, R06, and R08 still
abstain because they ask about actions or approval. In three additional
spot checks, the assistant cited the pooler logs for a rephrased database
question and abstained on deployment approval logs. It missed the
supported question asking which checks to run for a sluggish dashboard.
The answer trigger matches whole words and accepts check but misses checks.

## Action and approval answers

The answer mode quotes approval requirements for supported operations.
It also recognizes checks as a diagnostic question term.

| Development measure | Previous | Updated |
| --- | --- | --- |
| Expected passage in top three | 8/8 | 8/8 |
| Complete grounded answer | 3/8 | 8/8 |
| Abstention on unsupported questions | 2/2 | 2/2 |

The five previously missed action and approval questions now receive
cited answers. Spot checks for rebooting Redis and restarting after a
release triggered 500 errors both preserved approval. A rephrased
deployment cancellation question still received an abstention.
These rules were developed against the ten questions and use a limited
set of terms. Broader paraphrases still need evaluation.
