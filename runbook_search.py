"""Read-only lexical search over the runbook assistant's five guides."""
import argparse
from collections import Counter
import math
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
