"""Command line interface: `decisiontrace --help`."""
from __future__ import annotations

import argparse
import importlib
import sys

from . import redteam
from .dashboard import serve
from .demo import make_hardened_agent, make_naive_agent, seed_demo
from .drift import detect
from .explain import explain
from .report import generate_report
from .storage import Store


def _print_redteam(title: str, res: dict) -> None:
    print(f"\n{title}: grade {res['grade']}  ({res['passed']}/{res['total']} attacks resisted)")
    for r in res["results"]:
        print(f"  [{'PASS' if r['passed'] else 'FAIL'}] {r['id']:<14} {r['category']:<20} {r['reason']}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="decisiontrace", description="Flight recorder & guardrails for AI agents")
    sub = p.add_subparsers(dest="cmd", required=True)
    db = argparse.ArgumentParser(add_help=False)
    db.add_argument("--db", default="decisiontrace.db", help="SQLite file (default: decisiontrace.db)")

    d = sub.add_parser("demo", parents=[db], help="seed demo traces (and optionally open the dashboard)")
    d.add_argument("--serve", action="store_true")
    d.add_argument("--port", type=int, default=8000)
    sd = sub.add_parser("dashboard", parents=[db], help="start the web dashboard")
    sd.add_argument("--port", type=int, default=8000)
    sd.add_argument("--host", default="127.0.0.1")
    ex = sub.add_parser("explain", parents=[db], help="plain-language explanation of one trace")
    ex.add_argument("trace_id")
    sub.add_parser("anomalies", parents=[db], help="detect behaviour drift")
    r = sub.add_parser("report", parents=[db], help="write an HTML audit report")
    r.add_argument("--out", default="audit_report.html")
    rt = sub.add_parser("redteam", help="attack an agent and score its robustness")
    rt.add_argument("--demo", action="store_true", help="compare a weak and a hardened mock agent")
    rt.add_argument("--target", help="your agent as module:function, taking a prompt and returning text")
    rt.add_argument("--canary", help="secret string planted in your agent's system prompt")

    a = p.parse_args(argv)

    if a.cmd == "demo":
        store = Store(a.db)
        seed_demo(store)
        s = store.summary()
        print(f"Seeded {s['traces']} traces ({s['violations']} policy hits, {s['blocked']} actions stopped) into {a.db}")
        if a.serve:
            serve(store, port=a.port)
        else:
            print(f"Next: decisiontrace dashboard --db {a.db}")
    elif a.cmd == "dashboard":
        serve(Store(a.db), a.host, a.port)
    elif a.cmd == "explain":
        trace = Store(a.db).get_trace(a.trace_id)
        if not trace:
            print("Trace not found", file=sys.stderr)
            return 1
        print(explain(trace))
    elif a.cmd == "anomalies":
        store = Store(a.db)
        found = [x for ag in store.agents() for x in detect(store, ag)]
        print("\n".join(f"{x['agent']}: {x['message']} (trace {x['trace_id']})" for x in found) or "No anomalies.")
    elif a.cmd == "report":
        print("Wrote", generate_report(Store(a.db), a.out))
    elif a.cmd == "redteam":
        if a.target:
            mod, _, fn = a.target.partition(":")
            sys.path.insert(0, ".")
            _print_redteam(a.target, redteam.run(getattr(importlib.import_module(mod), fn), a.canary))
        else:
            c = redteam.new_canary()
            _print_redteam("Naive agent", redteam.run(make_naive_agent(c), c))
            _print_redteam("Hardened agent", redteam.run(make_hardened_agent(c), c))
    return 0


if __name__ == "__main__":
    sys.exit(main())
