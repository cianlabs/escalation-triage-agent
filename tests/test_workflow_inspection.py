"""Read-only public run inspection on fake HTTP responses, including races."""
import asyncio
import copy

import httpx
import pytest

import workflow_inspection as wi
from agent import main
from errors import AgentError

URL='https://github.com/example/project/actions/runs/123'
API='https://api.github.com/repos/example/project/actions/runs/123'
TIME='2026-11-01T12:00:00Z'


def run_data(status='completed',conclusion='success',attempt=2):
    return dict(id=123,run_attempt=attempt,status=status,conclusion=conclusion,
                repository=dict(private=False,full_name='example/project'),html_url=URL,created_at=TIME,updated_at=TIME)


def job(id=1,status='completed',conclusion='success'):
    return dict(id=id,run_id=123,run_attempt=2,name='test-'+str(id),status=status,conclusion=conclusion)


def inspect(run=None,jobs=None,gates=None,second=None,job_code=200,gate_code=200,requests=None):
    run=run if run is not None else run_data()
    jobs=jobs if jobs is not None else dict(total_count=1,jobs=[job()])
    gates=gates if gates is not None else []
    root_calls=0
    def handler(request):
        nonlocal root_calls
        if requests is not None: requests.append(request)
        if request.url.path.endswith('/jobs'):
            return httpx.Response(job_code,json=jobs)
        if request.url.path.endswith('/pending_deployments'):
            return httpx.Response(gate_code,json=gates)
        assert str(request.url)==API
        root_calls+=1
        return httpx.Response(200,json=second if root_calls>1 and second is not None else run)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await wi.inspect_run(client,URL)
    return asyncio.run(scenario())


@pytest.mark.parametrize('url',[
    'http://github.com/a/b/actions/runs/1','https://evil.com/a/b/actions/runs/1',
    'https://github.com.evil.com/a/b/actions/runs/1','https://user:secret@github.com/a/b/actions/runs/1',
    'https://github.com:443/a/b/actions/runs/1','https://github.com/a/b/actions/runs/1?token=secret',
    'https://github.com/a/b/actions/runs/1#job','https://github.com/a/b/pull/1',
    'https://github.com/a/b/actions/runs/1/attempts/2','https://github.com/a/b/actions/runs/1/job/2',
    'https://github.com/a/../actions/runs/1','https://github.com/a/%2e%2e/actions/runs/1',
    'https://github.com/a/b/actions/runs/0','https://[invalid',' https://github.com/a/b/actions/runs/1',
])
def test_invalid_url_rejected_without_network(url):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:pytest.fail('invalid URL requested network'))) as client:
            with pytest.raises(AgentError,match='BAD_TOOL_ARGS'):
                await wi.inspect_run(client,url)
    asyncio.run(scenario())


def test_finished_success_is_read_only_and_jobs_are_pinned():
    requests=[]
    result=inspect(requests=requests)
    assert result['assessment']=='completed_success' and result['complete']
    assert len(requests)==3
    assert requests[1].url.path.endswith('/attempts/2/jobs')
    assert all(r.method=='GET' and r.url.host=='api.github.com' and not r.content for r in requests)
    assert all('authorization' not in r.headers and 'cookie' not in r.headers for r in requests)
    assert all('pending_deployments' not in r.url.path for r in requests)
    assert result['confirmed_root_cause'] is None and not result['action_proposed']
    assert result['observed_at'].endswith('+00:00')


@pytest.mark.parametrize('conclusion',sorted(wi.CONCLUSIONS))
def test_each_completed_outcome_is_reported_without_explaining_cause(conclusion):
    result=inspect(run_data(conclusion=conclusion),dict(total_count=1,jobs=[job(conclusion=conclusion)]))
    assert result['assessment']=='completed_'+conclusion
    assert 'not an explanation' in result['message']


@pytest.mark.parametrize('status',['queued','requested','waiting','pending','in_progress'])
def test_run_state_does_not_automatically_mean_stuck_or_needs_approval(status):
    result=inspect(run_data(status,None),dict(total_count=1,jobs=[job(status=status,conclusion=None)]))
    assert result['assessment']==status
    assert 'does not automatically mean human approval' in result['message']
    assert result['complete']


@pytest.mark.parametrize('reviewers,expected',[
    ([dict(type='User',reviewer=dict(login='reviewer'))],'pending_deployment_review'),
    ([], 'pending_deployment_protection'),
])
def test_reported_pending_gate_distinguishes_review_from_other_protection(reviewers,expected):
    result=inspect(run_data('waiting',None),gates=[dict(environment=dict(name='staging'),reviewers=reviewers,wait_timer=30)])
    assert result['assessment']==expected
    assert result['confirmed_root_cause'] is None
    assert not result['action_proposed']


def test_missing_gate_details_do_not_become_approval_claim():
    result=inspect(run_data('waiting',None),gate_code=403)
    assert result['assessment']=='waiting'
    assert result['deployment_gates']['state']=='unknown'
    assert not result['complete']


@pytest.mark.parametrize('field,value',[
    ('id',999),('id',True),('run_attempt',True),('run_attempt',0),('status','future-status'),
    ('status','in_progress'),('conclusion',None),('updated_at','yesterday'),
    ('updated_at','2026-11-01T12:00:00'),('html_url','https://evil.com'),
    ('repository',dict(private=True,full_name='example/project')),
    ('repository',dict(private=False,full_name='other/repo')),
])
def test_malformed_or_wrong_root_never_becomes_a_known_run(field,value):
    data=run_data()
    data[field]=value
    result=inspect(data)
    assert result['run']['state']=='unknown'
    assert not result['complete']
    assert 'jobs' not in result


