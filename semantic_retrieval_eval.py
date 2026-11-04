"""Compare lexical and local embedding retrieval on a fixed practice corpus."""
from collections import Counter
import json
import math
from pathlib import Path

import httpx

from runbook_search import terms

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'semantic'


def cosine(first, second):
    denominator = math.hypot(*first) * math.hypot(*second)
    if len(first) != len(second) or not denominator:
        raise ValueError('Invalid embedding dimensions or zero vector.')
    return sum(a * b for a, b in zip(first, second)) / denominator


def evaluate():
    guides = json.loads((FIXTURES / 'guides.json').read_text())
    questions = json.loads((FIXTURES / 'questions.json').read_text())
    names = sorted(guides)
    words = {name: terms(guides[name]) for name in names}
    frequencies = Counter(word for tokens in words.values() for word in tokens)
    # EmbeddingGemma retrieval prefixes follow the model's documented format.
    inputs = ['title: ' + name + ' | text: ' + guides[name] for name in names]
    inputs += ['task: search result | query: ' + row['question'] for row in questions]
    with httpx.Client(trust_env=False, timeout=120) as client:
        response = client.post('http://127.0.0.1:11434/api/embed', json={
            'model': 'embeddinggemma', 'input': inputs, 'truncate': False,
        })
        response.raise_for_status()
        vectors = response.json()['embeddings']
    if len(vectors) != len(inputs):
        raise ValueError('Incomplete embeddings.')
    totals = dict(keyword=[0, 0], embeddings=[0, 0])
    print('| Case | Keyword top three | Embedding top three |')
    print('| --- | --- | --- |')
    for index, row in enumerate(questions):
        query = terms(row['question'])
        lexical = [(sum(math.log(1 + len(names) / frequencies[word])
                        for word in sorted(query & words[name])), name) for name in names]
        lexical.sort(key=lambda item: (-item[0], item[1]))
        keyword = [name for score, name in lexical if score > 0 and score >= lexical[0][0] / 2][:3]
        semantic = sorted(zip(names, vectors[:len(names)]),
                          key=lambda item: (-cosine(item[1], vectors[len(names) + index]), item[0]))
        embeddings = [name for name, _ in semantic[:3]]
        for method, results in (('keyword', keyword), ('embeddings', embeddings)):
            totals[method][0] += row['expected'] in results
            totals[method][1] += sum(name != row['expected'] for name in results)
        print(f"| {row['id']} | {', '.join(keyword) or 'None'} | {', '.join(embeddings)} |")
    print()
    for method, (correct, unrelated) in totals.items():
        print(f'{method}: top-three recall {correct}/{len(questions)}; unrelated results {unrelated}')
    print('One expected guide per question. Other results count as unrelated under this rubric.')


if __name__ == '__main__':
    evaluate()
