# Fresh runbook questions

Expected evidence was specified before running the assistant. Use the same
five guides and score retrieval, complete cited answers, and abstention separately.

| ID | Question | Expected evidence |
| --- | --- | --- |
| F01 | Nobody can access the customer portal. Who needs to be paged, and when? | customer_outage:3,5. Page on-call with human approval. |
| F02 | During a service outage, can we make changes before someone signs off? | customer_outage:5. A human must approve the specific action first. |
| F03 | We've hit the database connection ceiling. Where should I look for logs? | db_connection_pool:4. Connection pooler service logs. |
| F04 | Is permission needed to restart the database pooler? | db_connection_pool:5. Human approval is required. |
| F05 | Cache evictions are spiking on Redis. Which metrics should I inspect? | redis_memory:4. Memory eviction settings and keyspace metrics. |
| F06 | We shipped a deploy and immediately saw a burst of 500 responses. Is a restart the first move? | rollback_bad_deploy:5. Roll back after human approval. A restart is the wrong first step. |
| F07 | The dashboard feels sluggish. Which checks would narrow it down? | slow_dashboard:3,4. Pool limits, query performance, and pooler status. |
| F08 | Can I cycle the Redis nodes without getting a human to sign off? | redis_memory:5. Human approval is required for a restart. |
| F09 | How do I increase Redis maxmemory? | Unsupported. The guide gives checks and restart guidance. |
| F10 | Where are the database pooler logs stored on disk? | Unsupported. The guide names the logs without giving a path. |
