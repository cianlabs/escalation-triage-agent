from http.client import HTTPConnection
import json
from threading import Thread

import pytest

from errors import AgentError
from runbook_ui import Handler, ThreadingHTTPServer, query_runbooks


@pytest.fixture
def local_server():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_port
    server.shutdown()
    server.server_close()
    thread.join()


def test_http_search_returns_real_passages_and_exact_answer_without_model(local_server, monkeypatch):
    monkeypatch.setattr('runbook_model_answer.ask_ollama',
                        lambda *args: pytest.fail('Search must not call the model'))
    client = HTTPConnection('127.0.0.1', local_server)
    client.request('POST', '/api/query', json.dumps({
        'question': 'What should I check if Redis hits maxmemory?',
    }), {'Content-Type': 'application/json'})
    response = client.getresponse()
    result = json.loads(response.read())
    client.close()
    assert response.status == 200
    assert result['rule_answer'] == [{
        'citation': 'runbooks/redis_memory.txt:4',
        'text': 'Check memory eviction settings and keyspace metrics.',
    }]
    assert 'keyspace metrics' in result['passages'][0]['text']
    assert result['model_answer'] is None


def test_model_failure_keeps_rules_and_sources(monkeypatch):
    def unavailable(*args):
        raise AgentError('MODEL_ERROR', 'Local model unavailable.')
    monkeypatch.setattr('runbook_model_answer.ask_ollama', unavailable)
    result = query_runbooks({
        'question': 'What should I check if Redis hits maxmemory?', 'compare': True,
    })
    assert result['passages'] and result['rule_answer']
    assert 'Local model unavailable' in result['model_error']
    assert result['model_answer'] is None


def test_unsupported_question_stays_clear():
    result = query_runbooks({'question': 'How do I rotate TLS certificates?'})
    assert result['rule_answer'] == []


def test_http_rejects_cross_origin_posts_and_arbitrary_files(local_server):
    client = HTTPConnection('127.0.0.1', local_server)
    client.request('POST', '/api/query', '{}', {
        'Content-Type': 'application/json', 'Origin': 'https://unrelated.example',
    })
    response = client.getresponse()
    response.read()
    assert response.status == 403
    client.request('GET', '/../../agent.py')
    response = client.getresponse()
    response.read()
    assert response.status == 404
    client.request('GET', '/')
    response = client.getresponse()
    page = response.read()
    assert response.status == 200
    assert b'Find the next check.' in page
    assert b'grok-4.7' in page
    assert b'type="password"' not in page
    client.close()


@pytest.mark.parametrize('payload', [
    None, {'question': ''}, {'question': 'x', 'model': 'arbitrary-cloud-model'},
    {'question': 'x', 'compare': 'yes'},
    {'question': 'x', 'provider': 'gemini', 'model': 'grok-4.7'},
    {'question': 'x', 'provider': 'xai', 'model': 'qwen2.5:3b'},
])
def test_invalid_query_is_rejected(payload):
    with pytest.raises(ValueError):
        query_runbooks(payload)


def test_search_does_not_call_grok(monkeypatch):
    monkeypatch.setattr('runbook_model_answer.ask_xai', lambda *args: pytest.fail('Search must not call xAI'))
    result = query_runbooks({
        'question': 'What should I check if Redis hits maxmemory?',
        'provider': 'xai', 'model': 'grok-4.7',
    })
    assert result['model_answer'] is None
    assert result['rule_answer']


def test_grok_comparison_uses_xai_and_checks_citations(monkeypatch):
    def ask(model, messages):
        assert model == 'grok-4.7'
        assert 'Never' in messages[0]['content'] and 'perform an action' in messages[0]['content']
        return json.dumps({
            'claims': [{'text': 'Human approval is required.', 'citation': 'runbooks/redis_memory.txt:5'}],
            'missing': 'The guide gives no form.',
        })

    monkeypatch.setattr('runbook_model_answer.ask_xai', ask)
    monkeypatch.setattr('runbook_model_answer.ask_ollama', lambda *args: pytest.fail('Grok must not use Ollama'))
    result = query_runbooks({
        'question': 'What approval form must I file before I restart Redis?',
        'compare': True, 'provider': 'xai', 'model': 'grok-4.7',
    })
    assert result['model_provider'] == 'xai'
    assert '[runbooks/redis_memory.txt:5]' in result['model_answer']
    assert result['rule_answer']
    assert result['model_error'] is None


def test_grok_failure_keeps_rules_without_another_provider(monkeypatch):
    monkeypatch.delenv('XAI_API_KEY', raising=False)
    monkeypatch.setattr('runbook_model_answer.ask_ollama', lambda *args: pytest.fail('A Grok failure must not use Ollama'))
    monkeypatch.setattr('agent.make_gemini_summary_client', lambda: pytest.fail('A Grok failure must not use Gemini'))
    result = query_runbooks({
        'question': 'What should I check if Redis hits maxmemory?',
        'compare': True, 'provider': 'xai',
    })
    assert result['passages'] and result['rule_answer']
    assert result['model_answer'] is None
    assert 'MISSING_KEY' in result['model_error']
    assert 'XAI_API_KEY' in result['model_error']


def test_api_key_in_the_request_is_rejected_without_echoing_it():
    secret = 'sentinel-not-a-real-key'
    with pytest.raises(ValueError, match='API key') as caught:
        query_runbooks({'question': 'What should I check?', 'api_key': secret})
    assert secret not in str(caught.value)
