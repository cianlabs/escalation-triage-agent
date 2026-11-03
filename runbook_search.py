"""Read-only lexical search over the runbook assistant's five guides."""
import argparse
from collections import Counter
import math
from pathlib import Path
import re
import sys

from errors import AgentError

GUIDES = (
    'customer_outage.txt',
    'db_connection_pool.txt',
    'redis_memory.txt',
    'rollback_bad_deploy.txt',
    'slow_dashboard.txt',
)
RUNBOOKS = Path(__file__).resolve().parent / 'runbooks'
STOP_WORDS = set('a an and are at can do for how i in is it of on or our should the there to what when which who with'.split())


def terms(text):
    return set(re.findall(r'[a-z0-9]+', text.lower())) - STOP_WORDS


def search(question):
    query = terms(question)
    passages = []
    for name in GUIDES:
        lines = (RUNBOOKS / name).read_text(encoding='utf-8').splitlines()
        passage = '\n'.join(lines)
        passages.append((f'runbooks/{name}:1-{len(lines)}', passage, terms(passage)))

    frequencies = Counter(word for _, _, words in passages for word in words)
    weights = {word: math.log(1 + len(passages) / count)
               for word, count in frequencies.items() if word in query}
    hits = [(sum(weights[word] for word in sorted(query & words)), citation, passage)
            for citation, passage, words in passages]
    ranked = sorted(hits, key=lambda hit: (-hit[0], hit[1]))
    # Keep alternatives with at least half the lexical support of the best hit.
    cutoff = ranked[0][0] / 2
    return [hit for hit in ranked if hit[0] > 0 and hit[0] >= cutoff][:3]



def answer(question, hits):
    """Extract a cited check or approval requirement from a matching guide."""
    query = terms(question)
    if 'logs' in query and query & {'path', 'stored', 'disk', 'directory', 'location'}:
        return []
    if re.search(r'\bsign(?:s|ed|ing)?[ -]+off\b', question, re.IGNORECASE):
        query.add('approval')
    if not hits or query & {'cancel', 'rotate'}:
        return []
    best_score = hits[0][0]
    candidates = []
    for score, citation, passage in hits:
        if score != best_score:
            break
        path, _ = citation.rsplit(':', 1)
        lines = passage.splitlines()
        action = approval_answer(query, path, lines)
        if action:
            candidates.append(action)
            continue
        if not query & {'check', 'checks', 'inspect', 'review', 'logs'}:
            continue
        subject = terms(lines[0]) & query
        checks = [(number, line) for number, line in enumerate(lines[1:], 2)
                  if re.match(r'(?:Check|Inspect|Review)\b|If [^,]+, (?:check|inspect|review)\b', line)]
        if 'logs' in query:
            checks = [(number, line.split(' and clear ', 1)[0])
                      for number, line in checks if 'logs' in terms(line)]
        if subject and checks:
            candidates.append([(f'{path}:{number}', line) for number, line in checks])
    return candidates[0] if len(candidates) == 1 else []


def approval_answer(query, path, lines):
    """Require both the operation and its subject before quoting approval guidance."""
    restart = query & {'restart', 'bounce', 'reboot'}
    if path.endswith('/redis_memory.txt') and 'redis' in query and (restart or {'cycle', 'nodes'} <= query):
        pattern = r"^Restart Redis .*only after human approval"
    elif path.endswith('/db_connection_pool.txt') and 'pooler' in query and restart:
        pattern = r"^Restart connection pooler only after human approval"
    elif (path.endswith('/rollback_bad_deploy.txt') and query & {'500', '500s'}
          and query & {'release', 'deploy', 'deployment'} and restart):
        pattern = r"^Roll back only after a human approves"
    elif path.endswith('/customer_outage.txt') and 'service' in query and query & {'down', 'outage'} and 'approval' in query:
        pattern = r"^Page oncall only after a human approves"
    elif path.endswith('/customer_outage.txt') and query & {'customer', 'customers'} and query & {'bring', 'page', 'paged', 'call'}:
        pattern = r"^Page oncall (?:when|only after)"
    else:
        return []
    return [(f'{path}:{number}', line) for number, line in enumerate(lines, 1)
            if re.match(pattern, line)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--model-answer', action='store_true', help='Ask Gemini to answer from the retrieved guides.')
    mode.add_argument('--answer', action='store_true', help='Quote a supported check or approval requirement.')
    parser.add_argument('--ollama-model', help='Use this installed local Ollama model with --model-answer.')
    parser.add_argument('question')
    args = parser.parse_args()
    if args.ollama_model is not None and not args.model_answer:
        parser.error('--ollama-model requires --model-answer')
    hits = search(args.question)
    if args.model_answer:
        from agent import ask_model, make_gemini_summary_client
        from runbook_model_answer import model_answer

        try:
            if not hits:
                print('The guides do not provide a supported answer to this question.')
                return 0
            if args.ollama_model:
                from runbook_model_answer import ask_ollama

                print(model_answer(args.question, hits, lambda messages: ask_ollama(args.ollama_model, messages)))
                return 0
            with make_gemini_summary_client() as client:
                print(model_answer(args.question, hits, lambda messages: ask_model(
                    client, messages, None, comparison_summary=True,
                    model='gemini-3.1-flash-lite', provider='gemini',
                )))
        except AgentError as exc:
            print('Rule-based fallback')
            excerpts = answer(args.question, hits)
            if not excerpts:
                print('The guides do not provide a supported answer to this question.')
            for citation, line in excerpts:
                print(f'{line} [{citation}]')
            print(exc, file=sys.stderr)
            return 1
        return 0
    if args.answer:
        excerpts = answer(args.question, hits)
        if not excerpts:
            print('The guides do not provide a supported answer to this question.')
        for citation, line in excerpts:
            print(f'{line} [{citation}]')
        return
    if not hits:
        print('The guides do not contain a matching passage.')
        return
    for _, citation, passage in hits:
        print(f'{citation}\n{passage}\n')


if __name__ == '__main__':
    sys.exit(main())
