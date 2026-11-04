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

## Measured results

| Measure | Qwen 2.5 3B | Qwen 2.5 7B |
| --- | --- | --- |
| Expected guide retrieved | 8/8 | 8/8 |
| Complete supported answers | 4/8 | 0/8 |
| Unsupported questions handled | 3/4 | 4/4 |
| Model responses rejected | 1/11 | 0/11 |
| Median full command time | 3.04 seconds | 2.80 seconds |
| Total elapsed command time | 114.80 seconds | 45.77 seconds |
| First command | 80.41 seconds | 8.47 seconds |

T09 retrieved nothing and made no model call. Its time is included in the
command timings. The first 3B command overlapped the 7B download and had
an unusually long startup. These timings are observations from one
sequential run per model and do not establish a speed advantage.

3B passed T02, T03, T07 and T08. It incorrectly said the cache question
was unsupported in T01, repeated the question in T04, contradicted the
guide's deletion approval in T05, and claimed storage-wait information
was missing in T06. T11 failed validation.

7B withheld the diagnostic guidance on T01, T02, T03, T04 and T06.
T05 gave checks but also claimed the stated full-filesystem symptom
could not be identified from the evidence. T07 omitted the approval
requirement and the warning against restarting. T08 gave the checks but
also claimed the evidence did not give specific steps. Under the rubric,
these contradictions or omissions fail the complete-answer criterion.

7B explicitly identified the missing requested details in T10–T12.
The smaller model also handled T10 and T12. Both abstained on T09
without generation.

The captured outputs are qwen3b-comparison-responses.json and
qwen7b-comparison-responses.json. The earlier 3B run scored 3/8; this new
run scored 4/8. Generation varies, so one trial cannot establish a stable
model ranking. These questions have already guided prompt changes.

## Reproduce

With Ollama running and EmbeddingGemma installed:

```sh
ollama pull qwen2.5:7b
python runbook_model_eval.py --model qwen2.5:7b --output results/qwen7b-comparison-responses.json
```

The runner saves after every case and records timeouts. The answer prompt,
retrieval threshold, and application default model were held fixed.
