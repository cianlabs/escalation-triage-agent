import json

import pytest

from errors import AgentError
from runbook_model_answer import model_answer
from runbook_search import search


def test_partial_answer_names_missing_form_and_cites_approval():
    question = 'What approval form must I file before I restart Redis?'

    def ask(messages):
        evidence = json.loads(messages[1]['content'])['evidence']
        assert 'human approval' in evidence['runbooks/redis_memory.txt:5']
        return json.dumps({
            'claims': [{'text': 'Restart requires human approval.', 'citation': 'runbooks/redis_memory.txt:5'}],
            'missing': 'The guide does not specify a form.',
        })

    output = model_answer(question, search(question), ask)
    assert '[runbooks/redis_memory.txt:5]' in output
    assert 'does not specify a form' in output


def test_rejects_citation_outside_retrieved_passages():
    question = 'What should I check if Redis hits maxmemory?'
    with pytest.raises(AgentError, match='invalid runbook answer or citation'):
        model_answer(question, search(question), lambda _: json.dumps({
            'claims': [{'text': 'Check metrics.', 'citation': 'runbooks/redis_memory.txt:99'}],
            'missing': '',
        }))


def test_ollama_cli_uses_same_citation_validation(monkeypatch, capsys):
    import sys

    import httpx

    from runbook_search import main

    original_client = httpx.Client

    def respond(request):
        assert str(request.url) == 'http://127.0.0.1:11434/api/chat'
        body = json.loads(request.content)
        assert body['model'] == 'qwen2.5:3b'
        assert body['format']['required'] == ['claims', 'missing']
        assert 'runbooks/redis_memory.txt:5' in body['format']['properties']['claims']['items']['properties']['citation']['enum']
        assert 'runbooks/redis_memory.txt:5' in body['messages'][1]['content']
        return httpx.Response(200, json={'message': {'content': json.dumps({
            'claims': [{'text': 'Human approval is required.', 'citation': 'runbooks/redis_memory.txt:5'}],
            'missing': 'The guide gives no form.',
        })}})

    monkeypatch.setattr('runbook_model_answer.httpx.Client', lambda **kwargs: original_client(
        transport=httpx.MockTransport(respond), **kwargs))
    monkeypatch.setattr(sys, 'argv', ['runbook_search.py', '--model-answer', '--ollama-model',
                                     'qwen2.5:3b', 'What form do I need to restart Redis?'])
    assert main() == 0
    assert 'The guide gives no form.' in capsys.readouterr().out


def test_rejects_citation_only_approval_answer():
    question = 'What approval form must I file before I restart Redis?'
    citation = 'runbooks/redis_memory.txt:5'
    with pytest.raises(AgentError, match='invalid runbook answer or citation'):
        model_answer(question, search(question), lambda _: json.dumps({
            'claims': [{'text': citation, 'citation': citation}],
            'missing': '',
        }))
