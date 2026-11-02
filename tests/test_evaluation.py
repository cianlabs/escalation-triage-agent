"""Public observations, source receipts and meaningful scoring failures."""
import copy
import hashlib
import json
from pathlib import Path
import re
import socket

import pytest
import evaluation as ev
from incident_data import INCIDENTS, ROOT, SOURCE_CHECKS, load_incidents, load_sources, ranking_input
from sample_data import get_escalation, list_escalations, list_real_incidents


@pytest.fixture
def cases():
    return load_incidents()


def pred(case, titles, **extra):
    result = dict(incident_id=case['id'], hypotheses=[
        dict(title=t, status='unverified', supporting_evidence_ids=[]) for t in titles
    ], confirmed_root_cause=None, action_mode='simulation_only')
    result.update(extra)
    return result


def test_real_escalations_catalog(cases):
    assert len(list_real_incidents()) == 30
    assert sum(c['vague'] for c in cases) == 15
    assert sum(c['kind'] == 'cautious' for c in cases) == 4
    assert all('logs' not in c and 'deploys' not in c for c in cases)
    assert all(c['split'] == 'baseline_evaluation' for c in cases)


def test_synthetic_logs_are_not_claimed_as_real(cases):
    practice = list_escalations()
    assert len(practice) == 17
    assert {c['id'] for c in practice}.isdisjoint(c['id'] for c in cases)
    for fixture in practice:
        assert fixture['data_kind'] == 'synthetic_practice'
        assert 'published_root_cause' not in fixture
        assert all('synthetic' in log['source'] for log in fixture['logs'])
        assert all('synthetic' in deploy['note'] for deploy in fixture['deploys'])
    first = get_escalation('INC-CLOUDFLARE-01')
    first['logs'][0]['observation'] = 'changed'
    assert first != get_escalation('INC-CLOUDFLARE-01')


def test_evaluation_runs_and_scores(cases):
    report = ev.baseline_report()
    assert report == json.loads(ev.RESULTS.read_text())
    assert ev.render_report(report) == ev.REPORT.read_text()
    assert report['total'] == 30
    assert report['metrics']['top1']['total'] == 26
    assert report['metrics']['vague_top1']['total'] == 13
    assert {r['id'] for r in report['results'] if r['missed']} == {
        r['id'] for r in report['results'] if r['top1'] is False or (r['kind'] == 'cautious' and not r['correctly_cautious'])
    }
    for row in report['results']:
        if row['missed']:
            assert f"- {row['id']} (" in ev.render_report(report)
            assert row['reason']


@pytest.mark.parametrize('change', [
    {'id': ''}, {'date': 'tomorrow'}, {'vague': 'yes'}, {'kind': 'synthetic'},
    {'source_key': 'missing'}, {'expected_family': 'impact'},
    {'confirmed_root_cause': 'guess'}, {'evidence': []}, {'logs': []}, {'deploys': []},
    {'evidence': [{'id':'x'}]},
    {'evidence': [dict(id='x',source='s',observation='o')]*2},
])
def test_loader_rejects_bad_case(tmp_path, cases, change):
    path = tmp_path / 'bad.jsonl'
    path.write_text(json.dumps(dict(cases[0], **change))+'\n')
    with pytest.raises(ValueError, match=':1:'):
        load_incidents(path)


@pytest.mark.parametrize('raw', ['', 'not json', '[]', '{}'])
def test_loader_rejects_empty_or_malformed_file(tmp_path, raw):
    path = tmp_path / 'bad.jsonl'
    path.write_text(raw)
    with pytest.raises(ValueError):
        load_incidents(path)


def test_loader_rejects_duplicate_id_or_same_event(tmp_path, cases):
    path = tmp_path / 'bad.jsonl'
    first = cases[0]
    for second in [first, dict(first, id='another-id')]:
        path.write_text(json.dumps(first)+'\n'+json.dumps(second)+'\n')
        with pytest.raises(ValueError, match='duplicate incident'):
            load_incidents(path)


@pytest.mark.parametrize('change', [
    {'status':404}, {'verified_at':''}, {'sha256':'x'*64},
    {'url':'http://example.com'}, {'final_url':'https://'},
])
def test_loader_requires_verified_sources(tmp_path, change):
    sources = list(load_sources().values())
    sources[0].update(change)
    path = tmp_path / 'sources.json'
    path.write_text(json.dumps(sources))
    with pytest.raises(ValueError):
        load_incidents(sources_path=path)


def test_caution_cannot_have_a_single_selected_cause(tmp_path, cases):
    case = copy.deepcopy(next(c for c in cases if c['kind']=='cautious'))
    case['expected_family'] = 'change_regression'
    path = tmp_path / 'bad.jsonl'
    path.write_text(json.dumps(case)+'\n')
    with pytest.raises(ValueError, match='single cause'):
        load_incidents(path)


