import json

import httpx
import pytest

from runbook_line_eval import label_line


def test_line_label_sends_only_question_and_one_source_line():
    def respond(request):
        body = json.loads(request.content)
        assert body['model'] == 'qwen2.5:3b'
        assert json.loads(body['messages'][1]['content']) == {
            'question': 'Which command renews certificates?',
            'line': 'Inspect validity dates.',
        }
        return httpx.Response(200, json={'message': {'content': '{"label":"context"}'}})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert label_line(client, 'qwen2.5:3b', 'Which command renews certificates?',
                          'Inspect validity dates.') == 'context'


def test_unknown_label_is_rejected():
    transport = httpx.MockTransport(lambda _: httpx.Response(
        200, json={'message': {'content': '{"label":"maybe"}'}}))
    with httpx.Client(transport=transport) as client, pytest.raises(ValueError):
        label_line(client, 'qwen2.5:3b', 'Question', 'Line')
