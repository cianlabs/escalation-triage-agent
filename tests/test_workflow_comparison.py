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


def test_summary_connects_matching_simulated_error_and_diff():
    before = run('failure')
    before['error_details'] = dict(state='reported', message='Reported error', jobs=[
        dict(job_name='check-response', steps=dict(state='reported', steps=[]),
             annotations=dict(state='reported', annotations=[
                 dict(level='failure', path='.github', start_line=10, text_truncated=False,
                      message='Simulated HTTP response mismatch. Expected 200, got 503.')
             ]))
    ])
    diff = ['  |           expected=200', '  | -          observed=503', '  | +          observed=200']
    text = render_comparison(before, run('success'), diff)
    assert 'the simulated value changed from 503 to 200' in text
    assert 'Confirmed root cause: none' in text
    unchanged = render_comparison(before, run('success'), ['No workflow line changes found.'])
    assert 'The available evidence does not explain the change.' in unchanged
    assert 'the simulated value changed' not in unchanged


@pytest.mark.parametrize('headers, expected', [
    ({'x-ratelimit-remaining': '0', 'x-ratelimit-reset': '1800000000'},
     'Retry after 2027-01-15 08:00:00 UTC.'),
    ({}, 'GitHub refused access (HTTP 403). The reason is unknown.'),
])
def test_access_guidance_precedes_incomplete_comparison(headers, expected):
    import asyncio

    import httpx

    from workflow_inspection import inspect_run

    async def inspect():
        transport = httpx.MockTransport(lambda request: httpx.Response(403, headers=headers))
        async with httpx.AsyncClient(transport=transport) as client:
            return await inspect_run(client, 'https://github.com/a/b/actions/runs/1')

    before = asyncio.run(inspect())
    assert not before['complete']
    text = render_comparison(before, run('success'))
    assert text.index(expected) < text.index('Triage summary')
    assert 'Job comparison unavailable' in text
