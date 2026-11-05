import json
import sys

import httpx
import pytest

from gemini_client import GeminiClient, GeminiHTTPError


def test_native_gemini_runbook_cli_preserves_question_and_citations(monkeypatch, capsys):
    from runbook_search import main

    def respond(request):
        assert str(request.url) == 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent'
        assert request.headers['x-goog-api-key'] == 'private-test-key'
        assert 'private-test-key' not in str(request.url)
        body = json.loads(request.content)
        assert body['systemInstruction']['parts'][0]['text']
        assert body['generationConfig']['responseMimeType'] == 'application/json'
        assert 'tools' not in body
        evidence = json.loads(body['contents'][0]['parts'][0]['text'])
        assert evidence['question'] == 'What approval form must I file before I restart Redis?'
        assert 'runbooks/redis_memory.txt:5' in evidence['evidence']
        answer = json.dumps({
            'claims': [{'text': 'Human approval is required.', 'citation': 'runbooks/redis_memory.txt:5'}],
            'missing': 'The guide specifies no approval form.',
        })
        return httpx.Response(200, json={'candidates': [{
            'finishReason': 'STOP', 'content': {'parts': [
                {'text': 'private reasoning', 'thought': True}, {'text': answer},
            ]},
        }]})

    monkeypatch.setattr('agent.make_gemini_summary_client',
                        lambda: GeminiClient('private-test-key', transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(sys, 'argv', [
        'runbook_search.py', '--model-answer', '--gemini-model', 'gemini-3.8-flash',
        'What approval form must I file before I restart Redis?',
    ])
    assert main() == 0
    output = capsys.readouterr()
    assert 'guide specifies no approval form' in output.out
    assert '[runbooks/redis_memory.txt:5]' in output.out
    assert 'private' not in output.out + output.err


def test_native_error_retains_status_without_raw_body():
    transport = httpx.MockTransport(lambda _: httpx.Response(503, text='private request details'))
    with GeminiClient('key', transport=transport) as client, pytest.raises(GeminiHTTPError) as error:
        client.generate(model='gemini-3.8-flash', messages=[{'role': 'user', 'content': 'hello'}])
    assert error.value.status_code == 503
    assert 'private' not in str(error.value)


@pytest.mark.parametrize('data', [
    {'candidates': []},
    {'candidates': [{'finishReason': 'MAX_TOKENS'}]},
    {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': 'reasoning', 'thought': True}]}}]},
])
def test_native_incomplete_or_blocked_response_is_rejected(data):
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=data))
    with GeminiClient('key', transport=transport) as client, pytest.raises(ValueError):
        client.generate(model='gemini-3.8-flash', messages=[{'role': 'user', 'content': 'hello'}])
