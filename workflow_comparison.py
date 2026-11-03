"""Compare reported job outcomes without inferring what changed in the code."""
import asyncio
from collections import defaultdict

import httpx

from errors import AgentError
from workflow_error_details import clip_text
from workflow_inspection import inspect_run, parse_run_url, render_run


async def _compare(before, after):
    async with httpx.AsyncClient(trust_env=False) as client:
        first, second = await asyncio.gather(inspect_run(client, before), inspect_run(client, after))
    return first, second


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


def render_comparison(before, after):
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
                  '', 'Before details', render_run(before), '', 'After details', render_run(after)])
    return '\n'.join(lines)
