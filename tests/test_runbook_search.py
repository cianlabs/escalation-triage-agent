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
