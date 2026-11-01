"""The state object and the one JSON file that stores it."""

import json

import pytest

from errors import AgentError
from sample_data import get_escalation
from state import EscalationState, load_state, memory_path, save_state


def test_round_trip_keeps_the_checklist_and_the_evidence(tmp_path):
    state = EscalationState.from_sample(get_escalation("ESC-1001"))
    state.checked["runbooks"] = True
    state.evidence.append({"id": "log-1", "source": "checkout-api.log", "observation": "error rate jumped"})
    state.step_log.append("search_runbooks: 1 hit(s)")
    path = save_state(state, tmp_path)
    loaded = load_state("ESC-1001", tmp_path)
    assert path.name == "ESC-1001.json"
    assert loaded.to_dict() == state.to_dict()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["escalation_id"] == "ESC-1001"
    assert "api_key" not in path.read_text(encoding="utf-8").lower()
    assert "xai_api_key" not in path.read_text(encoding="utf-8").lower()


def test_missing_file_returns_none(tmp_path):
    assert load_state("ESC-1001", tmp_path) is None


def test_bad_escalation_id_cannot_escape_the_memory_directory(tmp_path):
    with pytest.raises(AgentError) as caught:
        memory_path(tmp_path, "../ESC-1001")
    assert caught.value.name == "BAD_ESCALATION_ID"


def test_memory_file_for_a_different_id_is_rejected(tmp_path):
    state = EscalationState.from_sample(get_escalation("ESC-1001"))
    save_state(state, tmp_path)
    path = tmp_path / "ESC-1001.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["escalation_id"] = "ESC-1002"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(AgentError) as caught:
        load_state("ESC-1001", tmp_path)
    assert caught.value.name == "MEMORY_MISMATCH"


def test_empty_ticket_is_rejected():
    with pytest.raises(AgentError) as caught:
        EscalationState.from_sample({
            "id": "ESC-1",
            "ticket": "  ",
            "customer_tier": "gold",
            "service": "checkout-api",
        })
    assert caught.value.name == "EMPTY_ESCALATION"
