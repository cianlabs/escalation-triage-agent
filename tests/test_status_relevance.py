"""Component relevance is context, never a confirmed cause."""
import asyncio
import copy

import httpx
import pytest

import github_status as gh
from status_relevance import COMPONENTS, assess_relevance, select_component
from evidence_collection import render_collection
from agent import main


def summary(states=None,indicator='none'):
    states=states if states is not None else {'actions':'operational','pages':'operational'}
    return dict(page=dict(id=gh.STATUS_PAGE_ID,name='GitHub',url='https://www.githubstatus.com',updated_at='2026-11-01T12:00:00Z'),
                status=dict(indicator=indicator,description='Provider report'),
                components=[dict(id=COMPONENTS[k][0],name=COMPONENTS[k][1],page_id=gh.STATUS_PAGE_ID,status=v,updated_at='2026-11-01T11:59:00Z') for k,v in states.items()])


async def run(data,problem='GitHub Actions jobs are queued',component=None,code=200,requests=None):
    def handler(request):
        if requests is not None:
            requests.append(request)
        return httpx.Response(code,json=data)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await gh.collect_github_status(client,problem,component)


@pytest.mark.parametrize('problem,expected',[
    ('GitHub Actions jobs are queued','actions'), ('GitHub runners cannot start','actions'),
    ('git push to GitHub fails','git'), ('GitHub API returns errors','api'),
    ('My GitHub Pages site cannot build','pages'), ('Cannot pull from ghcr.io','packages'),
    ('Codespaces will not start','codespaces'), ('GitHub Copilot is unavailable','copilot'),
    ('GitHub issues will not save','issues'), ('GitHub pull requests will not load','pull-requests'),
    ('GitHub webhooks arrive late','webhooks'),
    ('My website will not open',None), ('My API returns 500',None),
    ('Actions for my team are failing',None),
    ('GitHub Actions and GitHub Pages are broken',None),
])
def test_conservative_service_selection(problem,expected):
    assert select_component(problem)==expected


@pytest.mark.parametrize('status',['degraded_performance','partial_outage','major_outage','under_maintenance'])
def test_same_component_degradation_is_only_possibly_related(status):
    result=asyncio.run(run(summary({'actions':status})))
    relevance=result['status_relevance']
    assert relevance['assessment']=='possibly_related'
    assert relevance['component']=='actions'
    assert relevance['component_status']==status
    assert 'does not prove the cause' in relevance['message']
    assert result['confirmed_root_cause'] is None
    assert not result['action_proposed']
    assert not result['hypotheses']


def test_an_unrelated_outage_does_not_explain_actions_failure():
    result=asyncio.run(run(summary({'actions':'operational','pages':'major_outage'},indicator='major')))
    assert result['github_status']['indicator']=='major'
    assert result['status_relevance']['assessment']=='no_reported_issue'
    assert 'does not rule out' in result['status_relevance']['message']


def test_aggregate_healthy_does_not_override_degraded_component():
    result=asyncio.run(run(summary({'actions':'partial_outage'},indicator='none')))
    assert result['status_relevance']['assessment']=='possibly_related'


@pytest.mark.parametrize('states',[{}, {'pages':'operational'}, {'actions':'new_future_state'}])
def test_missing_or_unrecognized_component_is_unknown(states):
    result=asyncio.run(run(summary(states)))
    assert result['status_relevance']['assessment']=='unknown'
    assert result['status_relevance']['component']=='actions'
    assert not result['hypotheses']


def test_ambiguous_problem_asks_for_a_component_even_during_outage():
    result=asyncio.run(run(summary({'actions':'major_outage'},'major'),'The website is broken'))
    assert result['status_relevance']['assessment']=='needs_component'
    assert 'Specify the affected GitHub service' in result['next_checks'][0]


def test_explicit_component_disambiguates_without_claiming_causation():
    result=asyncio.run(run(summary({'actions':'major_outage'}),'My build is stuck',component='actions'))
    assert result['status_relevance']['assessment']=='possibly_related'
    assert result['confirmed_root_cause'] is None


