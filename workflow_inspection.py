"""Read a public Actions run, its pinned-attempt jobs and deployment gates.

GET only. No credentials, logs, approvals, cancellations or reruns.
"""
import asyncio
from datetime import datetime, timezone
import re
from urllib.parse import urlsplit

import httpx
from errors import AgentError

RUN_STATES = {'queued','requested','waiting','pending','in_progress','completed'}
CONCLUSIONS = {'success','failure','neutral','cancelled','skipped','timed_out','action_required','stale','startup_failure'}
HEADERS = {'Accept':'application/vnd.github+json','User-Agent':'escalation-triage-agent/run-reader','X-GitHub-Api-Version':'2026-03-10'}
MAX_JOB_PAGES = 5


def parse_run_url(url):
    if not isinstance(url,str):
        raise AgentError('BAD_TOOL_ARGS','Provide a public GitHub Actions run URL.')
    try:
        parsed=urlsplit(url)
    except ValueError:
        raise AgentError('BAD_TOOL_ARGS','Invalid GitHub run URL.') from None
    if any(c.isspace() for c in url):
        raise AgentError('BAD_TOOL_ARGS','The run URL cannot contain whitespace.')
    if parsed.scheme!='https' or parsed.netloc!='github.com' or parsed.query or parsed.fragment:
        raise AgentError('BAD_TOOL_ARGS','Use an https://github.com/OWNER/REPO/actions/runs/NUMBER URL without query, fragment or credentials.')
    match=re.fullmatch(r'/([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+)/actions/runs/([1-9][0-9]*)/?',parsed.path)
    if not match or match[2] in ('.','..'):
        raise AgentError('BAD_TOOL_ARGS','Use the run page URL, not a pull request, job, attempt or external URL.')
    owner,repo,run_id=match.groups()
    return dict(owner=owner,repo=repo,id=int(run_id),
                html_url=f'https://github.com/{owner}/{repo}/actions/runs/{run_id}',
                api_url=f'https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}')


def stamp(value):
    if not isinstance(value,str):
        raise ValueError('missing timestamp')
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('missing timezone')
    return parsed.isoformat()


def positive_integer(value):
    return type(value) is int and value>0


def parse_state(row):
    status,conclusion=row.get('status'),row.get('conclusion')
    if not isinstance(status,str) or status not in RUN_STATES:
        raise ValueError('unknown state')
    if conclusion is not None and (not isinstance(conclusion,str) or conclusion not in CONCLUSIONS):
        raise ValueError('unknown conclusion')
    if (status=='completed') != (conclusion is not None):
        raise ValueError('inconsistent status and conclusion')
    return status,conclusion


def parse_run(data, target):
    if not isinstance(data,dict) or not positive_integer(data.get('id')) or data.get('id')!=target['id'] or not positive_integer(data.get('run_attempt')):
        raise ValueError('wrong run or missing attempt')
    repo=data.get('repository')
    if not isinstance(repo,dict) or repo.get('private') is not False or not isinstance(repo.get('full_name'),str) or repo['full_name'].casefold()!=f"{target['owner']}/{target['repo']}".casefold():
        raise ValueError('not the requested public repository')
    if not isinstance(data.get('html_url'),str) or data['html_url'].rstrip('/').casefold()!=target['html_url'].casefold():
        raise ValueError('wrong run link')
    status,conclusion=parse_state(data)
    return dict(id=data['id'],run_attempt=data['run_attempt'],status=status,conclusion=conclusion,
                created_at=stamp(data.get('created_at')),updated_at=stamp(data.get('updated_at')),
                html_url=target['html_url'],
                workflow_path=data.get('path') if isinstance(data.get('path'),str) else None,
                event=data.get('event') if isinstance(data.get('event'),str) else None,
                head_sha=data.get('head_sha') if isinstance(data.get('head_sha'),str) and re.fullmatch(r'[0-9a-fA-F]{40}',data['head_sha']) else None,
                check_suite_id=data.get('check_suite_id') if positive_integer(data.get('check_suite_id')) else None)


async def get_json(client,url,params=None):
    try:
        response=await asyncio.wait_for(client.get(url,params=params,headers=HEADERS,timeout=4,follow_redirects=False),5)
        if response.status_code!=200:
            return dict(state='unknown',source_url=url,error=f'HTTP {response.status_code}; unavailable, inaccessible or rate-limited. No state inferred.')
        return dict(state='reported',source_url=url,data=response.json())
    except (TimeoutError,httpx.TimeoutException):
        return dict(state='unknown',source_url=url,error='Request timed out. No state inferred.')
    except (httpx.RequestError,ValueError,UnicodeError):
        return dict(state='unknown',source_url=url,error='Request failed or returned invalid JSON. No state inferred.')


