"""Durable test-only accounting for the three approved local ASR gate calls."""

import datetime
import fcntl
import json
from pathlib import Path


def spend(label):
    path = Path("ragflow-logs/phase6-16-asr-calls.json")
    path.parent.mkdir(exist_ok=True)
    with path.open("a+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        rows = json.loads(stream.read() or "[]")
        retained = Path(".planning/phases/06-deep-parsing-and-chunking-breadth/06-16-ASR-OBSERVED.json")
        if retained.exists():
            recorded = json.loads(retained.read_text())["calls"]
            if len(recorded) > len(rows):
                rows = recorded
        assert len(rows) < 3, "Approved ASR cap exhausted; preserve successful evidence instead of replaying."
        assert not any(row["label"] == label for row in rows), "This ASR gate request was already submitted."
        rows.append({"label": label, "submitted_at": datetime.datetime.now(datetime.timezone.utc).isoformat()})
        stream.seek(0)
        stream.truncate()
        stream.write(json.dumps(rows, indent=2) + "\n")
        stream.flush()
