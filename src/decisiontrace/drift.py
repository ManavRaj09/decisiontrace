"""Simple statistical drift / anomaly detection over an agent's recent traces."""
from __future__ import annotations

import statistics
from typing import Any, Dict, List

from .storage import Store

_METRICS = (("steps", "step count"), ("cost_usd", "cost per run"), ("violations", "policy violations"))


def detect(store: Store, agent: str, window: int = 50, z: float = 3.0, min_baseline: int = 5) -> List[Dict[str, Any]]:
    rows = store.list_traces(agent=agent, limit=window)  # newest first
    if len(rows) < min_baseline + 1:
        return []
    latest, base = rows[0], rows[1:]
    out = []
    for key, label in _METRICS:
        vals = [r[key] for r in base]
        mean, sd, x = statistics.fmean(vals), statistics.pstdev(vals), latest[key]
        flagged = x > mean if sd == 0 else (x - mean) / sd >= z
        if flagged:
            out.append({"agent": agent, "trace_id": latest["id"], "metric": key,
                        "message": f"{label} jumped to {x:g} (baseline average {mean:.3g})"})
    return out
