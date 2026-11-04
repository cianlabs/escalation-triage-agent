# Semantic retrieval baseline

This experiment searches 15 short practice guides. Five are snapshots of
the existing runbooks and ten were authored as synthetic guides for this
experiment. Fifteen questions and their expected guide IDs were committed
before the comparison implementation.

Both methods receive the same guides and questions. Keyword search uses
the existing term extraction, rarity weighting and relative cutoff.
EmbeddingGemma runs locally through Ollama. Cosine similarity selects
three embedding results per question without a relevance cutoff.

| Measure | Keyword | Embeddings |
| --- | --- | --- |
| Expected guide in top three | 12/15 | 15/15 |
| Unrelated results returned | 11 | 30 |

Each question has one expected guide. Other returned guides count as
unrelated under this rubric. Embeddings always return three results,
while keyword search can return fewer, so the counts reflect different
result filtering policies as well as ranking.

Keyword search missed S03, the expired certificate paraphrase, S04,
the hostname resolution paraphrase, and S10, the slow file reads question.
Embeddings included the expected guide for all 15 questions.
The guide with slow file reads ranked second behind the dashboard guide.

## Reproduce

With Ollama running:

```sh
ollama pull embeddinggemma
python semantic_retrieval_eval.py
```

The command prints every ranked result and the scores. It uses the
separate practice corpus in fixtures/semantic. Existing runbook answers
continue to use their five-guide corpus.

This is a development experiment on short synthetic material, with one
query per guide and no unsupported questions. It does not measure answer
quality or establish a safe semantic relevance threshold.

[Ollama embeddings API](https://docs.ollama.com/api/embed)
· [EmbeddingGemma](https://ollama.com/library/embeddinggemma)

## Exploratory similarity cutoffs

| Cutoff | Expected guide in top three | Extra results |
| --- | --- | --- |
| No cutoff | 15/15 | 30 |
| 0.3 | 15/15 | 12 |
| 0.4 | 10/15 | 1 |
| 0.6 | 0/15 | 0 |

The first trial, 0.6, removed every result. Two lower cutoffs were then
tested on the same questions. At 0.4, S02, S03, S04, S05, and S10 lost
their expected guides. At 0.3, all expected guides remained and extra
results fell from 30 to 12. This threshold was explored on the development
set and needs fresh questions before adoption.

Reproduce with `python semantic_retrieval_eval.py --min-similarity 0.3`.
The default comparison still uses no cutoff. The filter applies to results
from each search, and all 15 guides remain in the corpus.
