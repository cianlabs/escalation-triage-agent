"""The command-line entry point, still on fake data."""

import json

from agent import main


def test_list_prints_the_practice_catalog(capsys):
    code = main(["--list"])
    assert code == 0
    out = capsys.readouterr().out
    assert "ESC-1001" in out
    assert "ESC-1005" in out
    assert "Checkout 500s after a deploy" in out


def test_sample_defer_saves_memory_and_does_not_ask(tmp_path, capsys):
    memory = tmp_path / "memory"
    log = tmp_path / "action.log"
    code = main([
        "--sample",
        "--defer-approval",
        "--fresh",
        "--memory-dir",
        str(memory),
        "--action-log",
        str(log),
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "Stop reason: APPROVAL_REQUIRED" in out
    assert "Approve this action? (y/n)" not in out
    assert not log.exists()
    saved = json.loads((memory / "ESC-1001.json").read_text(encoding="utf-8"))
    assert saved["pending_approval"]["status"] == "pending"
    assert saved["pending_approval"]["kind"] == "rollback"


def test_unknown_id_is_a_named_error_on_stderr(tmp_path, capsys):
    code = main([
        "ESC-9999",
        "--memory-dir",
        str(tmp_path / "memory"),
        "--action-log",
        str(tmp_path / "action.log"),
    ])
    assert code == 1
    err = capsys.readouterr().err
    assert err.startswith("UNKNOWN_ESCALATION:")
