"""Serve the local runbook workspace. Start with python runbook_ui.py."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlsplit

from errors import AgentError
from runbook_search import answer, search

ROOT = Path(__file__).resolve().parent
ASSETS = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
    '/style.css': ('style.css', 'text/css; charset=utf-8'),
}
MODELS = ('qwen2.5:3b', 'qwen2.5:7b')


def query_runbooks(payload):
    if not isinstance(payload, dict):
        raise ValueError('Send a question and search mode.')
    question = payload.get('question')
    mode = payload.get('mode', 'keyword')
    compare = payload.get('compare', False)
    model = payload.get('model', MODELS[0])
    if not isinstance(question, str) or not question.strip() or len(question) > 2000:
        raise ValueError('Enter a question of up to 2,000 characters.')
    if mode not in ('keyword', 'semantic') or type(compare) is not bool or model not in MODELS:
        raise ValueError('Choose a supported search mode and local model.')
    question = question.strip()
    if mode == 'semantic':
        from semantic_runbook_search import search_semantic
        hits = search_semantic(question)
    else:
        hits = search(question)
    excerpts = answer(question, hits)
    result = {
        'question': question, 'mode': mode,
        'passages': [{'citation': citation, 'text': passage} for _, citation, passage in hits],
        'rule_answer': [{'citation': citation, 'text': text} for citation, text in excerpts],
        'model_answer': None, 'model_error': None,
    }
    if compare:
        if not hits:
            result['model_answer'] = 'The guides do not provide a supported answer to this question.'
        else:
            from runbook_model_answer import ask_ollama, model_answer
            try:
                result['model_answer'] = model_answer(
                    question, hits, lambda messages: ask_ollama(model, messages))
            except AgentError as exc:
                result['model_error'] = str(exc)
    return result


class Handler(BaseHTTPRequestHandler):
    def send(self, status, content, mime='application/json; charset=utf-8'):
        body = content if isinstance(content, bytes) else json.dumps(content).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy',
                         "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        route = urlsplit(self.path).path
        if route == '/health':
            self.send(200, {'status': 'ok'})
        elif route in ASSETS:
            filename, mime = ASSETS[route]
            self.send(200, (ROOT / 'web/runbooks' / filename).read_bytes(), mime)
        else:
            self.send(404, {'error': 'Page not found.'})

    def do_POST(self):
        host = self.headers.get('Host', '')
        if host not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
            self.send(403, {'error': 'Use the local workspace address.'})
            return
        origin = self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}',
                                     f'http://localhost:{self.server.server_port}'):
            self.send(403, {'error': 'Requests must come from this workspace.'})
            return
        if urlsplit(self.path).path != '/api/query':
            self.send(404, {'error': 'Endpoint not found.'})
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 16000:
                raise ValueError('Request is empty or too large.')
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('Send JSON with your question.')
            payload = json.loads(self.rfile.read(size))
            result = query_runbooks(payload)
            self.send(200, result)
        except (ValueError, TypeError, UnicodeError) as exc:
            self.send(400, {'error': str(exc)})
        except AgentError as exc:
            self.send(503, {'error': str(exc)})
        except Exception:
            self.send(500, {'error': 'The local request failed. Try again.'})

    def log_message(self, format, *args):
        # Keep user questions and model text out of the server log.
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error('--port must be between 0 and 65535')
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    except OSError:
        parser.error('Could not open the local port. Try --port 8766.')
    with server:
        print(f'Runbook workspace ready at http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
