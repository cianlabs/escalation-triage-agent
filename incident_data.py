"""Load reviewed public incidents without conflating labels and observations."""
import json
from datetime import date, datetime
from pathlib import Path
import re
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
INCIDENTS = ROOT / 'incidents/public.jsonl'
SOURCE_CHECKS = ROOT / 'incidents/source_checks.json'
CAUSE_FAMILIES = frozenset({
    'integer_overflow', 'database_failure', 'change_regression', 'dependency_outage',
    'operator_deletion', 'query_overload', 'resource_limit', 'build_node_failure',
    'network_partition', 'ddos', 'network_congestion', 'operator_disablement',
    'storage_dependency', 'capacity_removal',
})


def text(value):
    return isinstance(value, str) and bool(value.strip())


def load_sources(path=SOURCE_CHECKS):
    rows = json.loads(Path(path).read_text())
    if not isinstance(rows, list) or not rows:
        raise ValueError('source checks must be a nonempty list')
    sources = {}
    for row in rows:
        if not isinstance(row, dict) or not text(row.get('key')) or row['key'] in sources:
            raise ValueError('invalid or duplicate source key')
        for field in ('url', 'final_url'):
            parsed = urlparse(row.get(field, ''))
            if parsed.scheme != 'https' or not parsed.netloc:
                raise ValueError('source must have an HTTPS URL and resolved URL')
        if row.get('status') != 200:
            raise ValueError('source must have HTTP 200 verification')
        if not isinstance(row.get('sha256'), str) or not re.fullmatch('[a-f0-9]{64}', row['sha256']):
            raise ValueError('source needs a SHA-256 body hash')
        try:
            stamp = datetime.fromisoformat(row['verified_at'])
            if stamp.tzinfo is None:
                raise ValueError('timezone required')
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('source needs a timezone-aware fetch time') from exc
        sources[row['key']] = row
    return sources


def load_incidents(path=INCIDENTS, sources_path=SOURCE_CHECKS):
    sources = load_sources(sources_path)
    incidents, ids, events = [], set(), set()
    for line_number, line in enumerate(Path(path).read_text().splitlines(), 1):
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError('incident must be an object')
            for key in ('id', 'date', 'title', 'source_key', 'source_section', 'symptom', 'impact', 'context', 'input_provenance'):
                if not text(row.get(key)):
                    raise ValueError(f'{key} must be nonempty')
            date.fromisoformat(row['date'])
            if row['id'] in ids:
                raise ValueError('duplicate incident id')
            if row['source_key'] not in sources:
                raise ValueError('unknown or unverified source')
            event = (row['source_key'], row['date'], row['source_section'])
            if event in events:
                raise ValueError('duplicate incident event')
            if type(row.get('vague')) is not bool:
                raise ValueError('vague must be boolean')
            if row.get('kind') not in ('diagnosis', 'cautious'):
                raise ValueError('unknown incident kind')
            family = row.get('expected_family')
            if row['kind'] == 'diagnosis':
                if family not in CAUSE_FAMILIES or not text(row.get('reference_cause')):
                    raise ValueError('diagnosis needs a mechanism and known cause family')
            elif family is not None or row.get('reference_cause') is not None:
                raise ValueError('cautious case must not select a single cause')
            if row.get('confirmed_root_cause', 'missing') is not None:
                raise ValueError('supplied observations do not confirm a root cause')
            if 'logs' in row or 'deploys' in row:
                raise ValueError('public cases cannot carry synthetic log or deploy fixtures')
            evidence = row.get('evidence')
            if not isinstance(evidence, list) or not evidence:
                raise ValueError('case needs public observations')
            evidence_ids = set()
            for item in evidence:
                if not isinstance(item, dict) or any(not text(item.get(k)) for k in ('id', 'source', 'observation')):
                    raise ValueError('invalid evidence row')
                if item['id'] in evidence_ids:
                    raise ValueError('duplicate evidence id')
                evidence_ids.add(item['id'])
            ids.add(row['id'])
            events.add(event)
            incidents.append(row)
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f'{path}:{line_number}: {exc}') from exc
    if not incidents:
        raise ValueError('empty public incident set')
    return incidents


def ranking_input(incident):
    """Only observed impact crosses the boundary; no labels or retrospective cause."""
    return [dict(id=e['id'], source=e['source'], observation=e['observation']) for e in incident['evidence']]
