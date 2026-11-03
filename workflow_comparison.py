"""Compare reported job outcomes and read commit-pinned workflow versions."""
import asyncio
import base64
import difflib
import re
from itertools import islice
from collections import defaultdict

import httpx

from errors import AgentError
from workflow_error_details import clip_text
from workflow_inspection import get_json, inspect_run, parse_run_url, render_run


async def _compare(before, after):
    async with httpx.AsyncClient(trust_env=False) as client:
        first, second = await asyncio.gather(inspect_run(client, before), inspect_run(client, after))
        diff = await workflow_diff(client, first, second)
    return first, second, diff


def compare_public_runs(before, after):
    first, second = map(parse_run_url, (before, after))
    repository = lambda target: (target['owner'].casefold(), target['repo'].casefold())
    if repository(first) != repository(second) or first['id'] == second['id']:
        raise AgentError('BAD_TOOL_ARGS', 'Provide two distinct run URLs from the same repository.')
    return asyncio.run(_compare(first['html_url'], second['html_url']))


def _job_outcomes(result):
    outcomes = defaultdict(list)
    for job in result['jobs']['jobs']:
        outcomes[job['name']].append(job['conclusion'] or job['status'])
    return outcomes


def render_comparison(before, after, diff=()):
    lines = ['Public GitHub Actions run comparison',
             f"Before: {before['assessment']} | {before['run_url']}",
             f"After:  {after['assessment']} | {after['run_url']}", '', 'Changed job outcomes:']
    recovered = []
    if not all(result.get('snapshot_consistent') and result.get('jobs', {}).get('state') == 'reported'
               for result in (before, after)):
        lines.append('Job comparison unavailable because a job list is incomplete or changed during collection.')
    else:
        first, second = map(_job_outcomes, (before, after))
        section_start = len(lines)
        for name in sorted(first.keys() & second.keys()):
            if len(first[name]) != 1 or len(second[name]) != 1:
                lines.append(f"- {' '.join(clip_text(name, 250)[0].split())}: skipped because the job name is repeated.")
            elif first[name] != second[name]:
                if first[name] == ['failure'] and second[name] == ['success']:
                    recovered.append(name)
                lines.append(f"- {' '.join(clip_text(name, 250)[0].split())}: {first[name][0]} -> {second[name][0]}")
        if len(lines) == section_start:
            lines.append('No changes found among jobs with matching names.')
    lines[3:3] = ['', 'Triage summary', _triage_summary(before, recovered, diff)]
    lines.extend(['', 'Jobs are matched by name. A changed outcome alone does not explain why it changed.',
                  '', 'Workflow file comparison', *diff, '', 'Before details', render_run(before), '', 'After details', render_run(after)])
    return '\n'.join(lines)


async def workflow_diff(client, before, after):
    runs = [result['run'] for result in (before, after)]
    path = runs[0].get('workflow_path')
    unavailable = ['Workflow file comparison unavailable. Run evidence is shown below.']
    if not path or not re.fullmatch(r'\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml', path):
        return unavailable
    if not all(result.get('snapshot_consistent') and run.get('event') == 'push'
               and run.get('workflow_path') == path and run.get('head_sha')
               for result, run in zip((before, after), runs)):
        return unavailable

    target = parse_run_url(before['run_url'])
    repo = f"{target['owner']}/{target['repo']}"
    url = f'https://api.github.com/repos/{repo}/contents/{path}'
    shas = [run['head_sha'] for run in runs]
    responses = await asyncio.gather(*(get_json(client, url, {'ref': sha}) for sha in shas))
    links = [f'{label}: https://github.com/{repo}/blob/{sha}/{path}'
             for label, sha in zip(('Before file', 'After file'), shas)]
    try:
        texts = [_workflow_text(response.get('data'), path) for response in responses]
    except (ValueError, UnicodeError):
        return [*links, *unavailable]

    changes = difflib.unified_diff(*(text.splitlines() for text in texts),
                                   fromfile='before', tofile='after', lineterm='', n=1)
    lines = list(islice(changes, 81))
    if not lines:
        return [*links, 'No workflow line changes found.']
    return [*links, 'Workflow changes are evidence to review. Confirmed root cause remains none.',
            *(f'  | {clip_text(line, 500)[0]}' for line in lines[:80]),
            *(['Additional diff lines omitted.'] if len(lines) > 80 else [])]


def _workflow_text(data, path):
    if (not isinstance(data, dict) or data.get('type') != 'file' or data.get('path') != path
            or data.get('encoding') != 'base64' or not isinstance(data.get('content'), str)
            or len(data['content']) > 90_000):
        raise ValueError('Unavailable or oversized workflow file')
    return base64.b64decode(''.join(data['content'].split()), validate=True).decode('utf-8')


def _triage_summary(before, recovered, diff):
    if not recovered:
        return 'No uniquely matched job was shown to change from failure to success.'
    names = ', '.join(' '.join(clip_text(name, 250)[0].split()) for name in recovered[:3])
    subject = names if len(recovered) <= 3 else f'{names} and {len(recovered) - 3} more'
    outcome = f'{subject} failed before and passed after.'
    fallback = f'{outcome} The available evidence does not explain the change.'
    if len(recovered) != 1:
        return fallback

    # Require the reported mismatch and both sides of the exact demo-style edit.
    for job in before.get('error_details', {}).get('jobs', []):
        if job['job_name'] != recovered[0]:
            continue
        for annotation in job['annotations']['annotations']:
            if annotation['level'] != 'failure' or annotation.get('text_truncated'):
                continue
            match = re.fullmatch(r'Simulated HTTP response mismatch\. Expected ([0-9]{3}), got ([0-9]{3})\.',
                                 annotation['message'].strip())
            if match:
                expected, observed = match.groups()
                if expected != observed and _shows_response_edit(diff, expected, observed):
                    return (f'{outcome} GitHub reported expected {expected}, got {observed}. '
                            f'The workflow diff shows the simulated value changed from {observed} '
                            f'to {expected}, matching the expected value.')
    return fallback


def _shows_response_edit(diff, expected, observed):
    for context, removed, added in zip(diff, diff[1:], diff[2:]):
        if (context.startswith('  |  ') and context[5:].strip() == f'expected={expected}'
                and removed.startswith('  | -') and removed[5:].strip() == f'observed={observed}'
                and added.startswith('  | +') and added[5:].strip() == f'observed={expected}'):
            return True
    return False
