const form = document.getElementById('query-form');
const question = document.getElementById('question');
const mode = document.getElementById('mode');
const status = document.getElementById('status');
const error = document.getElementById('error');
const results = document.getElementById('results');
const passages = document.getElementById('passages');
const rule = document.getElementById('rule-answer');
const modelOutput = document.getElementById('model-answer');
const compare = document.getElementById('compare');
let lastQuery = null;
let busy = false;
const sourceLines = new Map();

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function citationButton(citation) {
  const button = element('button', 'citation', citation);
  button.type = 'button';
  button.addEventListener('click', () => {
    const target = sourceLines.get(citation);
    if (!target) return;
    document.querySelectorAll('.focused').forEach(node => node.classList.remove('focused'));
    target.classList.add('focused');
    target.scrollIntoView({behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'center'});
    target.focus({preventScroll: true});
  });
  return button;
}

function renderSources(data) {
  passages.replaceChildren();
  sourceLines.clear();
  document.getElementById('passage-count').textContent = data.passages.length + ' found';
  document.getElementById('source-note').textContent = data.mode === 'semantic'
    ? 'Practice corpus · 15 guides · similarity cutoff 0.3'
    : 'Local library · 5 guides · ranked by shared terms';
  if (!data.passages.length) {
    passages.append(element('p', 'quiet', 'No passages matched this question. Try describing the service and symptom.'));
  }
  data.passages.forEach((passage, index) => {
    const lines = passage.text.split('\n');
    const path = passage.citation.slice(0, passage.citation.lastIndexOf(':'));
    const card = element('article', 'source-card');
    const heading = element('div', 'source-title');
    heading.append(element('span', 'rank', String(index + 1).padStart(2, '0')));
    heading.append(element('h3', '', lines[0].replace(/^#\s*/, '')));
    card.append(heading, element('div', 'source-path', passage.citation));
    const body = element('div', 'source-lines');
    lines.forEach((text, number) => {
      if (number === 0 || !text.trim()) return;
      const line = element('div', 'source-line');
      line.tabIndex = -1;
      line.append(element('span', 'line-number', String(number + 1)), element('span', '', text));
      body.append(line);
      sourceLines.set(path + ':' + (number + 1), line);
    });
    card.append(body);
    passages.append(card);
  });
}

function renderRules(data) {
  rule.replaceChildren();
  if (!data.rule_answer.length) {
    rule.append(element('p', '', 'The guides do not provide a supported answer to this question.'));
    return;
  }
  data.rule_answer.forEach(excerpt => {
    const line = element('div', 'answer-line');
    line.append(element('p', '', excerpt.text), citationButton(excerpt.citation));
    rule.append(line);
  });
}

function renderModel(data) {
  modelOutput.replaceChildren();
  if (data.model_error) {
    modelOutput.append(element('p', 'error', data.model_error));
    return;
  }
  if (!data.model_answer) return;
  data.model_answer.split('\n').forEach(text => {
    const line = element('p', 'answer-line');
    const match = text.match(/^(.*?)\s*\[([^\[\]]+:[0-9]+)\]$/);
    if (match && sourceLines.has(match[2])) {
      line.append(document.createTextNode(match[1] + ' '), citationButton(match[2]));
    } else {
      line.textContent = text;
    }
    modelOutput.append(line);
  });
}

function setBusy(value, comparing = false) {
  busy = value;
  document.getElementById('search-button').disabled = value;
  compare.disabled = value || !lastQuery;
  document.querySelectorAll('[data-question]').forEach(button => button.disabled = value);
  document.getElementById('search-button').textContent = value && !comparing ? 'Finding guidance…' : 'Find guidance ↗';
  compare.textContent = value && comparing ? 'Generating…' : 'Generate answer';
}

async function query(payload) {
  const response = await fetch('/api/query', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'The request could not be completed.');
  return data;
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  if (busy || !question.value.trim()) return;
  error.hidden = true;
  lastQuery = null;
  results.hidden = true;
  document.getElementById('empty-state').hidden = true;
  setBusy(true);
  status.textContent = 'Searching the guides…';
  try {
    const payload = {question: question.value.trim(), mode: mode.value};
    const data = await query(payload);
    lastQuery = payload;
    renderSources(data);
    renderRules(data);
    renderModel(data);
    results.hidden = false;
    status.textContent = 'Showing guidance for “' + data.question + '”';
  } catch (failure) {
    error.textContent = failure.message;
    error.hidden = false;
    status.textContent = 'Search could not finish.';
  } finally {
    setBusy(false);
  }
});

compare.addEventListener('click', async () => {
  if (busy || !lastQuery) return;
  error.hidden = true;
  modelOutput.replaceChildren();
  setBusy(true, true);
  status.textContent = 'Asking the local model. The first answer can take longer while Ollama loads.';
  try {
    const data = await query({...lastQuery, compare: true, model: document.getElementById('model').value});
    renderSources(data);
    renderRules(data);
    renderModel(data);
    status.textContent = data.model_error ? 'The model did not produce a usable answer. The source passages and rule-based answer are still available.'
      : 'Comparison ready. Inspect the cited lines before trusting a model claim.';
  } catch (failure) {
    modelOutput.append(element('p', 'error', failure.message));
    status.textContent = 'Comparison could not finish. The search results are still available.';
  } finally {
    setBusy(false);
  }
});

document.querySelectorAll('[data-question]').forEach(button => {
  button.addEventListener('click', () => {
    question.value = button.dataset.question;
    form.requestSubmit();
  });
});
