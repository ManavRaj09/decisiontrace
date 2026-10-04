"""SQLite trace store (stdlib only)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS traces(id TEXT PRIMARY KEY, agent TEXT, goal TEXT, started REAL, ended REAL, status TEXT);
CREATE TABLE IF NOT EXISTS steps(id INTEGER PRIMARY KEY AUTOINCREMENT, trace_id TEXT, idx INTEGER, data TEXT);
CREATE INDEX IF NOT EXISTS idx_steps_trace ON steps(trace_id);
"""


class Store:
    def __init__(self, path: str = "decisiontrace.db"):
        self.path = path
        self._lock = threading.Lock()
        self._mem = sqlite3.connect(":memory:", check_same_thread=False) if path == ":memory:" else None
        with self._conn() as c:
            c.executescript(_SCHEMA)

    @contextmanager
    def _conn(self):
        with self._lock:
            conn = self._mem or sqlite3.connect(self.path)
            try:
                yield conn
                conn.commit()
            finally:
                if conn is not self._mem:
                    conn.close()

    # ---- writes ----
    def create_trace(self, agent: str, goal: str = "", started: Optional[float] = None) -> str:
        tid = uuid.uuid4().hex[:12]
        with self._conn() as c:
            c.execute("INSERT INTO traces VALUES (?,?,?,?,?,?)",
                      (tid, agent, goal, started or time.time(), None, "running"))
        return tid

    def finish_trace(self, tid: str, status: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE traces SET ended=?, status=? WHERE id=?", (time.time(), status, tid))

    def add_step(self, tid: str, step: Dict[str, Any]) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO steps(trace_id, idx, data) VALUES (?,?,?)",
                      (tid, step["idx"], json.dumps(step, default=str)))

    # ---- reads ----
    def get_trace(self, tid: str) -> Optional[Dict[str, Any]]:
        with self._conn() as c:
            row = c.execute("SELECT id,agent,goal,started,ended,status FROM traces WHERE id=?", (tid,)).fetchone()
            if not row:
                return None
            steps = [json.loads(r[0]) for r in
                     c.execute("SELECT data FROM steps WHERE trace_id=? ORDER BY idx", (tid,))]
        keys = ("id", "agent", "goal", "started", "ended", "status")
        return {**dict(zip(keys, row)), "steps": steps}

    def list_traces(self, agent: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        with self._conn() as c:
            q, args = "SELECT id,agent,goal,started,ended,status FROM traces", []
            if agent:
                q += " WHERE agent=?"
                args.append(agent)
            q += " ORDER BY started DESC LIMIT ?"
            args.append(limit)
            rows = c.execute(q, args).fetchall()
            wanted = {r[0] for r in rows}
            steps: Dict[str, list] = {i: [] for i in wanted}
            for tid, data in c.execute("SELECT trace_id, data FROM steps"):
                if tid in wanted:
                    steps[tid].append(json.loads(data))
        out = []
        for tid, ag, goal, started, ended, status in rows:
            ss = steps[tid]
            out.append({
                "id": tid, "agent": ag, "goal": goal, "started": started, "ended": ended, "status": status,
                "steps": len(ss),
                "violations": sum(len(s["violations"]) for s in ss),
                "blocked": sum(1 for s in ss if s["status"] in ("blocked", "pending_approval")),
                "pii_steps": sum(1 for s in ss if s["pii"]),
                "cost_usd": round(sum(s.get("cost_usd") or 0 for s in ss), 6),
            })
        return out

    def agents(self) -> List[str]:
        with self._conn() as c:
            return [r[0] for r in c.execute("SELECT DISTINCT agent FROM traces ORDER BY agent")]

    def summary(self) -> Dict[str, Any]:
        ts = self.list_traces(limit=10**6)
        return {
            "traces": len(ts),
            "steps": sum(t["steps"] for t in ts),
            "violations": sum(t["violations"] for t in ts),
            "blocked": sum(t["blocked"] for t in ts),
            "cost_usd": round(sum(t["cost_usd"] for t in ts), 6),
        }
