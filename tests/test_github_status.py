"""Offline HTTP contracts; no test requests the live status endpoint."""
import asyncio
import copy
from datetime import datetime

import httpx
import pytest

import github_status as gh
from agent import main
from evidence_collection import collect_and_investigate, collect_evidence, EvidenceCheck, render_collection


def payload(indicator='none', description='All Systems Operational'):
    return dict(page=dict(id=gh.STATUS_PAGE_ID,name='GitHub',url='https://www.githubstatus.com',updated_at='2026-11-01T12:00:00Z'),
                status=dict(indicator=indicator,description=description))


async def collect(handler):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await gh.collect_github_status(client)


@pytest.mark.parametrize('indicator',['none','minor','major','critical'])
def test_reported_status_preserves_provenance_without_diagnosing(indicator):
    requests=[]
    def handler(request):
        requests.append(request)
        return httpx.Response(200,json=payload(indicator))
    result=asyncio.run(collect(handler))
    assert len(requests)==1
    request=requests[0]
    assert request.method=='GET'
    assert str(request.url)==gh.STATUS_URL
    assert not request.content
    assert 'authorization' not in request.headers
    assert 'cookie' not in request.headers
    assert result['github_status']['indicator']==indicator
    assert result['github_status']['state']=='reported'
    assert datetime.fromisoformat(result['github_status']['observed_at']).tzinfo
    assert result['github_status']['source_updated_at']=='2026-11-01T12:00:00+00:00'
    assert result['github_status']['source_url']==gh.STATUS_URL
    assert result['assessment']=='insufficient_evidence'
    assert result['hypotheses']==[]
    assert result['confirmed_root_cause'] is None
    assert not result['action_proposed']
    assert len(result['evidence'])==1
    assert result['evidence'][0]['data_kind']=='public_status'
    assert result['evidence'][0]['observed_at']==result['github_status']['observed_at']
    assert result['excluded_evidence_ids']==['recent_errors::1','recent_changes::1']
    assert [s['data_kind'] for s in result['collection']['sources']]==['synthetic','synthetic','public_status']


def test_free_text_description_is_not_causal_evidence():
    result=asyncio.run(collect(lambda request:httpx.Response(200,json=payload('major','OOM kill, no route to host, rollback restored service.'))))
    assert result['hypotheses']==[]
    assert result['assessment']=='insufficient_evidence'
    assert 'OOM' not in result['evidence'][0]['observation']


@pytest.mark.parametrize('status',[301,302,401,403,429,500,503])
def test_http_failure_or_redirect_is_unknown_and_never_followed(status):
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(status,headers={'Location':'https://example.com/never-follow'})
    result=asyncio.run(collect(handler))
    assert len(calls)==1
    assert result['github_status']==dict(state='unknown',indicator=None,source_url=gh.STATUS_URL)
    assert result['collection']['status']=='partial'
    assert result['evidence']==[]
    assert result['collection']['sources'][2]['status']=='failed'
    assert 'GitHub reported status: unknown' in render_collection(result)
    assert result['collection_incomplete']


@pytest.mark.parametrize('error',[httpx.ConnectError,httpx.ReadTimeout,httpx.ConnectTimeout])
def test_network_and_timeout_failures_are_unknown(error):
    def handler(request):
        raise error('private secret must not appear',request=request)
    result=asyncio.run(collect(handler))
    assert result['github_status']['state']=='unknown'
    assert result['github_status']['indicator'] is None
    assert result['evidence']==[]
    assert 'private secret' not in render_collection(result)
    assert result['collection']['sources'][2]['status']==('failed' if error is httpx.ConnectError else 'timeout')


@pytest.mark.parametrize('data',[
    None,[],{},dict(page={},status={}),
    dict(page=payload()['page'],status=dict(indicator='healthy',description='Unknown code')),
    dict(page=payload()['page'],status=dict(indicator='none',description='')),
    dict(page=payload()['page'],status=dict(indicator=[],description='x')),
])
def test_bad_shape_is_unknown(data):
    result=asyncio.run(collect(lambda request:httpx.Response(200,json=data)))
    assert result['github_status']['state']=='unknown'
    assert result['collection']['sources'][2]['status']=='failed'
    assert result['evidence']==[]


