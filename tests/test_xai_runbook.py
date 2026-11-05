import json
import sys
from contextlib import nullcontext
from types import SimpleNamespace

import httpx
import pytest

from errors import AgentError
from runbook_model_answer import XAI_RUNBOOK_MODEL, ask_xai
from runbook_model_eval import FROZEN_COMPARISON, ROOT, capture_metadata, main
from runbook_search import main as search_main

QUESTION = 'What approval form must I file before I restart Redis?'
SECRET = 'sentinel-not-a-real-key'
ANSWER = {
    'claims': [{'text': 'Human approval is required.', 'citation': 'runbooks/redis_memory.txt:5'}],
    'missing': 'The guide provides no approval form.',
}


def install_xai(monkeypatch, create):
    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    monkeypatch.setattr('agent.make_client', lambda timeout=60: nullcontext(client))
    monkeypatch.setattr('agent.make_gemini_summary_client', lambda: pytest.fail('Gemini must not be called'))
    monkeypatch.setattr('agent.make_openai_summary_client', lambda: pytest.fail('OpenAI must not be called'))
    monkeypatch.setattr('runbook_model_answer.ask_ollama', lambda *args, **kwargs: pytest.fail('Ollama must not be called'))
    monkeypatch.setattr('tools.record_simulated_action', lambda *args, **kwargs: pytest.fail('No action is simulated'))
    monkeypatch.setenv('XAI_API_KEY', SECRET)
    return client


def run_search(monkeypatch, argv):
    monkeypatch.setattr(sys, 'argv', ['runbook_search.py', *argv])
    return search_main()


def test_default_runbook_model_is_documented_grok_and_not_the_triage_default():
    from agent import MODEL

    assert XAI_RUNBOOK_MODEL == 'grok-4.7'
    assert MODEL == 'grok-build-0.1'
    assert XAI_RUNBOOK_MODEL != MODEL


def test_grok_request_is_bounded_and_keeps_citations(monkeypatch, capsys):
    seen = {}

    def create(**kwargs):
        seen.update(kwargs)
        assert kwargs['store'] is False
        assert kwargs['max_output_tokens'] == 800
        assert kwargs['max_tool_calls'] == 0
        assert kwargs['tool_choice'] == 'none'
        assert kwargs['temperature'] == 0
        assert kwargs['reasoning'] == {'effort': 'low'}
        # Live Search is removed. Setting search_parameters, even to mode off,
        # fails the Responses request with HTTP 410. Omit the field and do not
        # attach web_search or x_search.
        encoded = json.dumps(kwargs)
        assert 'search_parameters' not in encoded
        assert 'extra_body' not in kwargs
        assert 'tools' not in kwargs
        assert 'web_search' not in encoded
        assert 'x_search' not in encoded
        assert 'live_search' not in encoded
        payload = json.loads(kwargs['input'][1]['content'])
        assert payload['question'] == QUESTION
        assert 'human approval' in payload['evidence']['runbooks/redis_memory.txt:5']
        assert 'Never' in kwargs['input'][0]['content'] and 'perform an action' in kwargs['input'][0]['content']
        assert SECRET not in json.dumps(kwargs)
        return SimpleNamespace(status='completed', output_text=json.dumps(ANSWER))

    install_xai(monkeypatch, create)
    assert run_search(monkeypatch, ['--model-answer', QUESTION]) == 0
    output = capsys.readouterr().out
    assert seen['model'] == 'grok-4.7'
    assert 'The guide provides no approval form.' in output
    assert '[runbooks/redis_memory.txt:5]' in output
    assert SECRET not in output


def test_explicit_model_is_sent_and_a_bad_id_makes_no_call(monkeypatch, capsys):
    def create(**kwargs):
        assert kwargs['model'] == 'grok-4.3'
        return SimpleNamespace(status='completed', output_text=json.dumps(ANSWER))

    install_xai(monkeypatch, create)
    assert run_search(monkeypatch, ['--model-answer', '--xai-model', 'grok-4.3', QUESTION]) == 0

    def unexpected(**kwargs):
        pytest.fail('An invalid model id must not call xAI')

    install_xai(monkeypatch, unexpected)
    assert run_search(monkeypatch, ['--model-answer', '--xai-model', '../grok', QUESTION]) == 1
    captured = capsys.readouterr()
    assert 'MODEL_ERROR' in captured.err
    assert 'No other model provider was called.' in captured.out
    assert SECRET not in captured.out + captured.err


