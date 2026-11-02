"""Synthetic fixtures for the CLI; verified incidents live in incidents/public.jsonl.

Historical INC-prefixed ids are retained for saved-state compatibility. Those ids
are not a claim that fixture logs, deploys, versions or customers are real.
"""
import copy
import json
from pathlib import Path
from errors import AgentError

PRACTICE_ESCALATIONS = {
    row['id']: row for row in json.loads(
        (Path(__file__).resolve().parent / 'fixtures/synthetic.json').read_text()
    )
}


def list_escalations():
    """Synthetic CLI workflow fixtures, copied so callers cannot mutate them."""
    return copy.deepcopy(list(PRACTICE_ESCALATIONS.values()))


def list_real_incidents():
    """The verified public benchmark, without fabricated logs or deployments."""
    from incident_data import load_incidents
    return load_incidents()


def get_escalation(escalation_id):
    """One synthetic CLI fixture. Public evaluation inputs use a separate loader."""
    if escalation_id in PRACTICE_ESCALATIONS:
        return copy.deepcopy(PRACTICE_ESCALATIONS[escalation_id])
    known = ', '.join(PRACTICE_ESCALATIONS)
    raise AgentError('UNKNOWN_ESCALATION', f'no practice escalation named {escalation_id!r}. Known ids: {known}.')


SAMPLE_ID = 'INC-CLOUDFLARE-01'
