"""Concurrency is checked with events, not a fragile elapsed-time comparison."""
import asyncio
import copy

import pytest

from errors import AgentError
from evidence_collection import EvidenceCheck, collect_evidence, collect_and_investigate, simulated_checks, run_simulated_collection
from agent import main


def evidence(text='The service is unavailable.', id='1'):
    return dict(id=id,source='synthetic probe',observation=text)


def test_all_three_checks_start_before_any_may_finish():
    async def scenario():
        started={name:asyncio.Event() for name in ('errors','changes','health')}
        async def read(name):
            started[name].set()
            await asyncio.gather(*(event.wait() for event in started.values()))
            return [evidence(id=name)]
        checks=[EvidenceCheck(name,lambda name=name:read(name),0.5) for name in started]
        result=await asyncio.wait_for(collect_evidence(checks),1)
        assert [s['status'] for s in result['sources']]==['ok']*3
        assert [s['name'] for s in result['sources']]==list(started)
        assert result['status']=='complete'
    asyncio.run(scenario())


def test_failure_and_timeout_keep_success_and_cancel_slow_reader():
    async def scenario():
        cleaned=asyncio.Event()
        async def good():
            return [evidence('The routing table is missing a route.')]
        async def bad():
            raise RuntimeError('private credential must never be printed')
        async def slow():
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()
        result=await collect_and_investigate('Cannot connect.',[
            EvidenceCheck('errors',good,0.5),EvidenceCheck('changes',bad,0.5),EvidenceCheck('health',slow,0.01)])
        assert cleaned.is_set()
        assert result['collection']['status']=='partial'
        assert [s['status'] for s in result['collection']['sources']]==['ok','failed','timeout']
        assert result['collection']['missing_sources']==['changes','health']
        assert result['collection_incomplete']
        assert result['hypotheses'][0]['supporting_evidence_ids']==['errors::1']
        assert any('changes, health' in note for note in result['hypotheses'][0]['missing_evidence'])
        assert 'private credential' not in str(result)
        assert result['confirmed_root_cause'] is None
        assert not result['action_proposed']
    asyncio.run(scenario())


def test_a_successful_probe_can_report_unhealthy_service():
    async def read():
        return [evidence('The endpoint is unavailable.')]
    result=asyncio.run(collect_evidence([EvidenceCheck('health',read)]))
    assert result['sources'][0]['status']=='ok'
    assert result['evidence'][0]['observation']=='The endpoint is unavailable.'
    assert 'does not imply service health' in result['sources'][0]['message']


def test_empty_results_do_not_imply_health_or_support_a_cause():
    async def read():
        return []
    result=asyncio.run(collect_and_investigate('Broken.',[EvidenceCheck('health',read)]))
    assert result['collection']['sources'][0]['status']=='empty'
    assert 'not evidence' in result['collection']['sources'][0]['message']
    assert result['assessment']=='insufficient_evidence'


def test_all_sources_failing_leaves_no_invented_evidence():
    result=run_simulated_collection('failed')
    assert result['collection']['status']=='failed'
    assert result['evidence']==[]
    assert result['hypotheses']==[]
    assert result['assessment']=='insufficient_evidence'
    assert result['confirmed_root_cause'] is None


@pytest.mark.parametrize('raw',[None,{},[{}],[evidence(),evidence()]])
def test_malformed_source_does_not_discard_another_source(raw):
    async def bad():
        return raw
    async def good():
        return [evidence()]
    result=asyncio.run(collect_evidence([EvidenceCheck('bad',bad),EvidenceCheck('good',good)]))
    assert result['sources'][0]['status']=='invalid_result'
    assert result['status']=='partial'
    assert len(result['evidence'])==1
    assert result['evidence'][0]['id']=='good::1'


def test_ids_are_namespaced_and_source_results_not_mutated():
    rows=[evidence()]
    original=copy.deepcopy(rows)
    async def read():
        return rows
    result=asyncio.run(collect_evidence([EvidenceCheck('a',read),EvidenceCheck('b',read)]))
    assert [e['id'] for e in result['evidence']]==['a::1','b::1']
    assert [e['source'] for e in result['evidence']]==['a: synthetic probe','b: synthetic probe']
    result['evidence'][0]['observation']='changed'
    assert rows==original