async def read_jobs(client,target,attempt):
    url=f"{target['api_url']}/attempts/{attempt}/jobs"
    jobs,seen=[],set()
    for page in range(1,MAX_JOB_PAGES+1):
        response=await get_json(client,url,dict(per_page=100,page=page))
        if response['state']!='reported':
            return dict(response,jobs=jobs,state='partial' if jobs else 'unknown')
        data=response['data']
        try:
            if not isinstance(data,dict) or type(data.get('total_count')) is not int or data['total_count']<0 or not isinstance(data.get('jobs'),list):
                raise ValueError('invalid jobs envelope')
            if len(data['jobs'])>100:
                raise ValueError('invalid page length')
            new=[]
            for job in data['jobs']:
                if not isinstance(job,dict) or not positive_integer(job.get('id')) or job['id'] in seen or not positive_integer(job.get('run_id')) or job.get('run_id')!=target['id']:
                    raise ValueError('invalid or repeated job')
                if 'run_attempt' in job and (not positive_integer(job['run_attempt']) or job['run_attempt']!=attempt):
                    raise ValueError('wrong attempt')
                status,conclusion=parse_state(job)
                if not isinstance(job.get('name'),str) or not job['name'].strip():
                    raise ValueError('missing job name')
                from workflow_error_details import parse_steps
                seen.add(job['id'])
                new.append(dict(id=job['id'],name=job['name'],status=status,conclusion=conclusion,step_details=parse_steps(job.get('steps')),check_run_reference=job.get('check_run_url')))
            jobs.extend(new)
            if len(jobs)>data['total_count']:
                raise ValueError('inconsistent count')
            if len(jobs)==data['total_count']:
                return dict(state='reported',source_url=url,jobs=jobs)
            if len(data['jobs'])<100:
                return dict(state='partial',source_url=url,jobs=jobs,error='Job list is incomplete or changed during collection.')
        except (ValueError,TypeError):
            return dict(state='partial' if jobs else 'unknown',source_url=url,jobs=jobs,error='Malformed or inconsistent jobs; remaining state is unknown.')
    return dict(state='partial',source_url=url,jobs=jobs,error='Stopped after 500 jobs. Remaining jobs are unknown.')


async def read_gates(client,target):
    response=await get_json(client,target['api_url']+'/pending_deployments')
    if response['state']!='reported':
        return dict(response,gates=[])
    data=response['data']
    if not isinstance(data,list):
        return dict(state='unknown',source_url=response['source_url'],gates=[],error='Malformed deployment-gate response.')
    gates=[]
    for row in data:
        if not isinstance(row,dict) or not isinstance(row.get('environment'),dict) or not isinstance(row['environment'].get('name'),str) or not row['environment']['name'].strip() or not isinstance(row.get('reviewers'),list) or type(row.get('wait_timer')) is not int or row['wait_timer']<0:
            return dict(state='unknown',source_url=response['source_url'],gates=[],error='Malformed deployment gate; approval state unknown.')
        reviewers=row['reviewers']
        if any(not isinstance(r,dict) or r.get('type') not in ('User','Team') or not isinstance(r.get('reviewer'),dict) or not (positive_integer(r['reviewer'].get('id')) or (isinstance(r['reviewer'].get('login' if r['type']=='User' else 'slug'),str) and r['reviewer']['login' if r['type']=='User' else 'slug'].strip())) for r in reviewers):
            return dict(state='unknown',source_url=response['source_url'],gates=[],error='Unrecognized reviewer data; approval state unknown.')
        gates.append(dict(environment=row['environment']['name'],review_required=bool(reviewers),wait_timer_minutes=row['wait_timer']))
    return dict(state='reported',source_url=response['source_url'],gates=gates)


