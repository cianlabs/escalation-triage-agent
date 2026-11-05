"""Validate saved runbook runs and report mechanical checks and human scores."""
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parent
CITATION = re.compile(r'\[([^\[\]\n]+):([1-9][0-9]*)\]')
FIELDS = ('complete', 'grounded', 'missing_detail')


def load_run(path, questions):
    data = json.loads(path.read_text(encoding='utf-8'))
    if isinstance(data, dict) and data.get('version') != 1:
        raise ValueError('Unsupported saved run version.')
    metadata = data.get('metadata', {}) if isinstance(data, dict) else {}
    rows = data.get('results') if isinstance(data, dict) else data
    if not isinstance(metadata, dict) or not isinstance(rows, list):
        raise ValueError('Expected a saved results list or a run with metadata and results.')
    allowed = {row['id'] for row in questions}
    results = {}
    for row in rows:
        if not isinstance(row, dict) or row.get('id') not in allowed or row['id'] in results:
            raise ValueError('Run contains duplicate or unknown question IDs.')
        if (not isinstance(row.get('output'), str) or not isinstance(row.get('error', ''), str)
                or (row.get('exit_code') is not None and type(row['exit_code']) is not int)):
            raise ValueError('Invalid saved response fields.')
        seconds = row.get('seconds')
        if seconds is not None and (type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0):
            raise ValueError('Invalid saved response time.')
        results[row['id']] = row
    return metadata, results


def load_reviews(path, questions, run_path):
    if not path:
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(data, dict) or data.get('run_sha256') != hashlib.sha256(run_path.read_bytes()).hexdigest()
            or data.get('questions_sha256') != question_hash(questions)):
        raise ValueError('Review file does not match this saved run and question set.')
    reviews = data.get('reviews')
    if not isinstance(reviews, dict) or set(reviews) - {row['id'] for row in questions}:
        raise ValueError('Reviews must be keyed by known question IDs.')
    for review in reviews.values():
        if (not isinstance(review, dict) or set(review) - set(FIELDS) - {'reason'}
                or any(review.get(field) is not None and type(review[field]) is not bool for field in FIELDS)
                or not isinstance(review.get('reason', ''), str)):
            raise ValueError('Review scores must be true, false, or null, with an optional reason.')
    return reviews


def question_hash(questions):
    return hashlib.sha256(json.dumps(questions, sort_keys=True).encode()).hexdigest()


def review_template(questions, run_path):
    return {
        'run_sha256': hashlib.sha256(run_path.read_bytes()).hexdigest(),
        'questions_sha256': question_hash(questions),
        'reviews': {row['id']: {**dict.fromkeys(FIELDS), 'reason': ''} for row in questions},
    }


def citation_check(output):
    citations = CITATION.findall(output)
    if not citations:
        return 'none'
    for name, number in citations:
        # Only the fixed corpus is read. Model text cannot select arbitrary files.
        if not re.fullmatch(r'fixtures/semantic/guides/[a-z0-9_]+\.txt', name):
            return 'invalid'
        path = ROOT / name
        if not path.is_file() or int(number) > len(path.read_text(encoding='utf-8').splitlines()):
            return 'invalid'
    return 'exists'


def report(questions, metadata, results, reviews):
    models = sorted({str(row.get('model', 'unknown')) for row in results.values()})
    lines = ['# Runbook evaluation', '',
             'Model — ' + ', '.join(models or ['unknown']),
             'Model digest — ' + str(metadata.get('model_digest', 'unknown')),
             'Prompt SHA-256 — ' + str(metadata.get('prompt_sha256', 'unknown')),
             'Corpus SHA-256 — ' + str(metadata.get('corpus_sha256', 'unknown')),
             'Legacy records without provenance remain unknown. Citation checks use the current corpus.',
             '', '| Case | Response | Citation IDs | Complete | Claims supported | Missing detail |',
             '| --- | --- | --- | --- | --- | --- |']
    counts = {field: [0, 0, 0] for field in FIELDS}
    usable = 0
    for question in questions:
        key = question['id']
        row = results.get(key)
        ready = row is not None and row.get('exit_code') == 0 and bool(row['output'].strip())
        usable += ready
        status = 'missing' if row is None else 'usable' if ready else 'failed'
        review = reviews.get(key, {})
        scores = []
        for field in FIELDS:
            applicable = field == 'grounded' or (field == 'complete') == (question['expected'] is not None)
            if not applicable:
                scores.append('n/a')
            elif not ready:
                counts[field][2] += 1
                scores.append('unscored')
            elif review.get(field) is None:
                counts[field][2] += 1
                scores.append('pending')
            else:
                value = review[field]
                counts[field][0] += value
                counts[field][1] += 1
                scores.append('pass' if value else 'fail')
        check = citation_check(row['output']) if ready else 'n/a'
        lines.append(f"| {key} | {status} | {check} | {' | '.join(scores)} |")
    lines += ['', f'Usable responses — {usable}/{len(questions)}']
    for field, (passed, reviewed, pending) in counts.items():
        lines.append(f'{field} — {passed}/{reviewed} human reviewed; {pending} pending or unscored.')
    times = [row['seconds'] for row in results.values() if row.get('seconds') is not None]
    lines.append('API cost — unrecorded in these saved runs.')
    lines.append(f'Median recorded command time — {statistics.median(times):.3f} seconds.' if times
                 else 'Median recorded command time — unknown.')
    lines += ['', 'Usable means the command exited successfully with output. It does not mean the answer is correct.',
              'Citation IDs existing in the corpus does not establish claim support. Review that separately.',
              'Failed and missing responses are unscored for quality and remain in the availability denominator.',
              '', '## Responses for review', '']
    for question in questions:
        key = question['id']
        lines += [f"### {key}", '', question['question'], '',
                  'Required guidance — ' + question.get('required', 'Use the expected guide and the fixed case rubric.'), '']
        row = results.get(key)
        lines += ['    ' + line for line in (row['output'] if row else 'No saved response.').splitlines()]
        if reviews.get(key, {}).get('reason'):
            lines += ['', 'Reviewer note — ' + reviews[key]['reason']]
        lines.append('')
    return '\n'.join(lines)
