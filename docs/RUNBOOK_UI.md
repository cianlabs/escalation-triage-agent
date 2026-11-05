# Local runbook workspace

From an activated project virtual environment, run:

```sh
python runbook_ui.py
```

Open http://127.0.0.1:8765 in your browser. Keep the terminal running.
Stop the server with Control-C. If the port is occupied, use --port 8766.

## Explore the guides

The default keyword search uses the five runbooks from the cited-answer
experiments. Type a question or choose an example. The page displays the
rule-based answer alongside up to three retrieved passages with line numbers.
Click an answer citation to highlight its source line.

A retrieved passage can share a topic without supplying the requested
detail. The rule-based answer can abstain while passages remain visible.

## Compare locally

Choose Semantic to search the separate 15-guide practice corpus using the
fixed 0.3 cutoff. This requires Ollama running with embeddinggemma installed.
The rule-based answer has limited coverage in the expanded corpus.

Generate answer sends the question and the retrieved passages to the chosen
local Qwen model. The comparison request repeats retrieval and refreshes
the displayed passages and rules, so the model's citations refer to that
request's evidence. Select one of the two supported local model tags.

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
The page runs from local assets and makes no cloud API calls. Search and
generation use the existing retrieval and answer functions. It does not
run operational actions. Questions and answers are not persisted, and the
server does not log their text.
