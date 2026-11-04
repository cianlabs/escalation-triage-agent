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

## Schema-constrained local answers

Ollama now receives an explicit response schema, including an enum of
retrieved citation IDs. The queue-depth example was removed from the
prompt after an intermediate run copied it into unrelated answers.
Both intermediate and final responses are saved.

| Measure | Previous | Schema plus revised prompt |
| --- | --- | --- |
| Complete supported answer | 1/8 | 3/8 |
| Unsupported question handled | 2/4 | 3/4 |
| Model responses rejected | 7/11 | 1/11 |

T02, T03, and T07 passed. T01 suggested a restart and omitted the checks.
T04 repeated the question as a cited claim. T05 gave appropriate checks
but claimed the reason for write failure was unknown despite the stated
full filesystem. T06 and T08 included checks while incorrectly claiming
the corresponding symptoms were absent from the guides. T11 returned an
invalid answer. T09, T10, and T12 handled missing information.

The schema improves response format and restricts citation IDs.
It does not establish that a claim follows from its cited line.
These cases guided the prompt revision, so these are regression results
from one local response per question.

## Compare another Gemini model

Select a cloud model with `--gemini-model`. For example:

```zsh
GOOGLE_API_KEY='op://Personal/Google API Key/credential' op run -- python runbook_search.py --semantic --model-answer --gemini-model gemini-3.8-flash 'What command increases Redis maxmemory?'
```

The question and retrieved evidence are sent to Google's API. Use the
same holdout questions and prompt when comparing with the local model.
Cloud availability, cost and answer quality need live measurement.
