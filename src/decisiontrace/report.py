"""Self-contained HTML audit report (open in a browser and 'Print to PDF')."""
from __future__ import annotations

import html
import time
from typing import Optional

from .drift import detect
from .explain import explain
from .storage import Store

_CSS = ("body{font:15px/1.5 system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#222}"
        "h1,h2{margin:1.4rem 0 .4rem}table{border-collapse:collapse;width:100%}"
        "td,th{border:1px solid #ddd;padding:6px 8px;text-align:left}th{background:#f3f3f3}"
        "pre{background:#f7f7f7;padding:10px;white-space:pre-wrap;border-radius:6px}.bad{color:#b00020}")


def generate_report(store: Store, path: str, agent: Optional[str] = None) -> str:
    e = html.escape
    traces = store.list_traces(agent=agent, limit=1000)
    s = store.summary()
    parts = [f"<!doctype html><meta charset='utf-8'><title>DecisionTrace audit report</title><style>{_CSS}</style>",
             "<h1>AI Agent Audit Report</h1>",
             f"<p>Generated {time.strftime('%Y-%m-%d %H:%M')} &middot; {s['traces']} traces &middot; {s['steps']} steps "
             f"&middot; {s['violations']} policy hits &middot; {s['blocked']} actions stopped &middot; ${s['cost_usd']:.4f} total cost</p>"]
    anomalies = [a for ag in ([agent] if agent else store.agents()) for a in detect(store, ag)]
    parts.append("<h2>Anomalies</h2>" + ("<ul>" + "".join(f"<li class='bad'>{e(a['agent'])}: {e(a['message'])}</li>" for a in anomalies)
                                          + "</ul>" if anomalies else "<p>None detected.</p>"))
    parts.append("<h2>Traces with policy activity</h2><table><tr><th>Trace</th><th>Agent</th><th>Goal</th><th>Hits</th><th>Stopped</th></tr>")
    for t in traces:
        if t["violations"]:
            parts.append(f"<tr><td>{e(t['id'])}</td><td>{e(t['agent'])}</td><td>{e(t['goal'])}</td>"
                         f"<td>{t['violations']}</td><td>{t['blocked']}</td></tr>")
    parts.append("</table><h2>Explanations</h2>")
    for t in traces:
        if t["violations"]:
            parts.append(f"<h3>{e(t['id'])}</h3><pre>{e(explain(store.get_trace(t['id'])))}</pre>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(parts))
    return path
