"""Named failures for the escalation agent.

A failure has a short name in CAPITALS, then a plain sentence. Tests and the
terminal both use the name. The name is the thing to search for when something
breaks.

These are crashes and bad inputs. They are not stop reasons. Stop reasons are
how a normal run ends, and they live in agent.py.
"""


class AgentError(Exception):
    """A named, human-readable failure. The message starts with the name."""

    def __init__(self, name, message):
        self.name = name
        super().__init__(f"{name}: {message}")
