"""Local traces for one agent run.

Each trace is a JSON file. It keeps the case input, the tool calls the model
made, the stop reason, and a wall-clock duration. Nothing here calls a model
provider or a tracing service. Do not put API keys in a trace.
"""

import json
import time
from pathlib import Path


def start_trace(case_id, kind, case_input):
    """Begin a trace. `case_input` must already be synthetic."""
    return {
        "case_id": case_id,
        "kind": kind,
        "input": case_input,
        "events": [],
        "_t0": time.perf_counter(),
    }


def add_event(trace, **fields):
    """Append one observation. Elapsed time is milliseconds since the start."""
    event = dict(fields)
    event["at_ms"] = round((time.perf_counter() - trace["_t0"]) * 1000, 3)
    trace["events"].append(event)


def finish_trace(trace, **fields):
    """Close the trace and drop the clock handle so the file is plain JSON."""
    finished = {key: value for key, value in trace.items() if key != "_t0"}
    finished.update(fields)
    finished["elapsed_ms"] = round((time.perf_counter() - trace["_t0"]) * 1000, 3)
    return finished


def write_trace(directory, trace):
    """Write `<case_id>.json`. The case id is used as a file name, so it must be safe."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    case_id = trace["case_id"]
    if not isinstance(case_id, str) or not case_id or "/" in case_id or ".." in case_id:
        raise ValueError(f"unsafe trace case id: {case_id!r}")
    path = directory / f"{case_id}.json"
    path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")
    return path
