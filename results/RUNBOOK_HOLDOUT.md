# Runbook holdout evaluation

Score the frozen assistant on eight supported questions and two unsupported
questions. A retrieval point requires the expected guide among the top three.
An answer point requires all listed guidance with supporting citations.
An abstention point requires withholding an answer to an unsupported request.

| ID | Question | Expected evidence |
| --- | --- | --- |
| H01 | The storefront is unavailable to buyers. Whom should we alert, and do we need permission? | customer_outage:3,5. Page on-call after human approval. |
| H02 | The customer-facing service is down. Is verbal sign-off for a specific change required before we touch it? | customer_outage:5. Human approval for the specific action is required. The guide gives no required approval channel. |
| H03 | Database connections are maxed out. Which logs might tell us what is happening? | db_connection_pool:4. Check connection pooler service logs. |
| H04 | Before restarting the database connection pooler, whose go-ahead do we need? | db_connection_pool:5. Human approval. |
| H05 | Redis hit its memory ceiling. What should we inspect to understand eviction? | redis_memory:4. Inspect memory eviction settings and keyspace metrics. |
| H06 | A release sent the 500 error rate soaring. Would a reboot be the right first response? | rollback_bad_deploy:5. Roll back only after human approval. Restart is the wrong first step. |
| H07 | When the dashboard takes forever to render, what should we review first? | slow_dashboard:3,4. Review pool limits, query performance and pooler status. |
| H08 | Is it okay to power-cycle the Redis cache nodes before a human gives the green light? | redis_memory:5. Restart requires human approval. |
| H09 | Which Redis maxmemory value in gigabytes should we set for production? | Unsupported. The guide gives no target limit. |
| H10 | What approval form must I file before I restart Redis? | Unsupported. The guide requires human approval and gives no form. |
