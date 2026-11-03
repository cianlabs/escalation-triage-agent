"""Replay sanitized versions of the demo responses through the CLI offline."""
import base64

import httpx
import pytest

from agent import main


REPO = 'example/project'
API = f'https://api.github.com/repos/{REPO}'
PATH = '.github/workflows/controlled-failure.yml'
BEFORE_SHA, AFTER_SHA = 'a' * 40, 'b' * 40
BEFORE, AFTER = (f'https://github.com/{REPO}/actions/runs/{number}' for number in (101, 102))


def replay_responses(after_value):
    responses = {}
    for number, url, sha, conclusion in (
        (101, BEFORE, BEFORE_SHA, 'failure'),
        (102, AFTER, AFTER_SHA, 'success'),
    ):
        run_api = f'{API}/actions/runs/{number}'
        responses[run_api] = dict(
            id=number, run_attempt=1, status='completed', conclusion=conclusion,
            head_sha=sha, check_suite_id=number, html_url=url, event='push', path=PATH,
            repository=dict(private=False, full_name=REPO),
            created_at='2026-11-03T00:00:00Z', updated_at='2026-11-03T00:01:00Z',
        )
        responses[f'{run_api}/attempts/1/jobs?per_page=100&page=1'] = dict(
            total_count=1, jobs=[
                dict(id=number, run_id=number, run_attempt=1, name='check-response',
                     status='completed', conclusion=conclusion, check_run_url=f'{API}/check-runs/201',
                     steps=[dict(number=2, name='Check simulated HTTP response',
                                 status='completed', conclusion=conclusion)])
            ],
        )
    responses[f'{API}/check-runs/201'] = dict(
        id=201, name='check-response', head_sha=BEFORE_SHA, check_suite=dict(id=101),
        status='completed', conclusion='failure', output=dict(annotations_count=1),
    )
    responses[f'{API}/check-runs/201/annotations?per_page=100&page=1'] = [
        dict(annotation_level='failure', path='.github', start_line=10, end_line=10,
             message='Simulated HTTP response mismatch. Expected 200, got 503.')
    ]
    for sha, value in ((BEFORE_SHA, 503), (AFTER_SHA, after_value)):
        script = f'          expected=200\n          observed={value}\n'
        responses[f'{API}/contents/{PATH}?ref={sha}'] = dict(
            type='file', path=PATH, encoding='base64',
            content=base64.b64encode(script.encode()).decode(),
        )
    return responses


@pytest.mark.parametrize('scenario', ['matching edit', 'unchanged file', 'rate limited'])
def test_compare_runs_offline(monkeypatch, capsys, scenario):
    responses = replay_responses(after_value=503 if scenario == 'unchanged file' else 200)
    blocked = f'{API}/actions/runs/102/attempts/1/jobs?per_page=100&page=1'
    client = httpx.AsyncClient

    def handler(request):
        assert request.method == 'GET'
        assert 'authorization' not in request.headers
        url = str(request.url)
        if scenario == 'rate limited' and url == blocked:
            return httpx.Response(403, headers={'retry-after': '60'})
        return httpx.Response(200, json=responses[url])

    def offline_client(**kwargs):
        return client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr('workflow_comparison.httpx.AsyncClient', offline_client)
    exit_code = main(['--compare-runs', BEFORE, AFTER])
    output = capsys.readouterr().out
    assert 'Confirmed root cause: none' in output

    if scenario == 'rate limited':
        assert exit_code == 1
        assert output.index('Wait at least 60 seconds') < output.index('Triage summary')
        assert 'Collection: incomplete' in output
        assert 'check-response: failure -> success' not in output
        return

    assert exit_code == 0
    assert 'check-response: failure -> success' in output
    assert 'Simulated HTTP response mismatch. Expected 200, got 503.' in output
    if scenario == 'matching edit':
        assert 'the simulated value changed from 503 to 200' in output
    else:
        assert 'No workflow line changes found.' in output
        assert 'The available evidence does not explain the change.' in output