def test_missing_key_does_not_build_a_client_or_switch_provider(monkeypatch, capsys):
    monkeypatch.delenv('XAI_API_KEY', raising=False)
    monkeypatch.setattr('agent.make_client', lambda **kwargs: pytest.fail('missing key must not build a client'))
    monkeypatch.setattr('agent.make_gemini_summary_client', lambda: pytest.fail('Gemini must not be called'))
    monkeypatch.setattr('agent.make_openai_summary_client', lambda: pytest.fail('OpenAI must not be called'))
    assert run_search(monkeypatch, ['--model-answer', '--xai-model', 'grok-4.7', QUESTION]) == 1
    captured = capsys.readouterr()
    assert 'MISSING_KEY' in captured.err
    assert 'XAI_API_KEY' in captured.err
    assert 'Rule-based fallback' in captured.out
    assert 'No other model provider was called.' in captured.out
    assert 'human approval' in captured.out


def test_provider_error_hides_the_key_and_retries_only_transient_status(monkeypatch, capsys):
    class Denied(Exception):
        status_code = 400
        code = 'invalid_request_error'

        def __str__(self):
            return SECRET

    calls = []
    delays = []

    def create(**kwargs):
        calls.append(kwargs['model'])
        raise Denied()

    install_xai(monkeypatch, create)
    monkeypatch.setattr('runbook_model_answer.time.sleep', delays.append)
    assert run_search(monkeypatch, ['--model-answer', QUESTION]) == 1
    captured = capsys.readouterr()
    assert calls == ['grok-4.7']
    assert delays == []
    assert 'HTTP 400' in captured.err
    assert 'provider code invalid_request_error' in captured.err
    assert SECRET not in captured.out + captured.err
    assert 'No other model provider was called.' in captured.out


@pytest.mark.parametrize('recovers', [True, False])
def test_xai_retries_http_503_once(monkeypatch, capsys, recovers):
    class Unavailable(Exception):
        status_code = 503

        def __str__(self):
            return SECRET

    calls = []
    delays = []

    def create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1 or not recovers:
            raise Unavailable()
        return SimpleNamespace(status='completed', output_text=json.dumps(ANSWER))

    install_xai(monkeypatch, create)
    monkeypatch.setattr('runbook_model_answer.time.sleep', delays.append)
    result = run_search(monkeypatch, ['--model-answer', QUESTION])
    captured = capsys.readouterr()
    assert len(calls) == 2
    assert delays == [1]
    assert SECRET not in captured.out + captured.err
    if recovers:
        assert result == 0
        assert '[runbooks/redis_memory.txt:5]' in captured.out
    else:
        assert result == 1
        assert 'still unavailable after one retry (HTTP 503)' in captured.err
        assert 'No other provider was called.' in captured.err


def test_rejected_key_and_incomplete_answer_stop_without_fallback_provider(monkeypatch, capsys):
    class AuthenticationError(Exception):
        def __str__(self):
            return SECRET

    def create(**kwargs):
        raise AuthenticationError()

    install_xai(monkeypatch, create)
    assert run_search(monkeypatch, ['--model-answer', QUESTION]) == 1
    captured = capsys.readouterr()
    assert 'BAD_KEY' in captured.err
    assert SECRET not in captured.out + captured.err

    def incomplete(**kwargs):
        return SimpleNamespace(status='incomplete', output_text='{"claims":[]')

    install_xai(monkeypatch, incomplete)
    assert run_search(monkeypatch, ['--model-answer', QUESTION]) == 1
    captured = capsys.readouterr()
    assert 'incomplete' in captured.err
    assert 'Gemini' not in captured.err


def test_bad_citation_is_rejected(monkeypatch, capsys):
    def create(**kwargs):
        return SimpleNamespace(status='completed', output_text=json.dumps({
            'claims': [{'text': 'Check metrics.', 'citation': 'runbooks/redis_memory.txt:99'}],
            'missing': '',
        }))

    install_xai(monkeypatch, create)
    assert run_search(monkeypatch, ['--model-answer', QUESTION]) == 1
    assert 'invalid runbook answer or citation' in capsys.readouterr().err


