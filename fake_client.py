"""Fake client for testing the live model path without network calls."""

import json
from types import SimpleNamespace


def tool_reply(name, arguments, call_id):
    call = SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )
    return SimpleNamespace(content="noted", tool_calls=[call])


class FakeClient:
    """Stands in for the xAI client during testing. Returns scripted replies and records calls."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.replies:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="No more scripted replies.", tool_calls=[]
                        )
                    )
                ]
            )
        return SimpleNamespace(choices=[SimpleNamespace(message=self.replies.pop(0))])