async def inspect_run(client,url):
    target=parse_run_url(url)  # validate before making any request
    result=dict(run_url=target['html_url'],observed_at=datetime.now(timezone.utc).isoformat(),
                confirmed_root_cause=None,action_proposed=False,action_mode='read_only',
                assessment='unknown',complete=False)
    response=await get_json(client,target['api_url'])
    if response['state']!='reported':
        return dict(result,run=response,message='The public run could not be read. It may be inaccessible, missing or rate-limited.')
    try:
        run=parse_run(response['data'],target)
    except (ValueError,TypeError):
        return dict(result,run=dict(state='unknown',source_url=target['api_url']),message='The response did not identify a consistent public run. No state inferred.')
    result['run']=dict(state='reported',source_url=target['api_url'],**run)
    if run['status']=='completed':
        jobs=await read_jobs(client,target,run['run_attempt'])
        gates=dict(state='not_checked',gates=[],reason='The run was already completed; no current waiting approval is inferred.')
    else:
        jobs,gates=await asyncio.gather(read_jobs(client,target,run['run_attempt']),read_gates(client,target))
    result.update(jobs=jobs,deployment_gates=gates)
    from workflow_error_details import collect_error_details
    result['error_details'] = await collect_error_details(client,target,run,jobs['jobs'])
    recheck=await get_json(client,target['api_url'])
    try:
        current=parse_run(recheck.get('data'),target)
        consistent=all(current[k]==run[k] for k in ('run_attempt','status','conclusion','updated_at','head_sha','check_suite_id','workflow_path','event'))
    except (ValueError,TypeError):
        consistent=None
    result['snapshot_consistent']=consistent
    if consistent is not True:
        return dict(result,message='The run changed during collection or could not be rechecked. Retry before combining the run and job states.',assessment='snapshot_uncertain')
    result['complete']=jobs['state']=='reported' and gates['state'] in ('reported','not_checked') and result['error_details']['state'] in ('reported','not_needed')
    if run['status']=='completed':
        assessment='completed_'+run['conclusion']
        message=f"GitHub reports this run completed with conclusion {run['conclusion']}. That is an outcome, not an explanation of its cause."
    elif gates['state']=='reported' and any(g['review_required'] for g in gates['gates']):
        assessment='pending_deployment_review'
        message='GitHub reports a pending deployment with required reviewers. This may be one blocker; it does not establish that every job is waiting on approval.'
    elif gates['state']=='reported' and gates['gates']:
        assessment='pending_deployment_protection'
        message='GitHub reports pending deployment protection. A timer or other rule may be involved; required human review was not reported.'
    else:
        assessment=run['status']
        message=f"GitHub reports this run as {run['status']}. Its reason is not established by that state alone. Waiting does not automatically mean human approval."
    result.update(assessment=assessment,message=message)
    return result


async def _inspect(url):
    parse_run_url(url)
    async with httpx.AsyncClient(trust_env=False) as client:
        return await inspect_run(client,url)


def inspect_public_run(url):
    return asyncio.run(_inspect(url))


def render_run(result):
    from workflow_error_details import clip_text

    lines=['Public GitHub Actions run inspection. No actions will run.',
           'Run: '+result['run_url'],'Collection started at: '+result['observed_at'],
           'Assessment: '+result['assessment'],result['message']]
    run=result['run']
    if run['state']=='reported':
        lines += [f"Reported attempt: {run['run_attempt']}", 'Run created at: '+run['created_at'],
                  'Run last updated at: '+run['updated_at'],'Run source: '+run['source_url']]
    for key,title in (('jobs','Jobs'),('deployment_gates','Deployment gates')):
        if key in result:
            detail=result[key]
            lines.append(title+': '+detail['state'])
            if detail.get('source_url'): lines.append('Source: '+detail['source_url'])
            if detail.get('error'): lines.append(detail['error'])
    for job in result.get('jobs',{}).get('jobs',[]):
        display_name,_=clip_text(job['name'],250)
        lines.append(f"- {display_name}: {job['status']}"+(f" / {job['conclusion']}" if job['conclusion'] else ''))
    for gate in result.get('deployment_gates',{}).get('gates',[]):
        lines.append(f"- Environment {gate['environment']}: required reviewers {'reported' if gate['review_required'] else 'not reported'}; configured wait timer {gate['wait_timer_minutes']} minutes.")
    next_check='open this run on GitHub and inspect the reported job or gate. Do not infer a root cause from its status.'
    if 'error_details' in result:
        from workflow_error_details import BAD_CONCLUSIONS, render_error_details
        details=result['error_details']
        lines.extend(render_error_details(details))
        failed_step=next(((job,step) for job in details['jobs'] for step in job['steps']['steps']
                          if step['conclusion'] in BAD_CONCLUSIONS),None)
        if failed_step:
            job,step=failed_step
            name=' '.join(clip_text(job['job_name'],250)[0].split())
            next_check=f"open step {step['number']} in job {name} on GitHub. Compare what the step expected with what it observed."
    lines += ['', 'Next check: '+next_check,
              'Collection: '+('complete' if result['complete'] else 'incomplete; some state remains unknown'),
              'Confirmed root cause: none']
    return '\n'.join(lines)
