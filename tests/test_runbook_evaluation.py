import json

import pytest

from runbook_evaluation import load_reviews, load_run, report, review_template
from runbook_model_eval import main, save_run

QUESTIONS = [
    dict(id='S1', question='Inspect Redis?', expected='redis_memory.txt'),
    dict(id='U1', question='Give its limit', expected=None),
]


def test_replay_legacy_run_marks_failed_and_missing_cases_without_model_calls(tmp_path, capsys):
    path = tmp_path / 'run.json'
    path.write_text(json.dumps([dict(id='S1', exit_code=1, output='Rule-based fallback', error='Unavailable')]))
    questions = tmp_path / 'questions.json'
    questions.write_text(json.dumps(QUESTIONS))
    assert main(['--replay', str(path), '--questions', str(questions)]) == 0
    text = capsys.readouterr().out
    assert '| S1 | failed | n/a | unscored' in text
    assert '| U1 | missing' in text
    assert 'Usable responses — 0/2' in text
    assert 'Prompt SHA-256 — unknown' in text


def test_review_binding_prevents_applying_scores_to_another_response(tmp_path):
    path = tmp_path / 'run.json'
    path.write_text('[]')
    reviews = tmp_path / 'reviews.json'
    template = review_template(QUESTIONS, path)
    template['reviews']['S1'].update(complete=True, grounded=False, reason='Citation does not support the claim.')
    reviews.write_text(json.dumps(template))
    assert load_reviews(reviews, QUESTIONS, path)['S1']['grounded'] is False
    path.write_text('[{}]')
    with pytest.raises(ValueError, match='does not match'):
        load_reviews(reviews, QUESTIONS, path)


def test_partial_review_denominators_and_citation_existence():
    results = {'S1': dict(exit_code=0, output='Wrong claim [fixtures/semantic/guides/redis_memory.txt:4]')}
    text = report(QUESTIONS, {}, results, {'S1': dict(complete=False, grounded=False)})
    assert '| S1 | usable | exists | fail | fail' in text
    assert 'complete — 0/1 human reviewed; 0 pending or unscored.' in text
    assert 'missing_detail — 0/0 human reviewed; 1 pending or unscored.' in text


def test_new_checkpoint_round_trips_and_rejects_duplicate_cases(tmp_path):
    path = tmp_path / 'run.json'
    rows = [dict(id='S1', exit_code=0, output='A response', seconds=0.5)]
    save_run(path, {'prompt_sha256': 'abc'}, rows)
    metadata, results = load_run(path, QUESTIONS)
    assert metadata['prompt_sha256'] == 'abc'
    assert results['S1']['seconds'] == 0.5
    path.write_text(json.dumps(rows * 2))
    with pytest.raises(ValueError, match='duplicate'):
        load_run(path, QUESTIONS)


def test_capture_saves_provenance_and_prints_pending_quality_report(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace

    questions = tmp_path / 'questions.json'
    questions.write_text(json.dumps(QUESTIONS[:1]))
    output = tmp_path / 'capture.json'
    monkeypatch.setattr('runbook_model_eval.capture_metadata', lambda rows, model, **kwargs: {
        'prompt_sha256': 'fixed-prompt', 'model_digest': 'fixed-model'})
    monkeypatch.setattr('runbook_model_eval.subprocess.run', lambda *args, **kwargs: SimpleNamespace(
        returncode=0, stdout='A cited response', stderr=''))
    assert main(['--model', 'test-model', '--questions', str(questions), '--output', str(output)]) == 0
    data = json.loads(output.read_text())
    assert data['metadata']['prompt_sha256'] == 'fixed-prompt'
    assert data['results'][0]['model'] == 'test-model'
    assert 'Usable responses — 1/1' in capsys.readouterr().out
