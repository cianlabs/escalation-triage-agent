"""One read-only public GitHub status request, plus two labeled practice checks."""
import asyncio
from datetime import datetime, timezone

import httpx

from evidence_collection import EvidenceCheck, collect_and_investigate, simulated_checks

STATUS_URL = 'https://www.githubstatus.com/api/v2/status.json'
STATUS_PAGE_ID = 'kctbh9vrtdwd'
INDICATORS = frozenset({'none', 'minor', 'major', 'critical'})
REQUEST_TIMEOUT = 4.0
CHECK_TIMEOUT = 5.0


class GitHubStatusUnavailable(Exception):
    """The public endpoint could not return a successful response."""


class GitHubStatusBadResponse(Exception):
    """A 200 response did not contain the expected GitHub status payload."""


def parse_status(payload, observed_at):
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
    return [dict(id='reported-status', source=STATUS_URL,
                 observation=f"GitHub's public status page reports aggregate indicator {indicator}. This is provider-reported impact, not evidence of a root cause.",
                 source_url=STATUS_URL, observed_at=observed_at,
                 source_updated_at=updated.isoformat(), status_indicator=indicator,
                 reported_description=' '.join(description.split()))]


async def read_github_status(client):
    try:
        response = await client.get(STATUS_URL, timeout=REQUEST_TIMEOUT,
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
    return parse_status(payload, datetime.now(timezone.utc).isoformat())


def mixed_checks(client):
    practice = simulated_checks('complete')
    # Declare provenance at the reader boundary, never from returned row claims.
    return [EvidenceCheck('recent_errors', practice[0].read, 0.1, data_kind='synthetic'),
            EvidenceCheck('recent_changes', practice[1].read, 0.1, data_kind='synthetic'),
            EvidenceCheck('github_status', lambda: read_github_status(client), CHECK_TIMEOUT, data_kind='public_status')]


async def collect_github_status(client):
    result = await collect_and_investigate(
        "Is there provider-reported impact on GitHub?", mixed_checks(client),
        allowed_data_kinds={'public_status'})
    result['collection_mode'] = 'github_status'
    status_source = next(s for s in result['collection']['sources'] if s['name'] == 'github_status')
    if status_source['status'] == 'ok':
        row = status_source['evidence'][0]
        result['github_status'] = dict(state='reported', indicator=row['status_indicator'],
                                     description=row['reported_description'], observed_at=row['observed_at'],
                                     source_updated_at=row['source_updated_at'], source_url=STATUS_URL)
    else:
        result['github_status'] = dict(state='unknown', indicator=None, source_url=STATUS_URL)
    return result


async def _run_github_collection():
    # A fresh client has no account cookies, model keys, authorization or retries.
    async with httpx.AsyncClient(trust_env=False) as client:
        return await collect_github_status(client)


def run_github_collection():
    return asyncio.run(_run_github_collection())
