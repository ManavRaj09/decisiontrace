"""Tracer: records every agent step, enforces policy BEFORE tools run, masks PII at rest."""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

from .pii import detect_obj, mask_obj
from .policy import Policy, PolicyViolation, worst_action
from .storage import Store


class Tracer:
    def __init__(self, store: Optional[Store] = None, policy: Optional[Policy] = None,
                 mask_pii: bool = True, approver: Optional[Callable[[Dict[str, Any]], bool]] = None):
        self.store = store or Store(":memory:")
        self.policy = policy or Policy.default()
        self.mask_pii = mask_pii
        self.approver = approver  # callable(step) -> bool; None means "always hold for a human"

    def trace(self, agent: str, goal: str = "", started: Optional[float] = None) -> "TraceContext":
        return TraceContext(self, agent, goal, started)


class TraceContext:
    def __init__(self, tracer: Tracer, agent: str, goal: str, started: Optional[float]):
        self.tracer, self.agent, self.goal, self._started = tracer, agent, goal, started
        self.id = ""
        self._idx = 0

    def __enter__(self) -> "TraceContext":
        self.id = self.tracer.store.create_trace(self.agent, self.goal, self._started)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            status = "completed"
        elif issubclass(exc_type, PolicyViolation):
            status = "halted"
        else:
            status = "error"
        self.tracer.store.finish_trace(self.id, status)
        return False

    # ---- internals ----
    def _new_step(self, type_, name, inp, out, cost_usd, latency_ms) -> Dict[str, Any]:
        step = {"idx": self._idx, "type": type_, "name": name, "input": inp, "output": out,
                "pii": [], "violations": [], "status": "ok",
                "cost_usd": cost_usd, "latency_ms": latency_ms, "ts": time.time()}
        self._idx += 1
        return step

    def _evaluate(self, step: Dict[str, Any]) -> str:
        step["pii"] = sorted({f.type for f in detect_obj([step["input"], step["output"]])})
        known = {v["rule_id"] for v in step["violations"]}
        for v in self.tracer.policy.evaluate(step):
            if v.rule_id not in known:
                step["violations"].append(v.to_dict())
        return worst_action(step["violations"])

    def _persist(self, step: Dict[str, Any]) -> None:
        stored = dict(step)
        if self.tracer.mask_pii:
            stored["input"], stored["output"] = mask_obj(step["input"]), mask_obj(step["output"])
        self.tracer.store.add_step(self.id, stored)

    # ---- public API ----
    def record(self, type: str, name: str, input: Any = None, output: Any = None,
               cost_usd: float = 0.0, latency_ms: Optional[int] = None) -> Dict[str, Any]:
        """Observe a step that already happened (LLM call, retrieval, final answer...)."""
        step = self._new_step(type, name, input, output, cost_usd, latency_ms)
        self._evaluate(step)
        self._persist(step)
        return step

    def call_tool(self, name: str, fn: Callable[..., Any], **kwargs: Any) -> Any:
        """Run a tool through the policy engine. Blocked calls are NEVER executed."""
        step = self._new_step("tool_call", name, kwargs, None, 0.0, None)
        action = self._evaluate(step)
        if action == "block":
            step["status"] = "blocked"
            self._persist(step)
            raise PolicyViolation(action, step["violations"], step)
        if action == "require_approval":
            approver = self.tracer.approver
            if not (approver and approver(step)):
                step["status"] = "pending_approval"
                self._persist(step)
                raise PolicyViolation(action, step["violations"], step)
            step["status"] = "approved"
        t0 = time.time()
        result = fn(**kwargs)
        step["latency_ms"] = int((time.time() - t0) * 1000)
        step["output"] = result
        self._evaluate(step)  # re-check with the tool's output included
        self._persist(step)
        return result
