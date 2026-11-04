# Answer design experiment

Eight new questions and required guidance were committed before either run.
Compare the original prompt with a candidate asking for supported checks
first and missing details afterward. Use Qwen 2.5 3B, the same 15 guides,
the same semantic retrieval and cutoff, and the same citation schema.

A supported answer passes when it includes all required guidance, preserves
approval, and uses correct supporting citations. Contradictions about the
evidence fail. Missing-detail handling requires an explicit statement that
the requested detail is absent. A generic statement of further missing
steps is not itself a failure unless it contradicts the evidence.

| Measure | Original prompt | Candidate prompt |
| --- | --- | --- |
| Complete cited answers | 3/6 | 1/6 |
| Missing details handled | 2/2 | 2/2 |
| Invalid model responses | 0/8 | 0/8 |

The original passed A02, A03 and A05. Both prompts cited Redis line 3
for the check actually on line 4, and omitted the DNS record and TTL
checks while claiming they were missing. Both failed the complete
rollback answer.

The candidate passed A03. A02 added an unrelated claim that disk latency
and storage health were missing. A05 omitted the required deletion approval
and added an unrelated missing-detail claim. A06 omitted the approval
requirement and the warning against restarting. A07 and A08 correctly
identified the missing resolver address and queue threshold.

The candidate is saved in answer-design-candidate.txt. Both response sets
are captured in answer-design-before.json and answer-design-after.json.
The candidate was rejected as an application default based on this run.
The original prompt remains in the application.

These are single runs of a stochastic model on eight questions within the
same synthetic corpus. The original prompt run was seen before the candidate
was finalized, so this is a development experiment.

The evaluation runner accepts a question file:

```sh
python runbook_model_eval.py --model qwen2.5:3b --questions fixtures/semantic/answer-design.json --output results/answer-design-repeat.json
```
