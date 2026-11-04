import pytest

from runbook_selection_eval import render_selection


def test_selection_renders_exact_source_text():
    evidence = {'guide:4': 'Inspect settings and metrics.'}
    assert render_selection(['guide:4'], evidence) == 'Inspect settings and metrics. [guide:4]'


@pytest.mark.parametrize('selected', [['guide:99'], ['guide:4', 'guide:4'], [{}]])
def test_rejects_unknown_duplicate_or_malformed_ids(selected):
    with pytest.raises(ValueError):
        render_selection(selected, {'guide:4': 'Source text'})