def test_rerun_between_requests_invalidates_combined_snapshot():
    result=inspect(second=run_data('queued',None,attempt=3))
    assert result['assessment']=='snapshot_uncertain'
    assert result['snapshot_consistent'] is False
    assert not result['complete']


def test_normal_progress_during_requests_is_also_reported():
    result=inspect(run_data('queued',None),second=run_data('in_progress',None))
    assert result['assessment']=='snapshot_uncertain'


@pytest.mark.parametrize('jobs',[
    {},dict(total_count=True,jobs=[]),dict(total_count=1,jobs=[job(),job()]),
    dict(total_count=1,jobs=[dict(job(),run_id=999)]),
    dict(total_count=1,jobs=[dict(job(),run_attempt=1)]),
    dict(total_count=1,jobs=[dict(job(),status='future-state')]),
])
def test_bad_job_data_keeps_detail_unknown(jobs):
    result=inspect(jobs=jobs)
    assert not result['complete']
    assert result['jobs']['state'] in ('unknown','partial')


def test_short_incomplete_page_is_explicitly_partial():
    result=inspect(jobs=dict(total_count=2,jobs=[job()]))
    assert result['jobs']['state']=='partial'
    assert not result['complete']


def test_all_job_pages_are_read_without_following_returned_links():
    calls=[]
    def handler(request):
        calls.append(request)
        if request.url.path.endswith('/jobs'):
            page=int(request.url.params['page'])
            jobs=[job(i) for i in (range(1,101) if page==1 else range(101,102))]
            return httpx.Response(200,json=dict(total_count=101,jobs=jobs),headers={'Link':'<https://evil.com>; rel="next"'})
        return httpx.Response(200,json=run_data())
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await wi.inspect_run(client,URL)
    result=asyncio.run(scenario())
    assert len(result['jobs']['jobs'])==101
    assert result['complete']
    assert all(r.url.host=='api.github.com' for r in calls)


@pytest.mark.parametrize('status',[302,403,404,429,500])
def test_root_http_errors_are_unknown_with_no_followup(status):
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(status,headers={'Location':'https://evil.com'})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await wi.inspect_run(client,URL)
    result=asyncio.run(scenario())
    assert len(calls)==1
    assert result['assessment']=='unknown'
    assert not result['complete']


@pytest.mark.parametrize('error',[httpx.ConnectError,httpx.ReadTimeout])
def test_request_failure_details_do_not_leak(error):
    def handler(request):
        raise error('SECRET credential',request=request)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await wi.inspect_run(client,URL)
    result=asyncio.run(scenario())
    assert not result['complete']
    assert 'SECRET' not in wi.render_run(result)


def test_cli_uses_no_model_approval_or_memory(monkeypatch,tmp_path,capsys):
    import agent
    def forbidden(*args,**kwargs):
        pytest.fail('run inspection entered a workflow/model/memory/action path')
    for name in ('make_client','run_escalation','load_state','save_state','record_simulated_action'):
        monkeypatch.setattr(agent,name,forbidden)
    monkeypatch.setattr(wi,'inspect_public_run',lambda url:inspect())
    monkeypatch.chdir(tmp_path)
    assert main(['--workflow-run',URL],ask=forbidden)==0
    assert 'completed_success' in capsys.readouterr().out
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('extra',[
    ['--github-status'],['--problem','failure'],['--component','actions'],['--real'],
    ['--sample'],['--fresh'],['--list'],['--defer-approval'],['ESC-1001'],
    ['--collect-sample','partial'],['--investigate','unused.json'],
])
def test_mixed_modes_fail_before_requests(extra,monkeypatch):
    monkeypatch.setattr(wi,'inspect_public_run',lambda url:pytest.fail('invalid combination made a request'))
    with pytest.raises(SystemExit) as err:
        main(['--workflow-run',URL,*extra])
    assert err.value.code==2


@pytest.mark.parametrize('gates',[
    {},[dict(environment=dict(name=''),reviewers=[],wait_timer=0)],
    [dict(environment=dict(name='staging'),reviewers=[dict(type='User',reviewer={})],wait_timer=0)],
])
def test_bad_gate_details_remain_unknown(gates):
    result=inspect(run_data('waiting',None),gates=gates)
    assert result['assessment']=='waiting'
    assert result['deployment_gates']['state']=='unknown'
    assert not result['complete']


def test_jobs_failure_keeps_known_run_outcome_but_marks_collection_incomplete():
    result=inspect(job_code=503)
    assert result['assessment']=='completed_success'
    assert result['jobs']['state']=='unknown'
    assert not result['complete']


def test_pagination_limit_is_visible_instead_of_claiming_all_jobs():
    requests=[]
    def handler(request):
        requests.append(request)
        if request.url.path.endswith('/jobs'):
            page=int(request.url.params['page'])
            return httpx.Response(200,json=dict(total_count=600,jobs=[job(i) for i in range((page-1)*100+1,page*100+1)]))
        return httpx.Response(200,json=run_data())
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await wi.inspect_run(client,URL)
    result=asyncio.run(scenario())
    assert len(result['jobs']['jobs'])==500
    assert result['jobs']['state']=='partial'
    assert not result['complete']
    assert len([r for r in requests if r.url.path.endswith('/jobs')])==5


def test_failed_recheck_leaves_snapshot_unknown():
    calls=0
    def handler(request):
        nonlocal calls
        if request.url.path.endswith('/jobs'):
            return httpx.Response(200,json=dict(total_count=1,jobs=[job()]))
        calls+=1
        return httpx.Response(200,json=run_data()) if calls==1 else httpx.Response(403)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await wi.inspect_run(client,URL)
    result=asyncio.run(scenario())
    assert result['assessment']=='snapshot_uncertain'
    assert result['snapshot_consistent'] is None
    assert not result['complete']
