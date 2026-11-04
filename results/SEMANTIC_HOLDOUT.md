# Semantic retrieval holdout

Twelve questions and expected evidence were committed before scoring.
Eight have an expected guide. Four ask for information missing from the
corpus. The corpus, embedding model, and 0.3 cutoff were fixed.

| Measure | Keyword | Embeddings | Embeddings with 0.3 cutoff |
| --- | --- | --- | --- |
| Expected guide in top three | 6/8 | 8/8 | 8/8 |
| Extra results across all questions | 16 | 28 | 7 |
| Unsupported questions with no results | 1/4 | 0/4 | 1/4 |

Keyword search missed T04, the hostname-to-IP question, and T06, the
question about waiting on reads and writes. Embeddings included the
expected guide on both. Filtering retained all eight expected guides.

The filter returned nothing for T09, the savings calculation. It still
returned guides for T10, the command for increasing Redis maxmemory,
T11, the exact pooler log path, and T12, the certificate renewal command.
Those guides match the topics without supplying the requested details.
A similarity cutoff cannot establish whether a passage answers a question.

All returned guides count as extra on unsupported questions. On supported
questions, guides other than the one expected count as extra. Some may
be topically related. The total of seven filtered extras comprises three
on supported questions and four on unsupported questions.

To reproduce with Ollama and EmbeddingGemma installed:

```sh
python semantic_retrieval_eval.py --questions holdout.json --min-similarity 0.3
```

The command prints each result list. This experiment uses synthetic guides
and the same 15-guide corpus as development, with new question wording.
It measures retrieval and result filtering. Answer quality needs its own
evaluation.
