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


def replay_responses(after_value, *, before_suffix="", after_suffix=""):
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
    for sha, value, suffix in ((BEFORE_SHA, 503, before_suffix), (AFTER_SHA, after_value, after_suffix)):
        script = f'          expected=200\n          observed={value}\n{suffix}'
        responses[f'{API}/contents/{PATH}?ref={sha}'] = dict(
            type='file', path=PATH, encoding='base64',
            content=base64.b64encode(script.encode()).decode(),
        )
    return responses


def install_replay(monkeypatch, responses, *, rate_limited=False, missing_file=False):
    blocked = f'{API}/actions/runs/102/attempts/1/jobs?per_page=100&page=1'
    client = httpx.AsyncClient

    def handler(request):
        assert request.method == 'GET'
        assert 'authorization' not in request.headers
        url = str(request.url)
        if rate_limited and url == blocked:
            return httpx.Response(403, headers={'retry-after': '60'})
        if missing_file and url == f'{API}/contents/{PATH}?ref={AFTER_SHA}':
            return httpx.Response(404)
        return httpx.Response(200, json=responses[url])

    def offline_client(**kwargs):
        return client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr('workflow_comparison.httpx.AsyncClient', offline_client)


@pytest.mark.parametrize('scenario', ['matching edit', 'unchanged file', 'rate limited'])
def test_compare_runs_offline(monkeypatch, capsys, scenario):
    responses = replay_responses(after_value=503 if scenario == 'unchanged file' else 200)
    install_replay(monkeypatch, responses, rate_limited=scenario == 'rate limited')
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


def test_comparison_summary_baseline(monkeypatch, capsys):
    # Expected summaries are fixed before invoking the CLI.
    recovery = 'check-response failed before and passed after.'
    cautious = 'The available evidence does not explain the change.'
    cases = [
        ('Matching edit', replay_responses(200),
         'GitHub reported expected 200, got 503. The workflow diff shows the '
         'simulated value changed from 503 to 200, matching the expected value.'),
        ('Comment only', replay_responses(503, after_suffix='          # Clarify the check\n'),
         cautious),
        ('Timeout and dependency', replay_responses(
            503, before_suffix='          timeout=10\n          dependency_version=1\n',
            after_suffix='          timeout=30\n          dependency_version=2\n'),
         cautious),
    ]
    # Keep the real client constructor available for each independent replay.
    results = []
    for name, responses, expected in cases:
        with monkeypatch.context() as patch:
            install_replay(patch, responses)
            exit_code = main(['--compare-runs', BEFORE, AFTER])
        output = capsys.readouterr().out
        summary = output.partition('Triage summary\n')[2].splitlines()
        outcome = exit_code == 0 and 'check-response: failure -> success' in output
        explanation = bool(summary) and summary[0] == f'{recovery} {expected}'
        results.append((name, outcome, explanation))

    print('\nCase | Outcome | Explanation')
    print('--- | --- | ---')
    for name, outcome, explanation in results:
        print(f'{name} | {int(outcome)}/1 | {int(explanation)}/1')
    print(f'Total | {sum(row[1] for row in results)}/3 | {sum(row[2] for row in results)}/3')
    assert all(outcome and explanation for _, outcome, explanation in results), results


def test_harder_summary_baseline(monkeypatch, capsys):
    two_jobs = replay_responses(200)
    for run_id in (101, 102):
        jobs = two_jobs[f'{API}/actions/runs/{run_id}/attempts/1/jobs?per_page=100&page=1']
        jobs['total_count'] = 2
        jobs['jobs'].append(dict(jobs['jobs'][0], id=run_id + 1000, name='check-cache',
                                 check_run_url=f'{API}/check-runs/202'))
    two_jobs[f'{API}/check-runs/202'] = dict(two_jobs[f'{API}/check-runs/201'],
                                           id=202, name='check-cache', output=dict(annotations_count=0))
    two_jobs[f'{API}/check-runs/202/annotations?per_page=100&page=1'] = []

    cases = [
        ('Two recoveries', two_jobs, False, ('check-response', 'check-cache'),
         'check-cache failed before and passed after. The available evidence does not explain the change.\n'
         'check-response failed before and passed after. GitHub reported expected 200, got 503. '
         'The workflow diff shows the simulated value changed from 503 to 200, matching the expected value.'),
        ('Matching numbers in a comment', replay_responses(
            503, before_suffix='          # expected=200\n          # observed=503\n',
            after_suffix='          # expected=200\n          # observed=200\n'),
         False, ('check-response',),
         'check-response failed before and passed after. The available evidence does not explain the change.'),
        ('Missing workflow file', replay_responses(200), True, ('check-response',),
         'check-response failed before and passed after. The workflow file comparison is unavailable.'),
    ]
    results = []
    report = []
    for name, responses, missing, jobs, expected in cases:
        with monkeypatch.context() as patch:
            install_replay(patch, responses, missing_file=missing)
            main(['--compare-runs', BEFORE, AFTER])
        output = capsys.readouterr().out
        summary = output.partition('Triage summary\n')[2].partition('\n\n')[0]
        outcome = all(f'- {job}: failure -> success' in output for job in jobs)
        results.append((outcome, summary == expected))
        report.append(f'{name} | outcome {int(outcome)}/1 | explanation {int(summary == expected)}/1')
        report.append(f'  Summary: {summary}')

    print('\n'.join(report))
    # Check the same three cases against the revised summary.
    assert results == [(True, True)] * 3


