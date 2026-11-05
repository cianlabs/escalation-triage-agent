"""Native Gemini generation using the terminal's normal HTTP configuration."""
import re

import httpx


class GeminiHTTPError(Exception):
    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__(f'Gemini HTTP {status_code}')


class GeminiClient:
    def __init__(self, key, *, transport=None):
        self.client = httpx.Client(
            base_url='https://generativelanguage.googleapis.com/v1beta/',
            headers={'x-goog-api-key': key}, timeout=60, transport=transport,
        )

    def __enter__(self):
        self.client.__enter__()
        return self

    def __exit__(self, *args):
        return self.client.__exit__(*args)

    def generate(self, *, model, messages):
        if not re.fullmatch(r'[a-zA-Z0-9_.-]+', model):
            raise ValueError('Invalid Gemini model ID')
        instructions = []
        contents = []
        for message in messages:
            if message['role'] == 'system':
                instructions.append({'text': message['content']})
            else:
                role = 'model' if message['role'] == 'assistant' else 'user'
                contents.append({'role': role, 'parts': [{'text': message['content']}]})
        response = self.client.post(f'models/{model}:generateContent', json={
            'systemInstruction': {'parts': instructions},
            'contents': contents,
            'generationConfig': {'responseMimeType': 'application/json'},
        })
        if response.status_code != 200:
            # Raw provider errors can contain request data. Retain only the status.
            raise GeminiHTTPError(response.status_code)
        data = response.json()
        candidates = data.get('candidates', [])
        if not candidates or candidates[0].get('finishReason') != 'STOP':
            raise ValueError('Gemini returned no completed answer')
        text = ''.join(part.get('text', '') for part in candidates[0]['content']['parts']
                       if not part.get('thought'))
        if not text.strip():
            raise ValueError('Gemini returned no answer text')
        return text
