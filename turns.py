"""The note a model hands the loop.

Both the practice model and the real model return a ModelTurn. The loop
does not care which one built it. A turn is either a tool call or plain
text. Plain text is never an approval.
"""

from dataclasses import dataclass, field


@dataclass
class ModelTurn:
    """One decision from a model.

    `kind` is "tool" or "text".
    `arguments` may contain a key named approved. That key is not permission.
    The loop deletes it and still asks a human.
    """

    kind: str
    name: str = ""
    arguments: dict = field(default_factory=dict)
    text: str = ""
    thought: str = ""
    call_id: str = ""


def tool_turn(name, arguments, thought):
    """A tool call, with a short thought so the step is visible in the terminal."""
    return ModelTurn(kind="tool", name=name, arguments=dict(arguments), thought=thought)