def test_opt_in_model_summary_uses_public_evidence_without_tools(monkeypatch, capsys):
    from contextlib import nullcontext
    from types import SimpleNamespace
    import json

    install_replay(monkeypatch, replay_responses(200))
    def create(*, model, input, store):
        assert model == "grok-build-0.1"
        assert store is False
        evidence = json.loads(input[1]['content'])
        assert 'Expected 200, got 503' in evidence['before']
        assert 'completed_success' in evidence['after']
        assert 'observed=200' in evidence['diff']
        return SimpleNamespace(output_text=json.dumps(dict(
            summary='The check recovered after the simulated value changed.',
            sources=['before', 'after', 'diff'],
        )))

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    monkeypatch.setattr('agent.make_client', lambda: nullcontext(client))
    assert main(['--compare-runs', BEFORE, AFTER, '--model-summary']) == 0
    output = capsys.readouterr().out
    assert output.index('Triage summary') < output.index('Experimental model summary')
    assert f'Source: {BEFORE}' in output
    assert f'Source: https://github.com/{REPO}/blob/{AFTER_SHA}/{PATH}' in output


def test_saved_demo_replays_without_github(monkeypatch, capsys):
    def unexpected_call(*args, **kwargs):
        pytest.fail('Replay must not call GitHub')

    monkeypatch.setattr('workflow_comparison.compare_public_runs', unexpected_call)
    assert main(['--replay-comparison']) == 0
    output = capsys.readouterr().out
    assert 'Replaying saved GitHub evidence.' in output
    assert 'check-response: failure -> success' in output
    assert 'the simulated value changed from 503 to 200' in output


def test_openai_summary_replays_saved_evidence(monkeypatch, capsys):
    import json
    from contextlib import nullcontext
    from types import SimpleNamespace

    def create(*, model, input, store):
        assert model == 'gpt-6-luna'
        assert store is False
        assert 'Expected 200, got 503' in json.loads(input[1]['content'])['before']
        return SimpleNamespace(output_text='{"summary":"The check recovered.","sources":["after"]}')

    def unexpected(*args, **kwargs):
        pytest.fail('OpenAI replay must not call GitHub or xAI')

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    monkeypatch.setattr('agent.make_openai_summary_client', lambda: nullcontext(client))
    monkeypatch.setattr('agent.make_client', unexpected)
    monkeypatch.setattr('workflow_comparison.compare_public_runs', unexpected)
    assert main(['--replay-comparison', '--model-summary', '--summary-provider', 'openai']) == 0
    assert 'The check recovered.' in capsys.readouterr().out


def test_gemini_summary_replays_saved_evidence(monkeypatch, capsys):
    import json
    from contextlib import nullcontext
    from types import SimpleNamespace

    def create(*, model, messages, response_format):
        assert response_format == {"type": "json_object"}
        assert model == 'gemini-3.1-flash-lite'
        assert 'Expected 200, got 503' in json.loads(messages[1]['content'])['before']
        message = SimpleNamespace(content='{"summary":"The check recovered.","sources":["after"]}')
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    def unexpected(*args, **kwargs):
        pytest.fail('Gemini replay must use saved evidence and only the selected provider')

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr('agent.make_gemini_summary_client', lambda: nullcontext(client))
    monkeypatch.setattr('agent.make_client', unexpected)
    monkeypatch.setattr('agent.make_openai_summary_client', unexpected)
    monkeypatch.setattr('workflow_comparison.compare_public_runs', unexpected)
    assert main(['--replay-comparison', '--model-summary', '--summary-provider', 'gemini']) == 0
    assert 'The check recovered.' in capsys.readouterr().out


def test_qwen_timeout_replays_without_github(monkeypatch, capsys):
    def unexpected_call(*args, **kwargs):
        pytest.fail('Replay must not call GitHub')

    monkeypatch.setattr('workflow_comparison.compare_public_runs', unexpected_call)
    assert main(['--replay-comparison', 'qwen-timeout']) == 0
    output = capsys.readouterr().out
    assert 'E2E Test - macOS - shard 1/2: failure -> success' in output
    assert 'ETIMEDOUT' in output
    assert 'No workflow line changes found.' in output
