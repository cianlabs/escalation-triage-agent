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
                lines.append(f"- {' '.join(clip_text(name, 250)[0].split())}: {first[name][0]} -> {second[name][0]}")
        if len(lines) == section_start:
            lines.append('No changes found among jobs with matching names.')
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
