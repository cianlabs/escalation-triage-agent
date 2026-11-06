"""Streamlit page for one synthetic escalation triage.

Community Cloud looks for this file at the repository root. The triage loop,
the approval gate, and the simulated action log stay in agent.py and tools.py.
This file only draws that result and keeps one approval session in the browser
(st.session_state), so two visitors do not share a pending action or a log.

Practice mode is the default. If XAI_API_KEY is unset, PracticeModel answers
from the bundled fixtures and does not call the model. On Streamlit Cloud, put
the key in the app Secrets as XAI_API_KEY. This file copies that secret into
the process environment so agent.make_client can read it. The value is never
printed and never written into the page.

Run locally:

    streamlit run streamlit_app.py
"""

import contextlib
import io
import os
import tempfile
from pathlib import Path

import agent
from errors import AgentError
from practice_model import PracticeModel
from sample_data import SAMPLE_ID

try:
    import streamlit as st
except ImportError:  # pytest stays green when Streamlit is not installed
    st = None


def apply_streamlit_secret(secrets=None):
    """Copy XAI_API_KEY from Streamlit secrets into the environment.

    An existing environment variable is left alone, so a local export wins.
    A missing secrets file is practice mode. The key is not returned.
    """
    if os.environ.get("XAI_API_KEY", "").strip():
        return
    if secrets is None:
        if st is None:
            return
        try:
            secrets = st.secrets
        except Exception:
            return
    try:
        if "XAI_API_KEY" not in secrets:
            return
        raw = secrets["XAI_API_KEY"]
    except Exception:
        return
    text = str(raw).strip() if raw is not None else ""
    if text:
        os.environ["XAI_API_KEY"] = text


def live_key_present():
    return bool(os.environ.get("XAI_API_KEY", "").strip())


def mode_banner():
    """Which model triages. The banner never includes the key."""
    if live_key_present():
        return (
            "**Live mode.** The real model triages this synthetic ticket. "
            "The API key comes from Streamlit secrets or the environment. "
            "It is not shown here. The ticket, logs, and runbooks are still "
            "synthetic fixtures, not customer data. "
            "**Approve and simulate** only appends a simulated line. "
            "Nothing is restarted, rolled back, paged, or emailed."
        )
    return (
        "**Practice mode.** No API key is set, so the built-in practice model "
        "triages the synthetic sample. It does not call the model network. "
        "The ticket, logs, and runbooks are synthetic fixtures, not customer data. "
        "**Approve and simulate** only appends a simulated line, the same as typing "
        "`y` in the terminal. Nothing is restarted, rolled back, paged, or emailed. "
        "To use the real model, add `XAI_API_KEY` under Secrets on Streamlit Community Cloud "
        "and reboot the app. Do not paste the key into this page."
    )


def ensure_session(store):
    """One browser's memory directory and action log.

    `store` is st.session_state or a plain dict. A second visitor gets a
    different directory, so their pending proposal is not this one.
    """
    session = store.get("triage_session")
    if not isinstance(session, dict) or "memory_dir" not in session or "action_log" not in session:
        root = Path(tempfile.mkdtemp(prefix="triage-demo-"))
        session = {
            "memory_dir": root / "memory",
            "action_log": root / "action.log",
            "view": None,
        }
        store["triage_session"] = session
    return session


def _citations(state):
    hits = getattr(state, "runbook_hits", None) or []
    if not hits:
        return "No runbook sections were cited."
    lines = []
    for hit in hits:
        snippet = (hit.get("text") or "").replace("\n", " ").strip()
        if len(snippet) > 220:
            snippet = snippet[:217] + "..."
        lines.append(f"- {hit.get('source')} — {hit.get('section')}: {snippet}")
    return "\n".join(lines)


def _hypotheses(state):
    rows = state.hypotheses or []
    if not rows:
        return "No hypotheses yet."
    lines = []
    for index, hypothesis in enumerate(rows, start=1):
        ids = ", ".join(hypothesis.get("supporting_evidence_ids") or []) or "none"
        lines.append(
            f"{index}. {hypothesis.get('title')} — evidence {ids} ({hypothesis.get('status')})"
        )
    lines.append("Confirmed root cause: none")
    return "\n".join(lines)


def _pending_text(proposal):
    if not isinstance(proposal, dict):
        return ""
    return "\n".join([
        "Nothing has run yet.",
        f"kind: {proposal.get('kind')}",
        f"target: {proposal.get('target')}",
        f"reason: {proposal.get('reason')}",
        f"details: {proposal.get('details')}",
        "A yes appends one simulated line. It does not restart, roll back, page anyone, or send the draft.",
    ])


