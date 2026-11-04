# Evidence selection experiment

The local Qwen 2.5 3B model selects line IDs from the same semantic
retrieval results used in the answer-design experiment. The program then
renders the selected source text verbatim. Required IDs were committed
before the run.

| Measure | Result |
| --- | --- |
| All required evidence selected, supported questions | 3/6 |
| Exact expected set selected, supported questions | 1/6 |
| No lines selected, unsupported questions | 2/2 |
| Additional lines selected | 3 |
| Invalid model responses | 0/8 |

A01, A04 and A06 included all required lines. A01 added one context
line. A06 added two related rollback lines beyond the required approval
and restart guidance. These additions are related or redundant, and
count as extra under the exact-set rubric. A04 selected exactly the
required line.

A02, A03 and A05 selected nothing despite receiving supporting evidence.
A07 and A08 correctly selected nothing for the missing resolver address
and numeric queue threshold.

The original prose prompt on these questions scored 3/6 complete cited
answers; the revised prose prompt scored 1/6. Selection recovered 3/6
complete evidence sets. Verbatim rendering eliminates generated wording
and citation mismatches in the displayed excerpts. Selection still
requires checking that the lines answer the question.

This is one local run on development questions that guided earlier prompt
work. The selector is a separate experiment. It is not the application's
default answer mode.

With Ollama, EmbeddingGemma and qwen2.5:3b available:

```sh
python runbook_selection_eval.py --output results/evidence-selection-repeat.json
```

The output argument writes the captured selections and scores after each
question. The first run is saved in evidence-selection-responses.json.
