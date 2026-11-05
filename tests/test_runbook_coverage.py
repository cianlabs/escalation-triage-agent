"""Keyword retrieval over the expanded runbooks/ directory."""
from runbook_search import answer, guide_names, search


def test_every_runbook_file_is_indexed():
    names = guide_names()
    assert len(names) >= 24
    assert 'worker_memory.txt' in names
    assert 'tls_certificate_expiry.txt' in names
    assert 'kafka_consumer_lag.txt' in names


def test_common_incident_topics_retrieve_a_cited_runbook():
    cases = {
        'TLS certificates expire tonight. What should I check before renewing them?':
            'runbooks/tls_certificate_expiry.txt',
        'Sign-in fails for every account and the identity provider is erroring.':
            'runbooks/auth_sso_outage.txt',
        'Kafka consumers are lagging behind the topic. What should I check?':
            'runbooks/kafka_consumer_lag.txt',
        'The CDN edge is returning 502 responses. What should I check?':
            'runbooks/cdn_edge_errors.txt',
        'Callers are getting HTTP 429 quota exceeded. What should I check?':
            'runbooks/rate_limit_429.txt',
        'Postgres sessions are waiting on locks. What should I check?':
            'runbooks/postgres_locks.txt',
        'Payment webhooks are failing delivery. What should I check?':
            'runbooks/payment_webhook.txt',
        'A feature flag rollout matches the start of errors. What should I check?':
            'runbooks/feature_flag_misconfig.txt',
        'Clients cannot resolve our hostname. What should I check?':
            'runbooks/dns_resolution.txt',
        'The host says there is no space left on the device. What should I check?':
            'runbooks/disk_full.txt',
    }
    for question, path in cases.items():
        hits = search(question)
        assert hits, question
        assert hits[0][1].startswith(path + ':'), (question, hits[0][1])


def test_tls_check_cites_the_runbook_line():
    question = 'TLS certificates expire tonight. What should I check before renewing them?'
    excerpts = answer(question, search(question))
    assert excerpts
    assert excerpts[0][0].startswith('runbooks/tls_certificate_expiry.txt:')
    assert 'certificate end date' in excerpts[0][1]


def test_held_out_topic_returns_no_runbook_and_no_invented_steps():
    question = 'How do I recalibrate the lunar rover antenna?'
    hits = search(question)
    assert hits == []
    assert answer(question, hits) == []
