# Local model comparison

Run one response per semantic holdout question for Qwen 2.5 3B and 7B
on the same Mac. Use the same retrieval, fixed 0.3 cutoff, schema and prompt.
Timings cover embedding retrieval, model startup where applicable, and
answer generation. First requests may include model loading.

## Scoring rubric

A complete answer includes the required guidance, uses supporting citations,
and avoids unsupported claims or contradictions. Unsupported questions
pass when the missing detail is explicitly identified. API or validation
failures count as failed answers and are also reported separately.

| Case | Required guidance |
| --- | --- |
| T01 | Inspect eviction settings and keyspace metrics. |
| T02 | Inspect queue depth, oldest message age and consumer throughput. |
| T03 | Inspect certificate validity dates and the served chain. |
| T04 | Compare resolver answers on affected and healthy machines. Check record changes and TTLs. |
| T05 | Inspect free space and largest directories. Preserve approval if deletion is mentioned. |
| T06 | Inspect disk latency, I/O queue depth and storage service health. |
| T07 | Rollback requires human approval. Restart is the wrong first step. |
| T08 | Inspect delivery history, destination URL and receiver response codes. |
| T09 | The guides give no compound-interest calculation. |
| T10 | The guides give no command to raise Redis maxmemory. |
| T11 | The guides give no filesystem path for pooler logs. |
| T12 | The guides give no certificate renewal command. |
