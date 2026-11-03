# Runbook holdout evaluation

Score the frozen assistant on eight supported questions and two unsupported
questions. A retrieval point requires the expected guide among the top three.
An answer point requires all listed guidance with supporting citations.
An abstention point requires withholding an answer to an unsupported request.

| ID | Question | Expected evidence |
| --- | --- | --- |
| H01 | The storefront is unavailable to buyers. Whom should we alert, and do we need permission? | customer_outage:3,5. Page on-call after human approval. |
| H02 | The customer-facing service is down. Is verbal sign-off for a specific change required before we touch it? | customer_outage:5. Human approval for the specific action is required. The guide gives no required approval channel. |
| H03 | Database connections are maxed out. Which logs might tell us what is happening? | db_connection_pool:4. Check connection pooler service logs. |
| H04 | Before restarting the database connection pooler, whose go-ahead do we need? | db_connection_pool:5. Human approval. |
| H05 | Redis hit its memory ceiling. What should we inspect to understand eviction? | redis_memory:4. Inspect memory eviction settings and keyspace metrics. |
| H06 | A release sent the 500 error rate soaring. Would a reboot be the right first response? | rollback_bad_deploy:5. Roll back only after human approval. Restart is the wrong first step. |
| H07 | When the dashboard takes forever to render, what should we review first? | slow_dashboard:3,4. Review pool limits, query performance and pooler status. |
| H08 | Is it okay to power-cycle the Redis cache nodes before a human gives the green light? | redis_memory:5. Restart requires human approval. |
| H09 | Which Redis maxmemory value in gigabytes should we set for production? | Unsupported. The guide gives no target limit. |
| H10 | What approval form must I file before I restart Redis? | Unsupported. The guide requires human approval and gives no form. |

## Results

| Measure | Previously tuned sets | New holdout |
| --- | --- | --- |
| Expected passage in the top three | 8/8 each | 8/8 |
| Complete cited answers | 8/8 each | 6/8 |
| Abstention on unsupported questions | 2/2 each | 1/2 |

- H01. The outage guide ranked first, but the answer rule missed the
  wording about alerting someone and asking permission.
- H04. The database guide ranked second, and answer selection considered
  only the top score. The question also used restarting and go-ahead,
  which the operation and approval rules do not recognize.
- H10. The assistant quoted the human approval requirement, but the guide
  specifies no form. The answer should have flagged that missing detail.

H09 correctly received an abstention. The holdout uses the same five
guides, so it measures unfamiliar questions within that corpus.

## Compare Gemini on the same questions

Use `--model-answer` in place of `--answer` to send the question and the
same retrieved lines to Gemini. The CLI checks that each cited line was
retrieved. Check separately that each line actually supports its claim.

For H10, award the abstention point if the answer explicitly says the
guides give no approval form. It may also cite the general human approval
requirement. Record API errors as unavailable and leave those answers
unscored. Output labeled Rule-based fallback belongs to the rules.

```zsh
GOOGLE_API_KEY='op://Personal/Google API Key/credential' op run -- python runbook_search.py --model-answer 'What approval form must I file before I restart Redis?'
```

The rules scored 6/8 for complete cited answers and 1/2 for abstention.
Live Gemini scores are pending.
