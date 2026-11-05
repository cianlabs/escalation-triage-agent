"""Capture local answers or report on a saved run without calling a model."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import httpx

from runbook_evaluation import load_reviews, load_run, question_hash, report, review_template

ROOT = Path(__file__).resolve().parent


def capture_metadata(questions, model):
    source = (ROOT / 'runbook_model_answer.py').read_text()
    prompt = None
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Dict):
            values = {key.value: value for key, value in zip(node.keys, node.values)
                      if isinstance(key, ast.Constant)}
            if isinstance(values.get('role'), ast.Constant) and values['role'].value == 'system':
                prompt = ast.literal_eval(values['content'])
                break
    corpus = {path.name: path.read_text() for path in sorted((ROOT / 'fixtures/semantic/guides').glob('*.txt'))}
    digests = {}
    try:
        with httpx.Client(trust_env=False, timeout=2) as client:
            response = client.get('http://127.0.0.1:11434/api/tags')
            response.raise_for_status()
            digests = {row['name']: row['digest'] for row in response.json()['models']}
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        pass
    return {
        'model_digest': digests.get(model if ':' in model else model + ':latest', 'unknown'),
        'embedding_digest': digests.get('embeddinggemma:latest', 'unknown'),
        'created_at': datetime.now(timezone.utc).isoformat(),
        'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest() if prompt else 'unknown',
        'answer_code_sha256': hashlib.sha256(source.encode()).hexdigest(),
        'corpus_sha256': hashlib.sha256(json.dumps(corpus, sort_keys=True).encode()).hexdigest(),
        'questions_sha256': question_hash(questions),
        'embedding_model': 'embeddinggemma', 'min_similarity': 0.3,
    }


def save_run(path, metadata, results):
    # Replace the checkpoint only when all bytes have been written.
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False, encoding='utf-8') as stream:
        temporary = Path(stream.name)
        try:
            json.dump({'version': 1, 'metadata': metadata, 'results': results}, stream, indent=2)
            stream.write('\n')
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--model')
    mode.add_argument('--replay', type=Path)
    parser.add_argument('--questions', type=Path, default=ROOT / 'fixtures/semantic/holdout.json')
    parser.add_argument('--output', type=Path, help='Saved run for capture, or Markdown report for replay.')
    parser.add_argument('--reviews', type=Path)
    parser.add_argument('--review-template', type=Path)
    args = parser.parse_args(argv)
    if args.model and (not args.output or args.reviews or args.review_template):
        parser.error('Capture requires --output. Use --replay for review options.')
    try:
        questions = json.loads(args.questions.read_text())
        if (not isinstance(questions, list) or not questions
                or any(not isinstance(row, dict) or not isinstance(row.get('id'), str)
                       or not isinstance(row.get('question'), str) or 'expected' not in row for row in questions)
                or len({row['id'] for row in questions}) != len(questions)):
            raise ValueError('Invalid or duplicate questions.')
        if args.replay:
            metadata, results = load_run(args.replay, questions)
            if metadata.get('questions_sha256') not in (None, question_hash(questions)):
                raise ValueError('Saved run was captured with a different question set.')
            protected = {path.resolve() for path in (args.replay, args.questions, args.reviews) if path}
            if ((args.output and args.output.resolve() in protected)
                    or (args.review_template and args.review_template.resolve() in protected)
                    or (args.output and args.review_template
                        and args.output.resolve() == args.review_template.resolve())):
                raise ValueError('Report and review outputs must be separate from input files and each other.')
            reviews = load_reviews(args.reviews, questions, args.replay)
            rendered = report(questions, metadata, results, reviews)
            if args.review_template:
                with args.review_template.open('x', encoding='utf-8') as stream:
                    json.dump(review_template(questions, args.replay), stream, indent=2)
                    stream.write('\n')
            if args.output:
                args.output.write_text(rendered, encoding='utf-8')
            else:
                print(rendered)
            return 0

        if args.output.resolve() == args.questions.resolve():
            raise ValueError('Capture output cannot overwrite the question set.')
        metadata = capture_metadata(questions, args.model)
        results = []
        for question in questions:
            started = time.perf_counter()
            try:
                response = subprocess.run([
                    sys.executable, str(ROOT / 'runbook_search.py'), '--semantic',
                    '--model-answer', '--ollama-model', args.model, question['question'],
                ], capture_output=True, text=True, timeout=180, cwd=ROOT)
                result = dict(id=question['id'], model=args.model, exit_code=response.returncode,
                              output=response.stdout, error=response.stderr)
            except subprocess.TimeoutExpired:
                result = dict(id=question['id'], model=args.model, exit_code=None,
                              output='', error='Evaluation timed out after 180 seconds.')
            result['seconds'] = round(time.perf_counter() - started, 3)
            results.append(result)
            save_run(args.output, metadata, results)
            print(f"{result['id']} {result['seconds']}s exit={result['exit_code']}", flush=True)
        print(report(questions, metadata, {row['id']: row for row in results}, {}))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f'Evaluation failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
