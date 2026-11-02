"""Offline cause-family evaluation of this repository's unchanged ranking tool.

This is a component benchmark, not a live-model or end-to-end agent score.
Public user-impact observations replace the old invented logs and deploy records.
"""
import argparse
import hashlib
import json
from pathlib import Path

from incident_data import CAUSE_FAMILIES, INCIDENTS, ROOT, load_incidents, ranking_input, text
from tools import rank_hypotheses

BASELINE_COMMIT = '68cb090e106180f08828954f7b322092a395fa8f'
BASELINE_TOOLS_SHA256 = '1712e5218b4be8ac1fba0c821ed78b0509a00ed6c36cda10b6c36a50b3142e40'
RESULTS = ROOT / 'results/baseline.json'
REPORT = ROOT / 'docs/BASELINE.md'

# Interpret existing output; these mappings never affect rank_hypotheses.
# A remediation or a description of impact is not a causal diagnosis.
TITLE_FAMILIES = {name.replace('_', ' '): name for name in CAUSE_FAMILIES}
TITLE_FAMILIES['bad deploy'] = 'change_regression'
NON_CAUSAL_TITLES = {'process needs a restart', 'customer-facing outage'}


def normalized(title):
    return ' '.join(title.casefold().split())


def cause_family(title):
    return TITLE_FAMILIES.get(normalized(title))


def correctly_cautious(prediction, evidence_ids):
    hypotheses = prediction.get('hypotheses')
    if not isinstance(hypotheses, list) or len(hypotheses) < 2:
        return False
    titles = [h.get('title') for h in hypotheses if isinstance(h, dict)]
    return (
        len(titles) == len(hypotheses) and all(text(t) for t in titles)
        and len({normalized(t) for t in titles}) == len(titles)
        and 'confirmed_root_cause' in prediction and prediction['confirmed_root_cause'] is None
        and prediction.get('action_mode') == 'simulation_only'
        and all(h.get('status') == 'unverified'
                and isinstance(h.get('supporting_evidence_ids'), list)
                and all(isinstance(x, str) and x in evidence_ids for x in h['supporting_evidence_ids'])
                for h in hypotheses)
    )


def score_predictions(incidents, predictions):
    if len(incidents) != len(predictions):
        raise ValueError('prediction count differs from incident count')
    metrics = {k: {'correct': 0, 'total': 0} for k in ('top1', 'top3', 'vague_top1', 'cautious')}
    results = []
    for case, prediction in zip(incidents, predictions):
        if not isinstance(prediction, dict) or prediction.get('incident_id') != case['id']:
            raise ValueError('prediction incident id or order mismatch')
        hypotheses = prediction.get('hypotheses')
        if not isinstance(hypotheses, list) or any(not isinstance(h, dict) or not text(h.get('title')) for h in hypotheses):
            raise ValueError('invalid ranked hypothesis list')
        titles = [h['title'] for h in hypotheses]
        families = [cause_family(title) for title in titles]
        caution = correctly_cautious(prediction, {e['id'] for e in case['evidence']})
        item = dict(id=case['id'], title=case['title'], kind=case['kind'], vague=case['vague'],
                    expected_family=case['expected_family'], reference_cause=case['reference_cause'],
                    ranked_titles=titles, ranked_families=families, correctly_cautious=caution,
                    top1_has_support=bool(hypotheses and hypotheses[0].get('supporting_evidence_ids')))
        if case['kind'] == 'cautious':
            metrics['cautious']['total'] += 1
            metrics['cautious']['correct'] += int(caution)
            item.update(top1=None, top3=None, missed=not caution,
                        reason='Kept multiple unverified hypotheses and no confirmed cause.' if caution else
                        'Failed caution: requires distinct unverified hypotheses, valid evidence, no confirmed cause and simulation-only mode.')
        else:
            first = case['expected_family'] in families[:1]
            third = case['expected_family'] in families[:3]
            for key, good in [('top1', first), ('top3', third)] + ([('vague_top1', first)] if case['vague'] else []):
                metrics[key]['total'] += 1
                metrics[key]['correct'] += int(good)
            if first:
                reason = ('Leading hypothesis matches the broad cause family; specific mechanism is not established.'
                          if item['top1_has_support'] else
                          'Broad family matches by default order, without supporting evidence; this is a guess.')
            elif third:
                reason = 'Correct broad cause family is present, but not ranked first.'
            else:
                reason = 'Top three cannot express ' + case['expected_family'].replace('_', ' ') + '; source mechanism: ' + case['reference_cause'] + '.'
            item.update(top1=first, top3=third, missed=not first, reason=reason)
        results.append(item)
    return dict(metrics=metrics, results=results)


