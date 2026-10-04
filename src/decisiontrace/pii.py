"""PII and secret detection / masking (regex based, zero dependencies)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, List


@dataclass(frozen=True)
class Finding:
    type: str
    value: str
    start: int
    end: int


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# Order matters: earlier patterns claim their text span first.
_PATTERNS = [
    ("AWS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("API_KEY", re.compile(r"\b(?:sk|pk|ghp|xox[bp])[-_][A-Za-z0-9_-]{16,}\b")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d[ -]?){12,18}\d\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?\d{1,3}[ -]?)?(?:\(\d{3}\)|\d{3})[ -]?\d{3}[ -]?\d{4}(?!\d)")),
]


def detect(text: str) -> List[Finding]:
    taken, found = [], []
    for kind, rx in _PATTERNS:
        for m in rx.finditer(text):
            s, e = m.span()
            if any(s < te and e > ts for ts, te in taken):
                continue
            if kind == "CREDIT_CARD":
                digits = re.sub(r"\D", "", m.group())
                if not (13 <= len(digits) <= 19 and _luhn(digits)):
                    continue
            taken.append((s, e))
            found.append(Finding(kind, m.group(), s, e))
    return sorted(found, key=lambda f: f.start)


def mask(text: str) -> str:
    out, last = [], 0
    for f in detect(text):
        out.append(text[last:f.start])
        out.append(f"[{f.type}_REDACTED]")
        last = f.end
    out.append(text[last:])
    return "".join(out)


def to_text(obj: Any) -> str:
    return obj if isinstance(obj, str) else json.dumps(obj, default=str, ensure_ascii=False)


def detect_obj(obj: Any) -> List[Finding]:
    return detect(to_text(obj))


def mask_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return mask(obj)
    if isinstance(obj, dict):
        return {k: mask_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [mask_obj(v) for v in obj]
    return obj
