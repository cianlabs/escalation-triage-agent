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
    assert error.value.__suppress_context__