def run_incident_evaluation(incidents=None, ranker=None):
    """Run the real ranking tool on an allowlist of public impact observations."""
    if incidents is None:
        incidents = load_incidents()
    if ranker is None:
        ranker = rank_hypotheses
    predictions = []
    for case in incidents:
        result = dict(ranker(ranking_input(case)))
        result['incident_id'] = case['id']
        predictions.append(result)
    report = score_predictions(incidents, predictions)
    report.update(total=len(incidents), predictions=predictions,
                  benchmark='public user-impact observations; deterministic ranking tool; cause-family scoring')
    return report


def baseline_report():
    current_hash = hashlib.sha256((ROOT / 'tools.py').read_bytes()).hexdigest()
    if current_hash != BASELINE_TOOLS_SHA256:
        raise ValueError('ranking baseline changed; review before recording another baseline')
    report = run_incident_evaluation()
    report.update(baseline_commit=BASELINE_COMMIT, tools_sha256=current_hash,
                  dataset_sha256=hashlib.sha256(INCIDENTS.read_bytes()).hexdigest())
    return report


def render_report(report):
    def cell(key):
        m = report['metrics'][key]
        return f"{m['correct']}/{m['total']} ({100*m['correct']/m['total']:.1f}%)" if m['total'] else 'not measured (0 cases)'
    unsupported_hits = sum(r['top1'] is True and not r['top1_has_support'] for r in report['results'])
    lines = ['# Public incident baseline', '',
             'Deterministic ranking tool on public user-impact observations. Diagnosis metrics measure broad cause families, not exact mechanisms or verified root causes. Four cautious cases are scored separately.', '',
             '| Overall top-1 | Overall top-3 | Vague symptom top-1 | Correctly cautious |',
             '| --- | --- | --- | --- |',
             '| ' + ' | '.join(cell(k) for k in ('top1', 'top3', 'vague_top1', 'cautious')) + ' |', '',
             'The existing Bad deploy title maps to change regression. Process needs a restart is a remedy, and Customer-facing outage is impact; neither earns cause credit. The top-3 score is a vocabulary-coverage ceiling because the tool always returns the same three titles. Caution measures restraint and valid output structure, not hypothesis relevance. Vague cases have equally sparse evidence; the ranker ignores the symptom itself.', '',
             f'{unsupported_hits} top-1 hits have no supporting evidence. The frozen ranker keeps Bad deploy first when evidence counts tie. Those hits are guesses, not evidence of successful investigation.', '',
             '## Missed incidents', '']
    misses = [r for r in report['results'] if r['missed']]
    lines.extend(f"- {r['id']} ({r['title']}): {r['reason']}" for r in misses)
    if not misses:
        lines.append('None.')
    lines += ['', '## All incidents', '', '| Incident | Kind | Top-1 | Top-3 | Caution |', '| --- | --- | --- | --- | --- |']
    for row in report['results']:
        def result(value):
            return 'not scored' if value is None else ('pass' if value else 'miss')
        lines.append(f"| {row['id']} | {row['kind']} | {result(row['top1'])} | {result(row['top3'])} | {result(row['correctly_cautious']) if row['kind']=='cautious' else 'not scored'} |")
    return '\n'.join(lines) + '\n'


def print_evaluation_results(eval_summary=None):
    print(render_report(eval_summary if eval_summary is not None else baseline_report()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='record baseline predictions and readable report')
    parser.add_argument('--check', action='store_true', help='verify committed baseline reproduces offline')
    args = parser.parse_args(argv)
    report = baseline_report()
    formatted = render_report(report)
    serialized = json.dumps(report, indent=2, ensure_ascii=False) + '\n'
    if args.write:
        RESULTS.parent.mkdir(exist_ok=True)
        RESULTS.write_text(serialized)
        REPORT.write_text(formatted)
    if args.check and (RESULTS.read_text() != serialized or REPORT.read_text() != formatted):
        raise SystemExit('Committed baseline does not reproduce')
    print(formatted)


if __name__ == '__main__':
    main()
