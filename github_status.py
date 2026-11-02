"""One read-only public GitHub status request, plus two labeled practice checks."""
import asyncio
from datetime import datetime, timezone

import httpx

from evidence_collection import EvidenceCheck, collect_and_investigate, simulated_checks

STATUS_URL = 'https://www.githubstatus.com/api/v2/status.json'
SUMMARY_URL = 'https://www.githubstatus.com/api/v2/summary.json'
STATUS_PAGE_ID = 'kctbh9vrtdwd'
INDICATORS = frozenset({'none', 'minor', 'major', 'critical'})
REQUEST_TIMEOUT = 4.0
CHECK_TIMEOUT = 5.0


class GitHubStatusUnavailable(Exception):
    """The public endpoint could not return a successful response."""


class GitHubStatusBadResponse(Exception):
    """A 200 response did not contain the expected GitHub status payload."""


def parse_status(payload, observed_at, source_url=STATUS_URL):
    if not isinstance(payload, dict):
        raise GitHubStatusBadResponse()
    page, status = payload.get('page'), payload.get('status')
    if not isinstance(page, dict) or not isinstance(status, dict):
        raise GitHubStatusBadResponse()
    if page.get('id') != STATUS_PAGE_ID or page.get('name') != 'GitHub' or page.get('url') not in ('https://www.githubstatus.com', 'https://www.githubstatus.com/'):
        raise GitHubStatusBadResponse()
    indicator = status.get('indicator')
    description = status.get('description')
    if not isinstance(indicator, str) or indicator not in INDICATORS or not isinstance(description, str) or not description.strip():
        raise GitHubStatusBadResponse()
    updated_at = page.get('updated_at')
    try:
        updated = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
        if updated.tzinfo is None:
            raise ValueError('timezone missing')
    except (AttributeError, TypeError, ValueError):
        raise GitHubStatusBadResponse() from None
    # Do not feed the provider's free-text description into causal rules.
    # Aggregate status is context about impact, not diagnostic mechanism evidence.
    return [dict(id='reported-status', source=source_url,
                 observation=f"GitHub's public status page reports aggregate indicator {indicator}. This is provider-reported impact, not evidence of a root cause.",
                 source_url=source_url, observed_at=observed_at,
                 source_updated_at=updated.isoformat(), status_indicator=indicator,
                 reported_description=' '.join(description.split()))]


async def _read_payload(client, url):
    try:
        response = await client.get(url, timeout=REQUEST_TIMEOUT,
                                    follow_redirects=False,
                                    headers={'Accept': 'application/json', 'User-Agent': 'escalation-triage-agent/status-reader'})
    except httpx.TimeoutException:
        raise TimeoutError('GitHub status request timed out') from None
    except httpx.RequestError:
        raise GitHubStatusUnavailable() from None
    if response.status_code != 200:
        raise GitHubStatusUnavailable()
    try:
        payload = response.json()
    except (ValueError, UnicodeError):
        raise GitHubStatusBadResponse() from None
    return payload


async def read_github_status(client):
    return parse_status(await _read_payload(client, STATUS_URL), datetime.now(timezone.utc).isoformat())


def parse_summary(payload, observed_at):
    from status_relevance import COMPONENTS
    rows = parse_status(payload, observed_at, SUMMARY_URL)
    components = payload.get('components')
    if not isinstance(components, list):
        raise GitHubStatusBadResponse()
    known = {value[0]: (key, value[1]) for key, value in COMPONENTS.items()}
    seen = set()
    statuses = {'operational', 'degraded_performance', 'partial_outage', 'major_outage', 'under_maintenance'}
    for component in components:
        if not isinstance(component, dict) or not isinstance(component.get('id'), str):
            raise GitHubStatusBadResponse()
        cid = component['id']
        if cid in seen:
            raise GitHubStatusBadResponse()
        seen.add(cid)
        if cid not in known:
            continue  # Unknown future components cannot be silently matched.
        key, name = known[cid]
        if component.get('name') != name or component.get('page_id') != STATUS_PAGE_ID:
            raise GitHubStatusBadResponse()
        raw_status = component.get('status')
        status = raw_status if isinstance(raw_status, str) and raw_status in statuses else 'unknown'
        updated_at = component.get('updated_at')
        try:
            updated = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
            if updated.tzinfo is None:
                raise ValueError('timezone missing')
        except (AttributeError, TypeError, ValueError):
            raise GitHubStatusBadResponse() from None
        rows.append(dict(id='component-'+key, source=SUMMARY_URL, source_url=SUMMARY_URL,
                         observation=f'GitHub reports component {name} as {status}. This describes provider impact, not a root cause.',
                         observed_at=observed_at, source_updated_at=rows[0]['source_updated_at'],
                         component_key=key, component_name=name, component_status=status,
                         component_updated_at=updated.isoformat()))
    return rows


async def read_github_summary(client):
    return parse_summary(await _read_payload(client, SUMMARY_URL), datetime.now(timezone.utc).isoformat())


def mixed_checks(client, with_components=False):
    practice = simulated_checks('complete')
    # Declare provenance at the reader boundary, never from returned row claims.
    return [EvidenceCheck('recent_errors', practice[0].read, 0.1, data_kind='synthetic'),
            EvidenceCheck('recent_changes', practice[1].read, 0.1, data_kind='synthetic'),
            EvidenceCheck('github_status', lambda: read_github_summary(client) if with_components else read_github_status(client), CHECK_TIMEOUT, data_kind='public_status')]


async def collect_github_status(client, problem=None, component=None):
    if problem is not None:
        from evidence_ranker import investigate
        from status_relevance import COMPONENTS
        investigate(dict(symptom=problem, evidence=[]))
        if component is not None and component not in COMPONENTS:
            raise ValueError('Unknown GitHub component')
    elif component is not None:
        raise ValueError('A component needs a problem description')
    result = await collect_and_investigate(
        problem if problem is not None else "Is there provider-reported impact on GitHub?", mixed_checks(client, with_components=problem is not None),
        allowed_data_kinds={'public_status'})
    result['collection_mode'] = 'github_status'
    status_source = next(s for s in result['collection']['sources'] if s['name'] == 'github_status')
    if status_source['status'] == 'ok':
        row = status_source['evidence'][0]
        result['github_status'] = dict(state='reported', indicator=row['status_indicator'],
                                     description=row['reported_description'], observed_at=row['observed_at'],
                                     source_updated_at=row['source_updated_at'], source_url=row['source_url'])
    else:
        result['github_status'] = dict(state='unknown', indicator=None, source_url=SUMMARY_URL if problem is not None else STATUS_URL)
    if problem is not None:
        from status_relevance import assess_relevance
        components = [row for row in status_source['evidence'] if 'component_key' in row]
        result['status_relevance'] = assess_relevance(problem, components, component)
        result['next_checks'].insert(0, result['status_relevance']['next_check'])
    return result


async def _run_github_collection(problem=None, component=None):
    # A fresh client has no account cookies, model keys, authorization or retries.
    async with httpx.AsyncClient(trust_env=False) as client:
        return await collect_github_status(client, problem, component)


def run_github_collection(problem=None, component=None):
    return asyncio.run(_run_github_collection(problem, component))
