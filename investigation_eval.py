"""Score frozen synthetic challenge examples; never claim public-incident accuracy."""
import argparse
import hashlib
import json
from pathlib import Path

from evidence_ranker import investigate

ROOT = Path(__file__).resolve().parent
CHALLENGE = ROOT / 'examples/evidence-ranking/challenge.jsonl'
LOCK = ROOT / 'examples/evidence-ranking/challenge-lock.json'
RESULTS = ROOT / 'results/investigation-challenge.json'
REPORT = ROOT / 'docs/INVESTIGATION_CHALLENGE.md'


def evaluate_challenge():
    raw = CHALLENGE.read_bytes()
    lock = json.loads(LOCK.read_text())
    if hashlib.sha256(raw).hexdigest() != lock['sha256']:
        raise ValueError('frozen synthetic challenge changed')
    cases = [json.loads(line) for line in raw.decode().splitlines()]
    if len(cases) != lock['cases']:
        raise ValueError('challenge count mismatch')
    results = []
    for case in cases:
        prediction = investigate(dict(symptom=case['symptom'], evidence=case['evidence']))
        leading_family = prediction['hypotheses'][0]['family'] if prediction['hypotheses'] else None
        matched = prediction['assessment'] == case['expected'] and (case['family'] is None or leading_family == case['family'])
        results.append(dict(id=case['id'], expected_assessment=case['expected'], expected_family=case['family'],
                            predicted_assessment=prediction['assessment'], leading_family=leading_family,
                            matched=matched, prediction=prediction))
    # Audit exposed public observations without treating abstention as accuracy.
    from incident_data import load_incidents, ranking_input, INCIDENTS
    public_audit = []
    for case in load_incidents():
        prediction = investigate(dict(symptom=case['symptom'], evidence=ranking_input(case)))
        public_audit.append(dict(id=case['id'], assessment=prediction['assessment'],
                                 families=[h['family'] for h in prediction['hypotheses']],
                                 confirmed_root_cause=prediction['confirmed_root_cause']))
    return dict(public_audit=public_audit, public_dataset_sha256=hashlib.sha256(INCIDENTS.read_bytes()).hexdigest(), kind=lock['kind'], challenge_sha256=lock['sha256'], total=len(results),
                correct=sum(row['matched'] for row in results), results=results)


def render(report):
    lines = ['# Evidence-ranking synthetic challenge', '',
             'These are authored synthetic examples, frozen in a separate commit before implementation. They are not real incidents, a hidden test set, or an estimate of production accuracy. They check specific mechanism recognition and uncertainty behavior.', '',
             f"Matched expected behavior: {report['correct']}/{report['total']}.", '',
             'A match requires the expected uncertainty state and, when one is specified, the expected leading mechanism. A specific clue can support an unverified hypothesis but never a confirmed cause. Conflicting clues must remain conflicting. Generic impact alone must produce insufficient evidence.', '',
             '| Case | Expected behavior | Actual behavior | Result |', '| --- | --- | --- | --- |']
    for row in report['results']:
        expected = row['expected_assessment'] + (': '+row['expected_family'] if row['expected_family'] else '')
        actual = row['predicted_assessment'] + (': '+row['leading_family'] if row['leading_family'] else '')
        lines.append(f"| {row['id']} | {expected} | {actual} | {'pass' if row['matched'] else 'miss'} |")
    lines += ['', '## Misses', '']
    for row in report['results']:
        if not row['matched']:
            lines.append(f"- {row['id']}: Expected {row['expected_family'] or row['expected_assessment']}; the current rules returned {row['leading_family'] or row['predicted_assessment']}. Leave this miss visible rather than changing the challenge.")
    if all(row['matched'] for row in report['results']):
        lines.append('None on these examples.')
    abstentions = sum(row['assessment']=='insufficient_evidence' for row in report['public_audit'])
    lines += ['', f"On the existing {len(report['public_audit'])} exposed public user-impact records, this mode returns insufficient evidence for {abstentions}. This is a behavior audit, not an accuracy score: the records usually lack diagnostic clues. No retrospective cause labels enter the new ranker.", '', 'The original public ranking baseline and scorer remain unchanged. A new real-world comparison still needs fresh, independently reviewed diagnostic evidence and a locked evaluation protocol. User-impact-only observations generally do not contain mechanism clues.', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true')
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args(argv)
    report=evaluate_challenge()
    formatted=render(report)
    serialized=json.dumps(report,indent=2,ensure_ascii=False)+'\n'
    if args.write:
        RESULTS.write_text(serialized)
        REPORT.write_text(formatted)
    if args.check and (RESULTS.read_text()!=serialized or REPORT.read_text()!=formatted):
        raise SystemExit('Investigation challenge results do not reproduce')
    print(formatted)


if __name__=='__main__':
    main()