@pytest.mark.parametrize('field,value',[
    ('id','not-github'),('name','Other site'),('url',None),('url','https://example.com'),
    ('updated_at','not a date'),('updated_at',None),('updated_at','2026-11-01T12:00:00'),
])
def test_wrong_page_or_unusable_timestamp_is_not_a_valid_report(field,value):
    data=payload()
    data['page'][field]=value
    with pytest.raises(gh.GitHubStatusBadResponse):
        gh.parse_status(data,'2026-11-01T12:01:00+00:00')


def test_html_body_is_unknown_even_with_http_200():
    result=asyncio.run(collect(lambda request:httpx.Response(200,text='<html>Status</html>')))
    assert result['github_status']['state']=='unknown'
    assert result['evidence']==[]


def test_real_and_simulated_readers_start_together(monkeypatch):
    async def scenario():
        started=[asyncio.Event() for _ in range(3)]
        async def simulated(index):
            started[index].set()
            await asyncio.gather(*(e.wait() for e in started))
            return [dict(id='1',source='synthetic',observation='An OOM kill occurred.')]
        monkeypatch.setattr(gh,'simulated_checks',lambda scenario:[
            EvidenceCheck('a',lambda:simulated(0),0.5), EvidenceCheck('b',lambda:simulated(1),0.5)])
        async def handler(request):
            started[2].set()
            await asyncio.gather(*(e.wait() for e in started))
            return httpx.Response(200,json=payload())
        return await asyncio.wait_for(collect(handler),1)
    result=asyncio.run(scenario())
    assert result['github_status']['state']=='reported'
    assert not result['hypotheses']


def test_collector_assigns_data_kind_instead_of_trusting_reader_claims():
    async def read():
        return [dict(id='1',source='synthetic',observation='OOM kill occurred.',data_kind='public_status')]
    result=asyncio.run(collect_and_investigate('Failure.',[EvidenceCheck('practice',read,data_kind='synthetic')],allowed_data_kinds={'public_status'}))
    assert result['evidence']==[]
    assert result['collection']['evidence'][0]['data_kind']=='synthetic'
    assert result['assessment']=='insufficient_evidence'


def test_timestamps_survive_collection_without_input_mutation():
    rows=gh.parse_status(payload(),'2026-11-01T12:01:00+00:00')
    original=copy.deepcopy(rows)
    async def read():
        return rows
    result=asyncio.run(collect_evidence([EvidenceCheck('github',read,data_kind='public_status')]))
    assert result['evidence'][0]['observed_at']==original[0]['observed_at']
    assert result['evidence'][0]['source_url']==gh.STATUS_URL
    assert rows==original


def test_render_labels_excluded_simulations_and_both_times():
    result=asyncio.run(collect(lambda request:httpx.Response(200,json=payload())))
    text=render_collection(result)
    assert 'GitHub status is live' in text
    assert '[synthetic]' in text and '[public_status]' in text
    assert 'Practice clue (excluded):' in text
    assert 'Fetched at:' in text and 'Status page updated at:' in text
    assert 'does not prove the cause' in text


@pytest.mark.parametrize('reported,code',[(True,0),(False,1)])
def test_cli_calls_only_new_read_only_path(reported,code,monkeypatch,tmp_path,capsys):
    import agent
    def forbidden(*args,**kwargs):
        pytest.fail('mixed mode reached model, workflow, approval or saved state')
    for name in ('make_client','run_escalation','load_state','save_state','record_simulated_action'):
        monkeypatch.setattr(agent,name,forbidden)
    def run():
        return asyncio.run(collect(lambda request:httpx.Response(200,json=payload()) if reported else httpx.Response(503)))
    monkeypatch.setattr(gh,'run_github_collection',run)
    monkeypatch.chdir(tmp_path)
    assert main(['--github-status'],ask=forbidden)==code
    assert 'GitHub reported status: '+('none' if reported else 'unknown') in capsys.readouterr().out
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('extra',[
    ['--real'],['--sample'],['--fresh'],['--list'],['--defer-approval'],['ESC-1001'],
    ['--investigate','unused.json'],['--collect-sample','partial'],
])
def test_mode_conflicts_are_rejected_before_network(extra,monkeypatch):
    monkeypatch.setattr(gh,'run_github_collection',lambda:pytest.fail('must reject before any request'))
    with pytest.raises(SystemExit) as exc:
        main(['--github-status',*extra])
    assert exc.value.code==2
