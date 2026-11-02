"""Concurrent read-only evidence checks with independent deadlines.

The supplied readers must be cooperative async functions. Included samples are
entirely synthetic and never connect to systems, models or external services.
"""
import asyncio
from dataclasses import dataclass
import math

from errors import AgentError
from evidence_ranker import investigate, render_investigation, validate_evidence


@dataclass(frozen=True)
class EvidenceCheck:
    name: str
    read: object
    timeout_seconds: float = 1.0
    data_kind: str = "unspecified"


def validate_checks(checks):
    if not isinstance(checks, (list, tuple)) or not checks:
        raise AgentError('BAD_SETTINGS', 'Provide at least one evidence check.')
    names = set()
    for check in checks:
        if not isinstance(check, EvidenceCheck) or not isinstance(check.name, str) or not check.name.strip():
            raise AgentError('BAD_SETTINGS', 'Each check needs a nonempty source name.')
        if check.name in names or '::' in check.name:
            raise AgentError('BAD_SETTINGS', 'Check names must be unique and cannot contain ::.')
        names.add(check.name)
        if check.data_kind not in ('unspecified', 'synthetic', 'public_status'):
            raise AgentError('BAD_SETTINGS', 'Unknown source data kind.')
        if not callable(check.read):
            raise AgentError('BAD_SETTINGS', 'Each check needs an async reader function.')
        if isinstance(check.timeout_seconds, bool) or not isinstance(check.timeout_seconds, (int, float)) or not math.isfinite(check.timeout_seconds) or check.timeout_seconds <= 0:
            raise AgentError('BAD_SETTINGS', 'Each timeout must be a finite positive number of seconds.')


async def _run_check(check):
    loop = asyncio.get_running_loop()
    started = loop.time()
    result = dict(name=check.name, evidence=[], timeout_seconds=check.timeout_seconds, data_kind=check.data_kind)
    try:
        raw = await asyncio.wait_for(check.read(), timeout=check.timeout_seconds)
    except asyncio.CancelledError:
        if asyncio.current_task().cancelling():
            raise  # caller cancelled collection; TaskGroup cancels and drains siblings
        result.update(status='cancelled', message='The source cancelled its check. Its result is unknown.')
    except TimeoutError:
        result.update(status='timeout', message='The check did not finish before its deadline. Its result is unknown.')
    except Exception as exc:
        # Exception messages can contain secrets or request details. Keep only
        # the class name; failure is never translated into a healthy signal.
        result.update(status='failed', message=f'Check failed ({type(exc).__name__}). No result is available.')
    else:
        try:
            rows = validate_evidence(raw)
        except AgentError:
            result.update(status='invalid_result', message='The check returned malformed or duplicate evidence. No rows from it were used.')
        else:
            result.update(status='ok' if rows else 'empty',
                          message='Observations collected; this does not imply service health.' if rows else
                          'The check finished without observations. This is not evidence that the service is healthy.',
                          evidence=[dict(id=f'{check.name}::{row["id"]}',
                                         source=f'{check.name}: {row["source"]}',
                                         observation=row['observation'], data_kind=check.data_kind,
                                         **{key: original[key] for key in ('observed_at', 'source_updated_at', 'source_url', 'status_indicator', 'reported_description') if key in original})
                                    for row, original in zip(rows, raw)])
    result['elapsed_ms'] = max(0, round((loop.time()-started)*1000))
    return result


async def collect_evidence(checks):
    """Start all checks together; cancel and drain children if the caller cancels."""
    validate_checks(checks)
    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(_run_check(check), name=f'evidence:{check.name}') for check in checks]
    # Stable configured-source order, independent of completion order.
    sources = [task.result() for task in tasks]
    missing = [s['name'] for s in sources if s['status'] not in ('ok', 'empty')]
    completed = len(sources)-len(missing)
    status = 'complete' if not missing else ('partial' if completed else 'failed')
    return dict(status=status, sources=sources, missing_sources=missing,
                evidence=[row for source in sources for row in source['evidence']])


