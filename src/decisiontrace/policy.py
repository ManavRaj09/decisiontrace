"""Declarative policy engine: rules are plain JSON (or YAML if PyYAML is installed)."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

from .pii import to_text

ACTIONS = ("flag", "require_approval", "block")
SEVERITY = {"allow": 0, "flag": 1, "require_approval": 2, "block": 3}


@dataclass
class Violation:
    rule_id: str
    action: str
    message: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


class PolicyViolation(Exception):
    """Raised when an agent action is blocked or held for approval."""

    def __init__(self, action: str, violations: List[Dict[str, str]], step: Dict[str, Any]):
        self.action = action
        self.violations = violations
        self.step = step
        msgs = "; ".join(f"{v['rule_id']}: {v['message']}" for v in violations)
        super().__init__(f"{action.upper()} - {msgs}")


def worst_action(violations) -> str:
    worst = "allow"
    for v in violations:
        a = v["action"] if isinstance(v, dict) else v.action
        if SEVERITY[a] > SEVERITY[worst]:
            worst = a
    return worst


def _as_list(x):
    return x if isinstance(x, (list, tuple)) else [x]


class Policy:
    def __init__(self, rules: List[Dict[str, Any]]):
        for r in rules:
            if "id" not in r or not isinstance(r.get("when"), dict):
                raise ValueError(f"Rule needs 'id' and a 'when' object: {r}")
            if r.get("action") not in ACTIONS:
                raise ValueError(f"Rule {r['id']}: action must be one of {ACTIONS}")
        self.rules = rules

    @classmethod
    def default(cls) -> "Policy":
        return cls.from_file(Path(__file__).with_name("default_policy.json"))

    @classmethod
    def from_file(cls, path) -> "Policy":
        p = Path(path)
        raw = p.read_text(encoding="utf-8")
        if p.suffix in (".yaml", ".yml"):
            try:
                import yaml  # type: ignore
            except ImportError as exc:
                raise RuntimeError("YAML policies need PyYAML: pip install 'decisiontrace[yaml]'") from exc
            data = yaml.safe_load(raw)
        else:
            data = json.loads(raw)
        return cls(data["rules"])

    def evaluate(self, step: Dict[str, Any]) -> List[Violation]:
        text = to_text([step.get("input"), step.get("output")])
        hits = []
        for rule in self.rules:
            if self._matches(rule["when"], step, text):
                hits.append(Violation(rule["id"], rule["action"], rule.get("description", rule["id"])))
        return hits

    @staticmethod
    def _matches(when: Dict[str, Any], step: Dict[str, Any], text: str) -> bool:
        inp = step.get("input") if isinstance(step.get("input"), dict) else {}
        if "step_type" in when and step["type"] not in _as_list(when["step_type"]):
            return False
        if "name" in when and step["name"] not in _as_list(when["name"]):
            return False
        if "pii" in when:
            want, found = when["pii"], set(step.get("pii", []))
            if want is True and not found:
                return False
            if want is False and found:
                return False
            if isinstance(want, list) and not (found & set(want)):
                return False
        if "regex" in when and not re.search(when["regex"], text, re.I):
            return False
        if "field_gt" in when:
            spec = when["field_gt"]
            try:
                if float(inp.get(spec["field"])) <= float(spec["value"]):
                    return False
            except (TypeError, ValueError):
                return False
        if "recipient_not_in_domains" in when:
            to = inp.get("to")
            if not isinstance(to, str) or "@" not in to:
                return False
            allowed = {d.lower() for d in when["recipient_not_in_domains"]}
            if to.rsplit("@", 1)[1].lower() in allowed:
                return False
        return True