def test_explicit_gemini_remains_optional(monkeypatch, capsys):
    def create(*, model, messages, response_format):
        assert model == 'gemini-3.1-flash-lite'
        assert response_format == {'type': 'json_object'}
        message = SimpleNamespace(content=json.dumps(ANSWER))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    monkeypatch.setattr('agent.make_gemini_summary_client', lambda: nullcontext(
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))))
    monkeypatch.setattr('agent.make_client', lambda **kwargs: pytest.fail('Gemini mode must not call xAI'))
    assert run_search(monkeypatch, ['--model-answer', '--gemini-model', 'gemini-3.1-flash-lite', QUESTION]) == 0
    assert '[runbooks/redis_memory.txt:5]' in capsys.readouterr().out


def test_capture_metadata_records_the_frozen_set_without_calling_xai(monkeypatch):
    def client(**kwargs):
        class LocalOnly:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, url):
                assert 'api.x.ai' not in url
                raise httpx.ConnectError('local embeddings are offline in this test')

        return LocalOnly()

    monkeypatch.setattr('runbook_model_eval.httpx.Client', client)
    monkeypatch.setenv('XAI_API_KEY', SECRET)
    questions = json.loads((ROOT / FROZEN_COMPARISON).read_text())
    metadata = capture_metadata(questions, 'grok-4.7', provider='xai', questions_path=ROOT / FROZEN_COMPARISON)
    encoded = json.dumps(metadata)
    assert metadata['provider'] == 'xai'
    assert metadata['model'] == 'grok-4.7'
    assert metadata['dataset'] == FROZEN_COMPARISON
    assert metadata['dataset_id'] == 'semantic-holdout-t01-t12'
    assert metadata['dataset_sha256'] == metadata['questions_sha256']
    assert len(metadata['dataset_sha256']) == 64
    assert metadata['max_model_calls'] == 24
    assert metadata['max_attempts'] == 2
    assert metadata['timeout_seconds'] == 90
    assert metadata['max_output_tokens'] == 800
    assert metadata['search'] == 'off'
    assert metadata['api'] == 'https://api.x.ai/v1/responses'
    assert metadata['model_digest'] == 'remote-model-unverified'
    assert SECRET not in encoded
    assert 'expected' not in encoded


def test_xai_capture_uses_the_same_question_text_and_saves_provider(tmp_path, monkeypatch, capsys):
    questions = [
        dict(id='T01', question='Inspect the cache?', expected='redis_memory.txt'),
        dict(id='T02', question='How do I calculate compound interest?', expected=None),
    ]
    path = tmp_path / 'questions.json'
    path.write_text(json.dumps(questions))
    output = tmp_path / 'grok.json'
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        assert 'redis_memory.txt' not in command
        assert '--ollama-model' not in command
        assert '--gemini-model' not in command
        assert command[-1] == questions[len(commands) - 1]['question']
        return SimpleNamespace(returncode=0, stdout='A cited response\n', stderr='')

    monkeypatch.setattr('runbook_model_eval.subprocess.run', run)
    monkeypatch.setenv('XAI_API_KEY', SECRET)
    assert main(['--xai-model', 'grok-4.7', '--questions', str(path), '--output', str(output)]) == 0
    saved = output.read_text()
    data = json.loads(saved)
    assert [command[command.index('--xai-model') + 1] for command in commands] == ['grok-4.7', 'grok-4.7']
    assert data['metadata']['provider'] == 'xai'
    assert data['metadata']['dataset_id'] == 'custom'
    assert data['results'][0]['provider'] == 'xai'
    assert 'Provider — xai' in capsys.readouterr().out
    assert SECRET not in saved
    assert 'redis_memory.txt' not in saved


def test_invalid_capture_model_does_not_start_questions(monkeypatch, capsys, tmp_path):
    questions = tmp_path / 'questions.json'
    questions.write_text(json.dumps([dict(id='T01', question='Inspect the cache?', expected=None)]))

    def unexpected(*args, **kwargs):
        pytest.fail('An invalid model must not start a question')

    monkeypatch.setattr('runbook_model_eval.subprocess.run', unexpected)
    assert main(['--xai-model', 'grok 4', '--questions', str(questions), '--output', str(tmp_path / 'out.json')]) == 1
    assert 'model id' in capsys.readouterr().err


def test_ask_xai_rejects_a_direct_bad_id_before_the_client(monkeypatch):
    monkeypatch.setattr('agent.make_client', lambda **kwargs: pytest.fail('bad id must not build a client'))
    with pytest.raises(AgentError, match='model id'):
        ask_xai('grok/4', [])
