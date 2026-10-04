"""Plain-language explanation of a trace. Works offline; pass `llm` to polish the wording."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

_VERBS = {
    "retrieval": "retrieved data using",
    "llm_call": "asked the model",
    "tool_call": "called the tool",
    "output": "produced the final response",
}


def explain(trace: Dict[str, Any], llm: Optional[Callable[[str], str]] = None) -> str:
    steps = trace["steps"]
    lines = [f"Agent '{trace['agent']}' was working on: {trace['goal'] or 'an unspecified goal'}.",
             f"It took {len(steps)} step(s)."]
    for s in steps:
        line = f"{s['idx'] + 1}. The agent {_VERBS.get(s['type'], 'performed')} `{s['name']}`."
        if s["pii"]:
            line += f" Sensitive data present: {', '.join(s['pii'])}."
        if s["status"] == "blocked":
            line += " This action was BLOCKED by policy and never executed."
        elif s["status"] == "pending_approval":
            line += " This action was held for human approval and not executed."
        elif s["status"] == "approved":
            line += " A human approved this action."
        for v in s["violations"]:
            line += f"\n     - [{v['action']}] {v['rule_id']}: {v['message']}"
        lines.append(line)
    blocked = sum(1 for s in steps if s["status"] in ("blocked", "pending_approval"))
    hits = sum(len(s["violations"]) for s in steps)
    lines.append(f"Verdict: {hits} policy hit(s), {blocked} action(s) stopped."
                 if hits else "Verdict: no policy issues found.")
    text = "\n".join(lines)
    if llm:
        try:
            return llm("Rewrite this AI-agent audit log as a short plain-English summary for a "
                       "compliance manager. Do not add facts.\n\n" + text)
        except Exception:
            pass
    return text
