"""Bounded, read-only failed-step and check-annotation collection.

Provider text is displayed as unverified text, never executed or passed to a model.
"""
import asyncio
import re
import unicodedata

from workflow_inspection import get_json, parse_state, positive_integer

MAX_FAILED_JOBS = 5
MAX_STEPS = 200
MAX_ANNOTATIONS = 100
MAX_DISPLAY_ANNOTATIONS = 10
MAX_TEXT = 1000
BAD_CONCLUSIONS = {'failure','timed_out','startup_failure'}


def clip_text(value,limit=MAX_TEXT):
    # Neutralize terminal controls; keep ordinary line breaks and tabs as text.
    clean=''.join(c for c in value if c in '\n\t' or not unicodedata.category(c).startswith('C'))
    return clean[:limit],len(clean)>limit


def parse_steps(raw):
    if not isinstance(raw,list):
        return dict(state='unknown',steps=[],error='Step details were not supplied.')
    steps,seen=[],set()
    try:
        for row in raw[:MAX_STEPS]:
            if not isinstance(row,dict) or not positive_integer(row.get('number')) or row['number'] in seen or not isinstance(row.get('name'),str) or not row['name'].strip():
                raise ValueError('invalid step')
            status,conclusion=parse_state(row)
            seen.add(row['number'])
            name,truncated=clip_text(row['name'],250)
            steps.append(dict(number=row['number'],name=name,status=status,conclusion=conclusion,name_truncated=truncated))
    except (ValueError,TypeError):
        return dict(state='unknown',steps=[],error='Malformed step data; no failed step was inferred.')
    return dict(state='partial' if len(raw)>MAX_STEPS or any(s['name_truncated'] for s in steps) else 'reported',steps=steps)


def check_url(target,reference):
    if not isinstance(reference,str):
        return None
    prefix=f"https://api.github.com/repos/{target['owner']}/{target['repo']}/check-runs/"
    match=re.fullmatch(re.escape(prefix)+r'([1-9][0-9]*)',reference,re.I)
    return (prefix+match[1],int(match[1])) if match else None


def parse_annotations(raw):
    if not isinstance(raw,list) or len(raw)>MAX_ANNOTATIONS:
        raise ValueError('invalid annotations page')
    annotations=[]
    for row in raw:
        if not isinstance(row,dict) or row.get('annotation_level') not in ('failure','warning','notice') or not isinstance(row.get('message'),str) or not isinstance(row.get('path'),str) or not positive_integer(row.get('start_line')) or not positive_integer(row.get('end_line')) or row['end_line']<row['start_line']:
            raise ValueError('invalid annotation')
        message,truncated=clip_text(row['message'])
        path,path_truncated=clip_text(row['path'],250)
        annotations.append(dict(level=row['annotation_level'],message=message,path=path,
                                start_line=row['start_line'],end_line=row['end_line'],text_truncated=truncated or path_truncated))
    return annotations


