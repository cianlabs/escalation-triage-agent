import json

import httpx

from semantic_runbook_search import search_semantic


def test_semantic_cutoff_and_real_line_citations(monkeypatch):
    original = httpx.Client

    def respond(request):
        body = json.loads(request.content)
        assert len(body['input']) == 16
        assert body['truncate'] is False
        vectors = [[0.0, 1.0] for _ in range(15)]
        vectors[0] = [1.0, 0.0]
        return httpx.Response(200, json={'embeddings': vectors + [[1.0, 0.0]]})

    monkeypatch.setattr('semantic_runbook_search.httpx.Client',
                        lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    hits = search_semantic('A question')
    assert len(hits) == 1
    from pathlib import Path
    from semantic_retrieval_eval import FIXTURES
    _, citation, passage = hits[0]
    path, extent = citation.rsplit(':', 1)
    assert passage == (FIXTURES.parents[1] / path).read_text()
    assert extent == f'1-{len(passage.splitlines())}'
