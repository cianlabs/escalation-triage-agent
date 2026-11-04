# Independent line labels

Qwen 2.5 3B receives one retrieved line and the question per call.
It labels the line supports, context or irrelevant. The program displays
only supporting lines verbatim. Retrieval uses the same 0.3 cutoff and
15-guide corpus.

The eight answer-design questions are regression cases. Four fresh
questions and expected line IDs were committed before implementation.
Those include two supported diagnostic questions and two requests for
details the corpus lacks.

| Measure | Regression questions | Fresh questions |
| --- | --- | --- |
| All required lines selected | 1/6 | 0/2 |
| Unsupported questions with no lines selected | 2/2 | 2/2 |
| Additional selected lines | 0 | 0 |

The model labeled 37 lines in 13.18 seconds total, including retrieval.
It returned one supports label, ten context labels and 26 irrelevant
labels. No request or validation failures occurred.

A02 selected the required queue guidance. A01, A03, A04, A05 and A06
withheld required evidence. Neither fresh supported question, L01 for
webhook checks nor L02 for storage measurements, received supporting
lines. All four unsupported questions received no supporting lines.

The earlier whole-set selector included all required lines for 3/6
regression questions, versus 1/6 here. Independent decisions did not
improve evidence selection in this run. High abstention on unsupported
questions must be considered alongside the failure to select evidence
for seven of eight supported questions.

Every label and rendered excerpt is saved in line-label-responses.json.
This remains a separate experiment. The application answer mode is
unchanged. One run per question does not establish a stable model ranking.

Reproduce with Ollama, EmbeddingGemma and qwen2.5:3b installed:

```sh
python runbook_line_eval.py --output results/line-label-repeat.json
```