def test_result_order_is_source_order_not_completion_order():
    async def scenario():
        release=asyncio.Event()
        async def first():
            await release.wait()
            return [evidence(id='first')]
        async def second():
            release.set()
            return [evidence(id='second')]
        result=await collect_evidence([EvidenceCheck('first',first),EvidenceCheck('second',second)])
        assert [s['name'] for s in result['sources']]==['first','second']
    asyncio.run(scenario())


def test_one_source_cancelling_itself_is_a_missing_source():
    async def cancel():
        raise asyncio.CancelledError
    async def good():
        return [evidence()]
    result=asyncio.run(collect_evidence([EvidenceCheck('cancelled',cancel),EvidenceCheck('good',good)]))
    assert result['sources'][0]['status']=='cancelled'
    assert result['status']=='partial'
    assert result['missing_sources']==['cancelled']


def test_caller_cancellation_drains_all_readers():
    async def scenario():
        started=[asyncio.Event() for _ in range(3)]
        stopped=[asyncio.Event() for _ in range(3)]
        async def read(i):
            started[i].set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped[i].set()
        task=asyncio.create_task(collect_evidence([EvidenceCheck(str(i),lambda i=i:read(i),10) for i in range(3)]))
        await asyncio.wait_for(asyncio.gather(*(e.wait() for e in started)),1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert all(e.is_set() for e in stopped)
    asyncio.run(scenario())


@pytest.mark.parametrize('timeout',[0,-1,True,float('nan'),float('inf'),'1'])
def test_invalid_timeout_is_rejected_before_any_reader_starts(timeout):
    async def forbidden():
        pytest.fail('invalid configuration must not start readers')
    with pytest.raises(AgentError,match='BAD_SETTINGS'):
        asyncio.run(collect_evidence([EvidenceCheck('source',forbidden,timeout)]))


@pytest.mark.parametrize('names',[['same','same'],[''],['a::b']])
def test_invalid_source_names_are_rejected(names):
    async def forbidden():
        pytest.fail('invalid source configuration')
    with pytest.raises(AgentError,match='BAD_SETTINGS'):
        asyncio.run(collect_evidence([EvidenceCheck(name,forbidden) for name in names]))


def test_invalid_symptom_is_rejected_before_collecting():
    async def forbidden():
        pytest.fail('invalid symptom must not start a source')
    with pytest.raises(AgentError,match='BAD_TOOL_ARGS'):
        asyncio.run(collect_and_investigate('',[EvidenceCheck('source',forbidden)]))


@pytest.mark.parametrize('scenario,code',[('complete',0),('partial',0),('failed',1)])
def test_cli_simulation_never_calls_workflow_model_network_or_memory(scenario,code,tmp_path,monkeypatch,capsys):
    import agent
    import socket
    def forbidden(*args,**kwargs):
        pytest.fail('simulation entered a real system, model, workflow or memory path')
    for name in ('run_escalation','make_client','load_state','save_state','record_simulated_action'):
        monkeypatch.setattr(agent,name,forbidden)
    monkeypatch.setattr(socket,'create_connection',forbidden)
    monkeypatch.chdir(tmp_path)
    assert main(['--collect-sample',scenario],ask=forbidden)==code
    out=capsys.readouterr().out
    assert 'Synthetic evidence collection' in out
    assert 'Confirmed root cause: none' in out
    assert 'Collection: '+('complete' if scenario=='complete' else ('partial' if scenario=='partial' else 'failed')) in out
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('extra',[['--real'],['--sample'],['--fresh'],['--list'],['--defer-approval'],['ESC-1001'],['--investigate','unused.json']])
def test_collection_mode_rejects_workflow_options(extra):
    with pytest.raises(SystemExit) as exc:
        main(['--collect-sample','partial',*extra])
    assert exc.value.code==2
