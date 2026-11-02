"""Conservative matching between a user's problem and reported GitHub components."""
import re

COMPONENTS = {
    'actions': ('br0l2tvcx85d', 'Actions'),
    'git': ('8l4ygp009s5s', 'Git Operations'),
    'api': ('brv1bkgrwx7q', 'API Requests'),
    'pages': ('vg70hn9s2tyj', 'Pages'),
    'packages': ('st3j38cctv9l', 'Packages'),
    'codespaces': ('h2ftsgbw7kmk', 'Codespaces'),
    'copilot': ('pjmpxvq2cmr2', 'Copilot'),
    'issues': ('kr09ddfgbfsf', 'Issues'),
    'pull-requests': ('hhtssxt0f5v2', 'Pull Requests'),
    'webhooks': ('4230lsnqdsld', 'Webhooks'),
}
PATTERNS = {
    'actions': r'\b(?:actions|workflows?|runners?)\b',
    'git': r'\bgit (?:push|pull|clone|fetch)\b',
    'api': r'\bapi\b', 'pages': r'\bpages\b',
    'packages': r'\b(?:packages|ghcr(?:\.io)?)\b',
    'codespaces': r'\bcodespaces?\b', 'copilot': r'\bcopilot\b',
    'issues': r'\bissues\b', 'pull-requests': r'\bpull requests?\b',
    'webhooks': r'\bwebhooks?\b',
}
HISTORICAL = re.compile(r'\b(?:yesterday|last (?:night|week|month)|\d+ (?:hours?|days?|weeks?) ago|\d{4}-\d{2}-\d{2})\b', re.I)


def select_component(problem, explicit=None):
    if explicit:
        return explicit
    # A generic API, website or workflow is not necessarily hosted by GitHub.
    if not re.search(r'\bgithub(?:\.com)?\b|\bghcr\.io\b|\bcodespaces?\b', problem, re.I):
        return None
    matches = [key for key, pattern in PATTERNS.items() if re.search(pattern, problem, re.I)]
    return matches[0] if len(matches) == 1 else None


def assess_relevance(problem, components, explicit=None):
    selected = select_component(problem, explicit)
    result = dict(component=selected, confirmed_root_cause=None)
    if HISTORICAL.search(problem):
        return dict(result, assessment='time_not_matched', message='This is a current status snapshot, so it cannot establish what was happening at the earlier incident time.',
                    next_check='Compare the exact incident time with historical provider updates and your own logs.')
    if selected is None:
        return dict(result, assessment='needs_component', message='I cannot confidently tell which GitHub service this problem involves. Overall GitHub status alone is not enough.',
                    next_check='Specify the affected GitHub service with --component and collect the exact failed operation and error.')
    reported = next((row for row in components if row['component_key'] == selected), None)
    if reported is None or reported['component_status'] == 'unknown':
        return dict(result, assessment='unknown', message=f"The reported status for {COMPONENTS[selected][1]} is unavailable or unrecognized. Do not assume it is healthy.",
                    next_check='Retry the status check and compare a working and failing request without exposing credentials.')
    name, status = reported['component_name'], reported['component_status']
    if status == 'operational':
        return dict(result, assessment='no_reported_issue', component_status=status,
                    message=f"GitHub currently reports {name} as operational. That report does not explain this problem and does not rule out an unreported, account-specific or local failure.",
                    next_check='Collect the exact error, affected account or repository, and incident time; compare a working and failing operation.')
    return dict(result, assessment='possibly_related', component_status=status,
                message=f"GitHub reports {name} as {status}. Because the problem involves this service, the reported impact could be related. It does not prove the cause of this particular failure.",
                next_check='Compare the provider update with the exact failure time, error and scope before treating it as related.')
