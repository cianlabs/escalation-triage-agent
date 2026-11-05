from types import SimpleNamespace

import pytest

from agent import ask_model
from errors import AgentError


@pytest.mark.parametrize('code, expected', [
    ('model_not_found', 'provider code model_not_found'),
    ('arbitrary-secret-text', 'provider code unavailable'),
])
def test_model_error_shows_only_safe_details(code, expected):
    class BadRequestError(Exception):
        status_code = 400

    def reject(**kwargs):
        error = BadRequestError('raw request with arbitrary-secret-text')
        error.code = code
        raise error

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=reject)))
    with pytest.raises(AgentError) as error:
        ask_model(client, [], None)
    assert 'HTTP 400' in str(error.value)
    assert expected in str(error.value)
    assert 'arbitrary-secret-text' not in str(error.value)
    assert 'raw request' not in str(error.value)
    assert error.value.__suppress_context__


def test_bad_request_includes_a_structured_provider_message(monkeypatch):
    secret = 'sentinel-not-a-real-key'
    monkeypatch.setenv('XAI_API_KEY', secret)

    class BadRequestError(Exception):
        status_code = 400
        code = None
        body = {
            'error': 'Argument not supported: max_tool_calls',
        }

        def __str__(self):
            return f'raw request Bearer {secret}'

    def reject(**kwargs):
        raise BadRequestError()

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=reject)))
    with pytest.raises(AgentError) as error:
        ask_model(client, [], None)
    text = str(error.value)
    assert 'HTTP 400' in text
    assert 'provider code unavailable' in text
    assert 'provider message: Argument not supported: max_tool_calls' in text
    assert secret not in text
    assert 'Bearer' not in text
    assert 'raw request' not in text
