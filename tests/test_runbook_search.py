from runbook_search import RUNBOOKS, search


def test_hits_are_ranked_and_cite_exact_text():
    hits = search('Redis cache maxmemory')
    assert hits[0][1].startswith('runbooks/redis_memory.txt:')
    assert len(hits) <= 3
    for _, citation, passage in hits:
        path, line_range = citation.split(':')
        start, end = map(int, line_range.split('-'))
        lines = (RUNBOOKS / path.split('/')[-1]).read_text(encoding='utf-8').splitlines()
        assert passage == '\n'.join(lines[start - 1:end])


def test_no_shared_terms_returns_no_passage():
    assert search('Rotate the production TLS certificate') == []


def test_redis_query_omits_generic_check_matches():
    hits = search('What should I check if Redis hits maxmemory?')
    assert [citation for _, citation, _ in hits] == ['runbooks/redis_memory.txt:1-5']


def test_answer_quotes_redis_check_and_line():
    from runbook_search import answer

    question = 'What should I check if Redis hits maxmemory?'
    assert answer(question, search(question)) == [
        ('runbooks/redis_memory.txt:4', 'Check memory eviction settings and keyspace metrics.'),
    ]


def test_answer_abstains_on_unsupported_deployment_cancellation():
    from runbook_search import answer

    question = "How do I cancel a deployment that's stuck waiting for a reviewer?"
    assert search(question)
    assert answer(question, search(question)) == []
