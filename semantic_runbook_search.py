"""Retrieve cited passages from the 15-guide practice corpus using Ollama."""

import httpx

from errors import AgentError
from semantic_retrieval_eval import FIXTURES, cosine


def search_semantic(question):
    paths = sorted((FIXTURES / 'guides').glob('*.txt'))
    passages = [path.read_text(encoding='utf-8') for path in paths]
    inputs = ['title: ' + path.name + ' | text: ' + passage
              for path, passage in zip(paths, passages)]
    inputs.append('task: search result | query: ' + question)
    try:
        with httpx.Client(trust_env=False, timeout=120) as client:
            response = client.post('http://127.0.0.1:11434/api/embed', json={
                'model': 'embeddinggemma', 'input': inputs, 'truncate': False,
            })
            response.raise_for_status()
            vectors = response.json()['embeddings']
        if len(vectors) != len(inputs):
            raise ValueError
        hits = []
        for path, passage, vector in zip(paths, passages, vectors[:-1]):
            score = cosine(vector, vectors[-1])
            if score >= 0.3:
                citation = f'fixtures/semantic/guides/{path.name}:1-{len(passage.splitlines())}'
                hits.append((score, citation, passage))
        return sorted(hits, key=lambda hit: (-hit[0], hit[1]))[:3]
    except httpx.RequestError:
        raise AgentError('RETRIEVAL_ERROR', 'Could not reach the local embedding server.') from None
    except (httpx.HTTPStatusError, KeyError, TypeError, ValueError):
        raise AgentError('RETRIEVAL_ERROR', 'Embedding retrieval failed. Check that embeddinggemma is installed.') from None
