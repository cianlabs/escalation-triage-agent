"""Capture answers or report on a saved run without scoring them."""
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
from runbook_model_answer import (
    XAI_MAX_ATTEMPTS, XAI_MAX_OUTPUT_TOKENS, XAI_REASONING_EFFORT,
    XAI_RESPONSES_API, XAI_RUNBOOK_MODEL, XAI_TIMEOUT_SECONDS, model_id_error,
)

ROOT = Path(__file__).resolve().parent
FROZEN_COMPARISON = 'fixtures/semantic/holdout.json'


def dataset_identity(path, questions):
    if path is None:
        return 'unrecorded', 'unrecorded'
    try:
        relative = str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        relative = Path(path).name
    ids = [row.get('id') for row in questions]
    label = 'semantic-holdout-t01-t12' if relative == FROZEN_COMPARISON and ids == [f'T{number:02d}' for number in range(1, 13)] else 'custom'
    return relative, label


def capture_metadata(questions, model, provider='ollama', questions_path=None):
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
    dataset, dataset_id = dataset_identity(questions_path, questions)
    digest = question_hash(questions)
    attempts = XAI_MAX_ATTEMPTS if provider == 'xai' else 1
    return {
        'provider': provider,
        'model': model,
        'model_digest': digests.get(model if ':' in model else model + ':latest', 'unknown') if provider == 'ollama' else 'remote-model-unverified',
        'embedding_digest': digests.get('embeddinggemma:latest', 'unknown'),
        'created_at': datetime.now(timezone.utc).isoformat(),
        'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest() if prompt else 'unknown',
        'answer_code_sha256': hashlib.sha256(source.encode()).hexdigest(),
        'corpus_sha256': hashlib.sha256(json.dumps(corpus, sort_keys=True).encode()).hexdigest(),
        'questions_sha256': digest,
        'dataset': dataset,
        'dataset_id': dataset_id,
        'dataset_sha256': digest,
        'embedding_model': 'embeddinggemma', 'min_similarity': 0.3,
        'api': XAI_RESPONSES_API if provider == 'xai' else 'http://127.0.0.1:11434/api/chat',
        'max_output_tokens': XAI_MAX_OUTPUT_TOKENS if provider == 'xai' else None,
        'timeout_seconds': XAI_TIMEOUT_SECONDS if provider == 'xai' else 90,
        'max_attempts': attempts,
        'max_model_calls': len(questions) * attempts,
        'reasoning_effort': XAI_REASONING_EFFORT if provider == 'xai' else None,
        'search': 'off' if provider == 'xai' else 'not-applicable',
        'temperature': 0 if provider == 'xai' else None,
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
    mode.add_argument('--model', help='Capture with this local Ollama model.')
    mode.add_argument('--xai-model', help=f'Capture with this xAI model. The documented default is {XAI_RUNBOOK_MODEL}.')
    mode.add_argument('--replay', type=Path)
    parser.add_argument('--questions', type=Path, default=ROOT / FROZEN_COMPARISON)
    parser.add_argument('--output', type=Path, help='Saved run for capture, or Markdown report for replay.')
    parser.add_argument('--reviews', type=Path)
    parser.add_argument('--review-template', type=Path)
    args = parser.parse_args(argv)
    if (args.model or args.xai_model) and (not args.output or args.reviews or args.review_template):
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
        provider = 'xai' if args.xai_model else 'ollama'
        model = args.xai_model or args.model
        if provider == 'xai':
            problem = model_id_error(model)
            if problem:
                raise ValueError(problem)
        metadata = capture_metadata(questions, model, provider=provider, questions_path=args.questions)
        flag = '--xai-model' if provider == 'xai' else '--ollama-model'
        limit = 210 if provider == 'xai' else 180
        results = []
        for question in questions:
            started = time.perf_counter()
            try:
                response = subprocess.run([
                    sys.executable, str(ROOT / 'runbook_search.py'), '--semantic',
                    '--model-answer', flag, model, question['question'],
                ], capture_output=True, text=True, timeout=limit, cwd=ROOT)
                result = dict(id=question['id'], provider=provider, model=model, exit_code=response.returncode,
                              output=response.stdout, error=response.stderr)
            except subprocess.TimeoutExpired:
                result = dict(id=question['id'], provider=provider, model=model, exit_code=None,
                              output='', error=f'Evaluation timed out after {limit} seconds.')
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
