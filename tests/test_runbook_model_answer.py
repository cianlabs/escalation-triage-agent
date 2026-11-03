import json

import pytest

from errors import AgentError
from runbook_model_answer import model_answer
from runbook_search import search


def test_partial_answer_names_missing_form_and_cites_approval():
    question = 'What approval form must I file before I restart Redis?'

    def ask(messages):
        evidence = json.loads(messages[1]['content'])['evidence']
        assert 'human approval' in evidence['runbooks/redis_memory.txt:5']
        return json.dumps({
            'claims': [{'text': 'Restart requires human approval.', 'citation': 'runbooks/redis_memory.txt:5'}],
            'missing': 'The guide does not specify a form.',
        })

    output = model_answer(question, search(question), ask)
    assert '[runbooks/redis_memory.txt:5]' in output
    assert 'does not specify a form' in output


def test_rejects_citation_outside_retrieved_passages():
    question = 'What should I check if Redis hits maxmemory?'
    with pytest.raises(AgentError, match='invalid runbook answer or citation'):
        model_answer(question, search(question), lambda _: json.dumps({
            'claims': [{'text': 'Check metrics.', 'citation': 'runbooks/redis_memory.txt:99'}],
            'missing': '',
        }))