def test_sources_match_every_citation(cases):
    sources = load_sources()
    assert {c['source_key'] for c in cases} == set(sources)
    links = set(re.findall(r'\]\((https://[^)]+)\)', (ROOT/'SOURCES.md').read_text()))
    assert links == {s['url'] for s in sources.values()}
    assert len(sources) == 26


def test_only_public_observations_reach_the_actual_ranker(cases):
    original = copy.deepcopy(cases)
    received = []
    def spy(evidence):
        received.append(copy.deepcopy(evidence))
        return ev.rank_hypotheses(evidence)
    ev.run_incident_evaluation(cases, ranker=spy)
    assert received == [ranking_input(c) for c in cases]
    assert cases == original
    for evidence in received:
        assert all(set(e)=={'id','source','observation'} for e in evidence)
        assert all('synthetic' not in e['source'] for e in evidence)
    altered = copy.deepcopy(cases)
    for c in altered:
        c['reference_cause'] = 'SECRET LABEL DO NOT PASS'
        c['symptom'] = 'The ranking tool does not use this field'
        c['context'] = 'secret answer'
    again = ev.run_incident_evaluation(altered)['predictions']
    assert again == ev.run_incident_evaluation(cases)['predictions']


def test_top_k_vague_and_caution_denominators(cases):
    a,b,c=copy.deepcopy(cases[:3])
    a.update(expected_family='change_regression', vague=True)
    b.update(expected_family='database_failure', vague=False)
    predictions=[pred(a,['Customer-facing outage','Bad deploy']), pred(b,['Database failure']), pred(c,['first','second'])]
    result=ev.score_predictions([a,b,c],predictions)
    assert result['metrics']==dict(top1=dict(correct=1,total=2),top3=dict(correct=2,total=2),
                                  vague_top1=dict(correct=0,total=1),cautious=dict(correct=1,total=1))
    assert result['results'][0]['missed']
    assert not result['results'][2]['missed']


def test_impact_and_remedy_are_not_causes():
    assert ev.cause_family('Customer-facing outage') is None
    assert ev.cause_family('Process needs a restart') is None
    assert ev.cause_family('  BAD  DEPLOY ')=='change_regression'
    assert ev.cause_family('not a bad deploy') is None


def test_fourth_place_does_not_count(cases):
    c=dict(cases[0],expected_family='database_failure')
    result=ev.score_predictions([c],[pred(c,['wrong','other','third','Database failure'])])
    assert result['metrics']['top3']==dict(correct=0,total=1)


@pytest.mark.parametrize('changes', [
    {'confirmed_root_cause':'guess'}, {'action_mode':'execute'}, {'hypotheses':[]},
    {'hypotheses':[dict(title='same',status='unverified',supporting_evidence_ids=[])]*2},
    {'hypotheses':[dict(title='a',status='confirmed',supporting_evidence_ids=[]),dict(title='b',status='unverified',supporting_evidence_ids=[])]},
    {'hypotheses':[dict(title='a',status='unverified',supporting_evidence_ids=['invented']),dict(title='b',status='unverified',supporting_evidence_ids=[])]},
])
def test_caution_rejects_confidence_execution_or_bad_evidence(cases,changes):
    c=cases[2]
    result=ev.score_predictions([c],[pred(c,['a','b'],**changes)])
    assert result['metrics']['cautious']==dict(correct=0,total=1)
    assert result['results'][0]['missed']


def test_missing_confirmed_field_is_not_abstention(cases):
    p=pred(cases[2],['a','b'])
    del p['confirmed_root_cause']
    assert not ev.correctly_cautious(p,{'observation-1'})


def test_mismatched_predictions_fail(cases):
    with pytest.raises(ValueError,match='count'):
        ev.score_predictions(cases,[])
    with pytest.raises(ValueError,match='order'):
        ev.score_predictions([cases[0]],[pred(cases[1],['x'])])


def test_evaluation_never_calls_model_network_or_action_gate(monkeypatch,tmp_path):
    import tools
    import agent
    def forbidden(*args,**kwargs):
        raise AssertionError('evaluation attempted a network, model or action call')
    monkeypatch.setattr(socket,'create_connection',forbidden)
    monkeypatch.setattr(agent,'make_client',forbidden)
    monkeypatch.setattr(tools,'record_simulated_action',forbidden)
    monkeypatch.chdir(tmp_path)
    report=ev.baseline_report()
    assert all(p['action_mode']=='simulation_only' for p in report['predictions'])
    assert not list(tmp_path.iterdir())


def test_cli_check_reproduces_committed_baseline(capsys):
    ev.main(['--check'])
    assert '| Overall top-1 |' in capsys.readouterr().out


def test_unmodified_ranking_file_is_frozen():
    assert hashlib.sha256((ROOT/'tools.py').read_bytes()).hexdigest()==ev.BASELINE_TOOLS_SHA256
