# Semantic retrieval with local answers

The optional semantic mode searches the 15-guide practice corpus with
EmbeddingGemma and the fixed 0.3 cutoff. It sends up to three guides
to the existing model answer function. Citations point to text files
under fixtures/semantic/guides. The evaluation and CLI share those files.

Run with Ollama and both models installed:

```sh
python runbook_search.py --semantic --model-answer --ollama-model qwen2.5:3b 'The cache keeps throwing things away. What should I inspect?'
```

## First full-path holdout

One live local run per question. A complete answer must provide the
relevant diagnostic guidance with citations and preserve any approval
requirements. Unsupported questions must explicitly identify missing
information. A rejected model response counts as a failed answer and
is recorded separately as unavailable output.

| Measure | Result |
| --- | --- |
| Expected guide retrieved | 8/8 |
| Complete supported answer | 1/8 |
| Unsupported question handled | 2/4 |
| Model responses rejected by validation | 7/11 calls |

T03 gave the certificate checks. T01, T02, T05, T07, and T08
returned invalid answers or citations. T04 withheld an answer despite
receiving the DNS guide. T06 answered with queue guidance instead of
storage latency checks.

T09 returned no retrieved guides and abstained without calling the model.
T10 explicitly said the Redis command was missing. T11 and T12 produced
invalid responses and used the labeled fallback. The captured responses
are in semantic-answer-responses.json. An earlier exploratory pass also
showed unsupported claims, demonstrating that citation existence alone
does not establish grounding.

The 8/8 retrieval score does not imply good answers. The citation validator
checks that a line was retrieved, while this evaluation also checks
whether it supports the model's claim. These cases use synthetic practice
guides. The answer rubric was applied during review of this first run,
so these scores are exploratory.
