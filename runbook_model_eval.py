"""Capture one local model answer per semantic holdout question, with timing."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--questions', type=Path, default=ROOT / 'fixtures/semantic/holdout.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    questions = json.loads(args.questions.read_text())
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
        args.output.write_text(json.dumps(results, indent=2) + '\n')
        print(f"{result['id']} {result['seconds']}s exit={result['exit_code']}\n"
              f"{result['output']}{result['error']}", flush=True)


if __name__ == '__main__':
    main()
