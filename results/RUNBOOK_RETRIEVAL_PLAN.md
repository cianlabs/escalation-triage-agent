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
