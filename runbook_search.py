"""Read-only lexical search over the runbook assistant's five guides."""
import argparse
from pathlib import Path
import re

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
    hits = []
    for name in GUIDES:
        lines = (RUNBOOKS / name).read_text(encoding='utf-8').splitlines()
        passage = '\n'.join(lines)
        score = len(query & terms(passage))
        if score:
            hits.append((score, f'runbooks/{name}:1-{len(lines)}', passage))
    return sorted(hits, key=lambda hit: (-hit[0], hit[1]))[:3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('question')
    args = parser.parse_args()
    hits = search(args.question)
    if not hits:
        print('The guides do not contain a matching passage.')
        return
    for _, citation, passage in hits:
        print(f'{citation}\n{passage}\n')


if __name__ == '__main__':
    main()
