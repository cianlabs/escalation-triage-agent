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

## Results

| Measure | Development set | Fresh set |
| --- | --- | --- |
| Expected passage in the top three | 8/8 | 8/8 |
| Complete cited answers | 8/8 | 5/8 |
| Abstention on unsupported questions | 2/2 | 1/2 |

F03–F07 received complete cited answers. F09 correctly received an abstention.
The ranking found the expected passage for all eight supported questions.
The misses came from the answer step:

- F01. It retrieved the outage guide but missed the phrasing about who needs to be paged.
- F02. It retrieved the outage guide but missed signs off as approval language.
- F08. It retrieved the Redis guide but missed cycle as a way of saying restart.
- F10. It cited which logs to check, but the question asked for an on-disk path the guide does not give.

The fresh set uses the same five short guides. It tests unfamiliar wording
and unsupported details within that corpus.