async def collect_and_investigate(symptom, checks, *, allowed_data_kinds=None):
    # Validate before starting readers, even when the symptom is unusable.
    investigate(dict(symptom=symptom, evidence=[]))
    collection = await collect_evidence(checks)
    selected = [row for row in collection['evidence'] if allowed_data_kinds is None or row['data_kind'] in allowed_data_kinds]
    result = investigate(dict(symptom=symptom, evidence=selected))
    result['evidence'] = [dict(row) for row in selected]
    result['excluded_evidence_ids'] = [row['id'] for row in collection['evidence'] if allowed_data_kinds is not None and row['data_kind'] not in allowed_data_kinds]
    if result['excluded_evidence_ids']:
        result['message'] = 'Practice observations are shown separately and excluded from this investigation. '+result['message']
    result['collection'] = collection
    result['collection_incomplete'] = bool(collection['missing_sources'])
    if result['collection_incomplete']:
        missing = ', '.join(collection['missing_sources'])
        note = 'Evidence collection is incomplete. Unavailable checks: '+missing+'.'
        result['message'] = note+' '+result['message']
        for hypothesis in result['hypotheses']:
            hypothesis['missing_evidence'].append(note)
        result['next_checks'].insert(0, 'Retry or independently inspect the unavailable checks: '+missing+'.')
    return result


def simulated_checks(scenario='complete'):
    """Three synthetic async readers; sleeping represents waiting, not real I/O."""
    if scenario not in ('complete', 'partial', 'failed'):
        raise AgentError('BAD_SETTINGS', 'Unknown simulated collection scenario.')

    async def recent_errors():
        await asyncio.sleep(0.01)
        if scenario == 'failed':
            raise RuntimeError('simulated errors source failure')
        return [dict(id='1', source='synthetic network diagnostic',
                     observation='The routing table is missing a route to the application subnet.')]

    async def recent_changes():
        await asyncio.sleep(0.01)
        if scenario in ('partial', 'failed'):
            raise RuntimeError('simulated changes source failure')
        return [dict(id='1', source='synthetic update record',
                     observation='An operating system update completed before connectivity was lost.')]

    async def service_health():
        if scenario in ('partial', 'failed'):
            await asyncio.sleep(3600)  # wait_for cancels this cooperative wait
        await asyncio.sleep(0.01)
        return [dict(id='1', source='synthetic service probe',
                     observation='The dashboard endpoint is unavailable.')]

    return [EvidenceCheck('recent_errors', recent_errors, 0.1, data_kind='synthetic'),
            EvidenceCheck('recent_changes', recent_changes, 0.1, data_kind='synthetic'),
            EvidenceCheck('service_health', service_health, 0.1, data_kind='synthetic')]


def run_simulated_collection(scenario):
    return asyncio.run(collect_and_investigate('Our dashboard and alerts stopped working.', simulated_checks(scenario)))


def render_collection(result):
    collection = result['collection']
    heading = ('Mixed demonstration: GitHub status is live; recent errors and changes are synthetic.'
               if result.get('collection_mode') == 'github_status' else
               'Synthetic evidence collection. No real systems were contacted.')
    lines = [heading,
             'Collection: '+collection['status'], '']
    for source in collection['sources']:
        lines.append(f"- {source['name']}: {source['status']} [{source['data_kind']}] ({source['elapsed_ms']} ms). {source['message']}")
        if result.get('collection_mode') == 'github_status' and source['data_kind'] == 'synthetic':
            lines.extend('  Practice clue (excluded): '+row['observation'] for row in source['evidence'])
    if result.get('collection_mode') == 'github_status':
        live = result['github_status']
        lines += ['', 'GitHub reported status: '+(live['indicator'] if live['state']=='reported' else 'unknown'), 'Source: '+live['source_url']]
        if live['state']=='reported':
            lines += ['Provider description: '+live['description'], 'Fetched at: '+live['observed_at'], 'Status page updated at: '+live['source_updated_at']]
        lines.append('Public aggregate status does not prove the cause or health of your own service.')
    return '\n'.join(lines)+'\n\n'+render_investigation(result)