def view_from_result(result, action_log):
    """Plain text for the page. Does not include an API key."""
    state = result.state
    log_path = Path(action_log)
    log_text = ""
    if log_path.exists():
        log_text = log_path.read_text(encoding="utf-8").strip()
    return {
        "error": "",
        "stop_reason": result.stop_reason,
        "summary": result.summary,
        "hypotheses": _hypotheses(state),
        "draft": state.customer_draft or "(no draft)",
        "citations": _citations(state),
        "trace": "\n".join(state.step_log) or "(no steps)",
        "pending": _pending_text(state.pending_approval),
        "log_text": log_text,
        "escalation_id": state.escalation_id,
    }


def _run(session, *, defer_approval, answer, fresh):
    memory_dir = Path(session["memory_dir"])
    action_log = Path(session["action_log"])
    if fresh:
        path = agent.memory_path(memory_dir, SAMPLE_ID)
        if path.exists():
            path.unlink()
    use_real = live_key_present() and defer_approval
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            result = agent.run_escalation(
                SAMPLE_ID,
                model=None if use_real else PracticeModel(),
                ask=lambda _prompt: answer,
                memory_dir=memory_dir,
                action_log=action_log,
                defer_approval=defer_approval,
                use_real=use_real,
            )
    except AgentError as err:
        return {
            "error": str(err),
            "stop_reason": "",
            "summary": "",
            "hypotheses": "",
            "draft": "",
            "citations": "",
            "trace": "",
            "pending": "",
            "log_text": "",
            "escalation_id": SAMPLE_ID,
        }
    if result is None:
        return {
            "error": "The triage loop did not return a result.",
            "stop_reason": "",
            "summary": "",
            "hypotheses": "",
            "draft": "",
            "citations": "",
            "trace": "",
            "pending": "",
            "log_text": "",
            "escalation_id": SAMPLE_ID,
        }
    return view_from_result(result, action_log)


def on_sample(session):
    """Same path as `agent.py --sample --fresh --defer-approval`."""
    view = _run(session, defer_approval=True, answer="", fresh=True)
    session["view"] = view
    return view


def on_approve(session):
    """Same gate as typing y. Only boolean True records a simulated line."""
    view = _run(session, defer_approval=False, answer="y", fresh=False)
    session["view"] = view
    return view


def on_refuse(session):
    """Same gate as typing n. The action log is not written."""
    view = _run(session, defer_approval=False, answer="n", fresh=False)
    session["view"] = view
    return view


def draw(view, session):
    if view.get("error"):
        st.error(view["error"])
        return
    st.subheader("Why it stopped")
    st.write(view.get("summary") or "")
    if view.get("stop_reason"):
        st.caption(f"Stop reason: {view['stop_reason']}")
    st.subheader("Ranked hypotheses")
    st.text(view.get("hypotheses") or "")
    st.caption("These are unverified. None of them is a confirmed root cause.")
    st.subheader("Customer draft (not sent)")
    st.text(view.get("draft") or "")
    st.subheader("Runbook citations")
    st.text(view.get("citations") or "")
    st.subheader("What the agent did, step by step")
    st.text(view.get("trace") or "")
    if view.get("log_text"):
        st.subheader("Simulated action log")
        st.text(view["log_text"])
        st.caption("This line is a simulation in this browser's log. No service was changed.")
    if view.get("pending"):
        st.subheader("This action has not run")
        st.text(view["pending"])
        st.caption(
            "Approve and simulate uses the same rule as typing y in the terminal: "
            "one simulated line is appended for this browser session. "
            "Do not run writes nothing. Nothing is restarted, rolled back, paged, or emailed."
        )
        yes, no = st.columns(2)
        if yes.button("Approve and simulate", type="primary"):
            on_approve(session)
            st.rerun()
        if no.button("Do not run"):
            on_refuse(session)
            st.rerun()


def main():
    if st is None:
        raise RuntimeError(
            "Streamlit is not installed. Install it with: pip install -r requirements.txt"
        )
    apply_streamlit_secret()
    st.set_page_config(page_title="Escalation triage", layout="centered")
    session = ensure_session(st.session_state)
    st.title("Escalation triage")
    st.write(
        "Run one synthetic support escalation. You will see ranked hypotheses, "
        "a customer draft that is not sent, runbook citations, the stop reason, "
        "and the step trace. Nothing runs until you click **Approve and simulate**, "
        "and that click only appends a simulated line. "
        "The fixtures in this demo are not customer data."
    )
    st.markdown(mode_banner())
    st.write(f"Sample ticket: `{SAMPLE_ID}` (synthetic checkout-style outage).")
    if st.button("Run the practice sample"):
        on_sample(session)
        st.rerun()
    view = session.get("view")
    if view:
        draw(view, session)


if __name__ == "__main__":
    main()
