"""Conservative investigation hypotheses from mechanism-specific observations.

Rules identify diagnostic signals, not verified causes. No model, network,
commands, action proposals or persistent state are used. Impact words alone do
not select a cause. Unknown and conflicting evidence stay explicitly uncertain.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path

from errors import AgentError


@dataclass(frozen=True)
class Mechanism:
    family: str
    title: str
    patterns: tuple[str, ...]
    explanation: str
    next_check: str


MECHANISMS = (
    Mechanism('memory_exhaustion', 'Memory exhaustion',
              (r'\boom(?:\s+kill(?:s|ed|er)?)?\b', r'\boomkilled\b', r'\bout[- ]of[- ]memory\b', r'\bmemory (?:is )?exhausted\b'),
              'Memory exhaustion can terminate a process. This does not explain why memory ran out.',
              'Check the kernel event, memory limit and usage for the same process and incident time.'),
    Mechanism('network_routing_failure', 'Network routing failure',
              (r'\bmissing (?:a )?route\b', r'\broutes? (?:was |were |is |are )?(?:removed|deleted)\b', r'\b(?:removed|deleted)\b.{0,20}\broutes?\b', r'\bno route to host\b'),
              'A missing or removed route can prevent communication. The reason it changed is still unknown.',
              'Compare the affected route table with a healthy host and check when the route changed.'),
    Mechanism('authentication_failure', 'Authentication failure',
              (r'\b(?:access |authentication )?token (?:has |is )?expired\b', r'\b(?:invalid|expired|revoked) (?:access )?token\b',
               r'\btoken validation (?:failed|rejected)\b', r'\binvalid credentials\b'),
              'Rejected credentials can block access without implying that the service itself has failed.',
              'Check token expiry, issuer, audience and validation results without collecting secret values.'),
    Mechanism('storage_access_failure', 'Storage access failure',
              (r'\baccessdenied\b.{0,70}\b(?:object|bucket|file)\b',
               r'\bpermission denied\b.{0,70}\b(?:object|bucket|file)\b',
               r'\b(?:object|bucket|file)\b.{0,70}\bpermission denied\b'),
              'A storage permission rejection can block reads or writes. It does not establish a storage outage.',
              'Check the requested resource and effective access policy using a read-only permission check.'),
    Mechanism('storage_io_failure', 'Storage I/O failure',
              (r'\b(?:disk|device|filesystem)\b.{0,50}\b(?:eio|i/o error|input/output error)\b',
               r'\bno space left on device\b'),
              'An I/O or full-device error can stop file operations. The underlying device condition needs checking.',
              'Check device errors, mount health and available space for the affected operation.'),
    Mechanism('database_connection_limit', 'Database connection limit',
              (r'\btoo many connections\b', r'\bsqlstate\s*53300\b', r'\bconnection pool (?:is )?exhausted\b'),
              'A connection limit can reject database requests. It does not establish why connections accumulated.',
              'Compare active and waiting connections with configured limits and recent request volume.'),
    Mechanism('deployment_regression', 'Deployment regression',
              (r'\b(?:error rate|errors?|failures?)\b.{0,50}\b(?:increased|jumped|began|started)\b.{0,30}\bafter\b.{0,30}\bdeploy(?:ment)?\b',
               r'\brollback\b.{0,40}\b(?:restored|resolved|recovered)\b'),
              'Failure timing or recovery after rollback suggests a change-related regression. Timing alone is not proof.',
              'Compare the changed and prior versions, check other simultaneous changes and verify the recovery timeline.'),
)

# Split contrastive clauses so a negative statement does not erase a later
# positive clue. This is deliberately limited language handling, not an NLP model.
CLAUSES = re.compile(r'[.;!?\n]+|\b(?:but|however|although)\b', re.I)
UNCERTAIN = re.compile(r'\b(?:maybe|perhaps|possibly|suspect(?:ed)?|hypothetical|might|could)\b', re.I)
INSTRUCTION = re.compile(r'\b(?:ignore (?:all |the )?(?:previous|prior) instructions|you must|pretend|assume|please|should|must)\b', re.I)
NEGATIVE_PREFIX = re.compile(r'\b(?:no|not|without|never)\b(?:\W+\w+){0,5}\W*$', re.I)
NEGATIVE_SUFFIX = re.compile(r'^.{0,25}\b(?:not (?:observed|seen|present|recorded)|ruled out|absent)\b', re.I)


def validate_evidence(evidence):
    if not isinstance(evidence, list):
        raise AgentError('BAD_TOOL_ARGS', 'evidence must be a list of observation objects.')
    cleaned, seen = [], set()
    for row in evidence:
        if not isinstance(row, dict) or any(not isinstance(row.get(k), str) or not row[k].strip() for k in ('id', 'source', 'observation')):
            raise AgentError('EVIDENCE_INVALID', 'each observation needs a nonempty id, source and observation.')
        if row['id'] in seen:
            raise AgentError('EVIDENCE_INVALID', 'evidence ids must be unique.')
        seen.add(row['id'])
        cleaned.append({k: row[k] for k in ('id', 'source', 'observation')})
    return cleaned


def signals(observation, mechanism):
    """Return support and counterevidence without treating hedges as observations."""
    support, counter = False, False
    for clause in CLAUSES.split(observation):
        if UNCERTAIN.search(clause) or INSTRUCTION.search(clause):
            continue
        for pattern in mechanism.patterns:
            for match in re.finditer(pattern, clause, re.I):
                prefix = clause[:match.start()]
                # 'not only' is not a denial of the following signal.
                prefix = re.sub(r'\bnot only\b', '', prefix, flags=re.I)
                # 'no route to host' is itself a positive routing error signal.
                negative = bool(NEGATIVE_PREFIX.search(prefix) or NEGATIVE_SUFFIX.search(clause[match.end():]))
                if negative:
                    counter = True
                else:
                    support = True
    return support, counter


def rank_evidence(evidence):
    rows = validate_evidence(evidence)
    hypotheses, counters = [], []
    for mechanism in MECHANISMS:
        supporting, contradicting = [], []
        for row in rows:
            positive, negative = signals(row['observation'], mechanism)
            if positive:
                supporting.append(row['id'])
            if negative:
                contradicting.append(row['id'])
        if contradicting:
            counters.append(dict(family=mechanism.family, evidence_ids=contradicting))
        if not supporting:
            continue
        hypotheses.append(dict(
            title=mechanism.title, family=mechanism.family,
            rationale=mechanism.explanation,
            supporting_evidence_ids=supporting,
            contradicting_evidence_ids=contradicting,
            missing_evidence=['Independent verification of the mechanism and its incident timing.'],
            next_diagnostic_step=mechanism.next_check,
            status='unverified',
        ))
    # Evidence count is a reproducible order, not a probability. Contradicted
    # candidates sort behind uncontested ones and still force uncertainty.
    hypotheses.sort(key=lambda h: (bool(h['contradicting_evidence_ids']), -len(h['supporting_evidence_ids']), h['family']))
    if not hypotheses:
        assessment = 'insufficient_evidence'
        message = 'I do not have enough evidence to name a likely cause. A symptom or error page alone is not enough.'
    elif any(h['contradicting_evidence_ids'] for h in hypotheses):
        assessment = 'conflicting_evidence'
        message = 'The clues disagree. Keep the possible causes unverified and reconcile the evidence before choosing one.'
    elif len(hypotheses) > 1:
        assessment = 'competing_hypotheses'
        message = 'Several mechanisms have supporting clues. Their order is not proof that one caused the incident.'
    else:
        assessment = 'supported_hypothesis'
        message = 'One mechanism has a specific supporting clue. It remains a hypothesis, not a confirmed root cause.'
    checks = [h['next_diagnostic_step'] for h in hypotheses] or [
        'Collect the exact error, affected operation and incident time, then compare a working and failing request.'
    ]
    return dict(assessment=assessment, message=message, evidence=rows, hypotheses=hypotheses,
                counterevidence=counters, next_checks=checks,
                confirmed_root_cause=None, action_mode='simulation_only',
                action_proposed=False, stop_reason='INVESTIGATION_REQUIRED')


def investigate(data):
    if not isinstance(data, dict) or not isinstance(data.get('symptom'), str) or not data['symptom'].strip():
        raise AgentError('BAD_TOOL_ARGS', 'investigation requires an object with a nonempty symptom and an evidence list.')
    if 'evidence' not in data:
        raise AgentError('BAD_TOOL_ARGS', 'investigation requires an evidence list; use an empty list if no clues are available.')
    result = rank_evidence(data['evidence'])
    return dict(symptom=data['symptom'], **result)


def render_investigation(result):
    lines = ['Investigation only. No action will run.', f"Reported problem: {result['symptom']}", '', result['message']]
    observations = {row['id']: row['observation'] for row in result['evidence']}
    if result['hypotheses']:
        for index, hypothesis in enumerate(result['hypotheses'], 1):
            lines += ['', f"{index}. {hypothesis['title']} (unverified)",
                      '   Supporting clues: ' + ', '.join(hypothesis['supporting_evidence_ids']),
                      '   Why: ' + hypothesis['rationale']]
            lines.extend('   Clue '+eid+': '+observations[eid] for eid in hypothesis['supporting_evidence_ids'])
            if hypothesis['contradicting_evidence_ids']:
                lines.append('   Conflicting clues: ' + ', '.join(hypothesis['contradicting_evidence_ids']))
    lines += ['', 'Next checks:']
    lines.extend('- '+check for check in result['next_checks'])
    lines += ['', 'Confirmed root cause: none', 'Stop reason: INVESTIGATION_REQUIRED']
    return '\n'.join(lines)


def investigate_file(path):
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise AgentError('BAD_TOOL_ARGS', f'Could not read investigation JSON ({type(exc).__name__}).') from None
    return investigate(data)