@pytest.mark.parametrize('problem',[
    'GitHub Actions failed yesterday','GitHub Actions failed last week',
    'GitHub Actions failed 3 hours ago','GitHub Actions failed on 2026-10-20',
])
def test_current_snapshot_does_not_explain_a_historical_incident(problem):
    result=asyncio.run(run(summary({'actions':'major_outage'}),problem))
    assert result['status_relevance']['assessment']=='time_not_matched'
    assert 'earlier incident time' in result['status_relevance']['message']


def test_problem_stays_local_and_only_one_fixed_summary_request_is_sent():
    requests=[]
    problem='GitHub Actions fails for PRIVATE_REPOSITORY_NAME'
    result=asyncio.run(run(summary(),problem,requests=requests))
    assert len(requests)==1
    request=requests[0]
    assert str(request.url)==gh.SUMMARY_URL
    assert request.method=='GET'
    assert not request.content and not request.url.query
    assert 'PRIVATE_REPOSITORY_NAME' not in str(request.headers)
    assert 'authorization' not in request.headers
    assert result['symptom']==problem
    assert all(e['data_kind']=='public_status' for e in result['evidence'])
    assert result['github_status']['source_url']==gh.SUMMARY_URL
    component=result['evidence'][1]
    assert component['component_updated_at']=='2026-11-01T11:59:00+00:00'
    assert component['source_url']==gh.SUMMARY_URL
    assert 'Component last updated at:' in render_collection(result)


@pytest.mark.parametrize('bad', ['missing','not-list','duplicate','wrong-name','wrong-page','bad-time'])
def test_malformed_component_report_does_not_become_operational(bad):
    data=summary()
    if bad=='missing': del data['components']
    elif bad=='not-list': data['components']={}
    elif bad=='duplicate': data['components'].append(copy.deepcopy(data['components'][0]))
    elif bad=='wrong-name': data['components'][0]['name']='Fake Actions'
    elif bad=='wrong-page': data['components'][0]['page_id']='other-page'
    else: data['components'][0]['updated_at']='not-a-time'
    result=asyncio.run(run(data))
    assert result['github_status']['state']=='unknown'
    assert result['status_relevance']['assessment']=='unknown'
    assert result['evidence']==[]


def test_unknown_future_component_is_not_used_for_name_matching():
    data=summary({})
    data['components']=[dict(id='future-component',name='Actions',status='operational')]
    result=asyncio.run(run(data))
    assert result['status_relevance']['assessment']=='unknown'


def test_failed_request_cannot_be_hidden_by_simulated_sources():
    result=asyncio.run(run(summary(),code=503))
    assert result['github_status']['state']=='unknown'
    assert result['status_relevance']['assessment']=='unknown'
    assert not result['hypotheses']
    assert result['collection_incomplete']


@pytest.mark.parametrize('extra',[
    ['--problem','something'],['--component','actions'],
    ['--github-status','--component','actions'],['--github-status','--problem',' '],
])
def test_invalid_problem_options_rejected_before_any_request(extra,monkeypatch):
    monkeypatch.setattr(gh,'run_github_collection',lambda **kw:pytest.fail('invalid options started a request'))
    with pytest.raises(SystemExit) as exc:
        main(extra)
    assert exc.value.code==2


def test_cli_passes_problem_and_component_locally(monkeypatch,capsys):
    calls=[]
    def collect(**kwargs):
        calls.append(kwargs)
        return asyncio.run(run(summary(),kwargs['problem'],kwargs['component']))
    monkeypatch.setattr(gh,'run_github_collection',collect)
    assert main(['--github-status','--problem','My build is stuck','--component','actions'])==0
    assert calls==[dict(problem='My build is stuck',component='actions')]
    assert 'Relevance to your problem: no_reported_issue' in capsys.readouterr().out