async def read_annotations(client,target,run,job):
    ref=check_url(target,job.get('check_run_reference'))
    unknown=dict(state='unknown',annotations=[],error='A verified check-run reference and run identity are required. No annotation inferred.')
    if ref is None or not run.get('head_sha') or not run.get('check_suite_id'):
        return unknown
    url,cid=ref
    metadata=await get_json(client,url)
    if metadata['state']!='reported':
        return dict(metadata,annotations=[])
    data=metadata['data']
    try:
        if not isinstance(data,dict) or not positive_integer(data.get('id')) or data['id']!=cid or data.get('head_sha')!=run['head_sha'] or not isinstance(data.get('check_suite'),dict) or not positive_integer(data['check_suite'].get('id')) or data['check_suite']['id']!=run['check_suite_id'] or data.get('name')!=job['name']:
            raise ValueError('check identity mismatch')
        status,conclusion=parse_state(data)
        if status!=job['status'] or conclusion!=job['conclusion']:
            raise ValueError('check state mismatch')
        output=data.get('output')
        if not isinstance(output,dict) or type(output.get('annotations_count')) is not int or output['annotations_count']<0:
            raise ValueError('unknown annotation count')
    except (ValueError,TypeError):
        return dict(unknown,source_url=url,error='Check identity or state could not be matched to this run and job.')
    count=output['annotations_count']
    annotation_url=url+'/annotations'  # never follow output.annotations_url
    if count==0:
        return dict(state='reported',source_url=annotation_url,annotations=[],total_count=0)
    response=await get_json(client,annotation_url,dict(per_page=MAX_ANNOTATIONS,page=1))
    if response['state']!='reported':
        return dict(response,annotations=[])
    try:
        annotations=parse_annotations(response['data'])
    except (ValueError,TypeError):
        return dict(unknown,source_url=annotation_url,error='Malformed annotations; no error explanation inferred.')
    complete=len(annotations)==count and not any(a['text_truncated'] for a in annotations)
    return dict(state='reported' if complete else 'partial',source_url=annotation_url,
                annotations=annotations,total_count=count,
                error=None if complete else 'Annotation collection or text is truncated or changed. Remaining details are unknown.')


async def collect_error_details(client,target,run,jobs):
    failed=[j for j in jobs if j['conclusion'] in BAD_CONCLUSIONS]
    if not failed:
        return dict(state='not_needed' if run['conclusion'] not in BAD_CONCLUSIONS else 'unknown',jobs=[],
                    message='No failed jobs were returned for step and annotation inspection.')
    async def inspect(job):
        annotations=await read_annotations(client,target,run,job)
        return dict(job_id=job['id'],job_name=job['name'],steps=job['step_details'],annotations=annotations)
    details=await asyncio.gather(*(inspect(j) for j in failed[:MAX_FAILED_JOBS]))
    complete=len(failed)<=MAX_FAILED_JOBS and all(j['steps']['state']=='reported' and j['annotations']['state']=='reported' for j in details)
    return dict(state='reported' if complete else 'partial',jobs=details,
                message='Provider error details; these are not verified root causes.' if complete else
                'Some failed-job, step or annotation details are unavailable or limited. No explanation was invented.')


def render_error_details(details):
    lines=['', 'Failure details: '+details['state'],details['message']]
    for job in details['jobs']:
        name,_=clip_text(job['job_name'],250)
        lines.append('Job: '+name)
        steps=job['steps']
        lines.append('Step details: '+steps['state'])
        failed=[s for s in steps['steps'] if s['conclusion'] in BAD_CONCLUSIONS]
        for step in failed:
            lines.append(f"- Failed step {step['number']}: {step['name']} ({step['conclusion']})")
        if steps['state']=='reported' and not failed:
            lines.append('No failed step was reported in the returned step list. The job outcome alone does not identify a failed command.')
        annotations=job['annotations']
        lines.append('Annotations: '+annotations['state'])
        if annotations.get('source_url'): lines.append('Annotation source: '+annotations['source_url'])
        if annotations.get('error'): lines.append(annotations['error'])
        ordered=sorted(annotations['annotations'],key=lambda a:{'failure':0,'warning':1,'notice':2}[a['level']])
        for annotation in ordered[:MAX_DISPLAY_ANNOTATIONS]:
            lines.append(f"Provider {annotation['level']} at {annotation['path']}:{annotation['start_line']} (unverified text):")
            lines.extend('  | '+line for line in annotation['message'].splitlines())
            if annotation['text_truncated']: lines.append('  | [Text truncated]')
        if len(ordered)>MAX_DISPLAY_ANNOTATIONS: lines.append('Additional collected annotations omitted from display; only the first 10 are shown.')
        if annotations['state']=='reported' and not ordered: lines.append('No annotations were returned. This does not explain why the job failed.')
    lines.append('Warnings, notices and suggested links are not automatically causes or instructions to act. No logs or linked pages were opened.')
    return lines
