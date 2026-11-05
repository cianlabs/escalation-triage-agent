# Local runbook workspace

From an activated project virtual environment, run:

```sh
python runbook_ui.py
```

Open http://127.0.0.1:8765 in your browser. Keep the terminal running.
Stop the server with Control-C. If the port is occupied, use --port 8766.

## Explore the guides

The default keyword search reads every `.txt` file in `runbooks/`. Adding
a guide there makes it searchable on the next query; there is no separate
index to rebuild. Type a question or choose an example. The page displays the
rule-based answer alongside up to three retrieved passages with line numbers.
If nothing in the corpus overlaps the question, the page shows no passages
and the rule-based answer says the guides do not provide a supported answer.
That abstention is required: the assistant must not invent a procedure.
Click an answer citation to highlight its source line.

A retrieved passage can share a topic without supplying the requested
detail. The rule-based answer can abstain while passages remain visible.

## Compare a model

Choose Semantic to search the separate 15-guide practice corpus using the
fixed 0.3 cutoff. This requires Ollama running with embeddinggemma installed.
The rule-based answer has limited coverage in the expanded corpus.

Generate answer sends the question and the retrieved passages to the
chosen model. The menu opens on xAI Grok 4.7. Choose Local Ollama for a
Qwen model. The comparison request repeats retrieval and refreshes the
displayed passages and rules, so the model's citations refer to that
request's evidence. A failed Grok request stays on Grok: it does not call
Ollama or Gemini. The page has no key field. The server reads `XAI_API_KEY`
from its own environment. The Grok call is the same Responses request as
the CLI. It must not send Live Search `search_parameters` or
`max_tool_calls`. Setting `search_parameters` returns HTTP 410, and
`max_tool_calls` is not a field on the Responses request. The call omits
`web_search`, `x_search`, and `tool_choice`. Setting `tool_choice` without
tools is rejected.

```sh
ollama pull embeddinggemma
ollama pull qwen2.5:3b
```

Qwen 7B is optional and must be installed separately to use that selection.
Model output is experimental and may contradict the sources even when
citations exist. The page keeps the source passages and rule-based answer
visible if generation fails.

## Scope

The server binds to 127.0.0.1 and has no added package dependencies.
The page runs from local assets. Keyword and semantic search make no cloud
call. Generate answer calls xAI only when Grok is selected and
`XAI_API_KEY` is set; otherwise it reports the error and keeps the rules.
Search and generation use the existing retrieval and answer functions. It
does not run operational actions. Questions and answers are not persisted,
and the server does not log their text or the API key.
