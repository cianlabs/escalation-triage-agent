"""Evaluation harness for incident root cause accuracy.

Gives the agent only the symptoms (the ticket) for each incident, runs it offline
with the practice model, and evaluates whether its top-ranked hypothesis matches
the published root cause.
"""

from practice_model import PracticeModel
from sample_data import list_real_incidents
from state import EscalationState, add_evidence
from tools import call_tool


def run_incident_evaluation():
    """Run offline triage evaluation across all real incidents."""
    results = []
    correct_count = 0
    incidents = list_real_incidents()
    total_count = len(incidents)

    for incident in incidents:
        state = EscalationState.from_sample(incident)
        model = PracticeModel()
        last_tool_result = None

        # Step 1: search_runbooks
        turn = model.next_turn(state, last_tool_result)
        tool_res = call_tool(turn.name, turn.arguments)
        state.checked["runbooks"] = True
        state.runbook_hits = tool_res
        last_tool_result = str(tool_res)

        # Step 2: read_logs
        turn = model.next_turn(state, last_tool_result)
        tool_res = call_tool(turn.name, turn.arguments)
        state.checked["logs"] = True
        add_evidence(state, tool_res["evidence"])
        last_tool_result = str(tool_res)

        # Step 3: check_recent_deploys
        turn = model.next_turn(state, last_tool_result)
        tool_res = call_tool(turn.name, turn.arguments)
        state.checked["deploys"] = True
        state.deploys = tool_res["deploys"]
        add_evidence(state, tool_res["evidence"])
        last_tool_result = str(tool_res)

        # Step 4: rank_hypotheses
        turn = model.next_turn(state, last_tool_result)
        tool_res = call_tool(turn.name, turn.arguments)
        state.hypotheses = tool_res["hypotheses"]

        top_hypothesis = state.hypotheses[0]["title"] if state.hypotheses else "None"
        published_cause = incident.get("published_root_cause", "Unknown")
        match = (top_hypothesis == published_cause)
        if match:
            correct_count += 1

        results.append({
            "id": incident["id"],
            "title": incident["title"],
            "published_root_cause": published_cause,
            "top_ranked_cause": top_hypothesis,
            "match": match,
        })

    score = correct_count / total_count if total_count > 0 else 0.0
    return {
        "total": total_count,
        "correct": correct_count,
        "score": score,
        "results": results,
    }


def print_evaluation_results(eval_summary=None):
    """Print a clean Markdown/text results table."""
    if eval_summary is None:
        eval_summary = run_incident_evaluation()

    print("\n=== Incident Triage Offline Evaluation Results ===")
    print(f"Total Incidents: {eval_summary['total']}")
    print(f"Correct Top-Ranked Matches: {eval_summary['correct']}")
    print(f"Accuracy Score: {eval_summary['score'] * 100:.1f}%\n")

    header = f"| {'Incident ID':<18} | {'Published Root Cause':<22} | {'Top-Ranked Cause':<22} | {'Match':<5} |"
    divider = f"|{'-'*20}|{'-'*24}|{'-'*24}|{'-'*7}|"
    print(header)
    print(divider)
    for r in eval_summary["results"]:
        match_str = "YES" if r["match"] else "NO"
        print(f"| {r['id']:<18} | {r['published_root_cause']:<22} | {r['top_ranked_cause']:<22} | {match_str:<5} |")
    print()


if __name__ == "__main__":
    print_evaluation_results()
