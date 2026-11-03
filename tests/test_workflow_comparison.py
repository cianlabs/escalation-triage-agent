import pytest

from errors import AgentError
from workflow_comparison import compare_public_runs, render_comparison


def run(outcome, *, consistent=True, repeated=False):
    job = dict(name='check-response', conclusion=outcome, status='completed')
    return dict(assessment='completed_' + outcome, run_url='https://github.com/a/b/actions/runs/1',
                observed_at='now', message='Reported outcome', run={'state': 'unknown'},
                snapshot_consistent=consistent, complete=consistent,
                jobs=dict(state='reported', jobs=[job, job] if repeated else [job]))


def test_reports_changed_job_and_keeps_cause_unconfirmed():
    text = render_comparison(run('failure'), run('success'))
    assert 'check-response: failure -> success' in text
    assert 'Confirmed root cause: none' in text


def test_skips_duplicate_names_and_inconsistent_snapshots():
    assert 'job name is repeated' in render_comparison(run('failure', repeated=True), run('success'))
    assert 'Job comparison unavailable' in render_comparison(run('failure', consistent=False), run('success'))


def test_rejects_same_run_before_fetching():
    url = 'https://github.com/a/b/actions/runs/1'
    with pytest.raises(AgentError, match='two distinct'):
        compare_public_runs(url, url)
