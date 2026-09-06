"""Secret detection + redaction.

Two jobs (THREAT_MODEL T4):
1. redact() — scrub secrets from any text before it is embedded/stored OR placed
   in an LLM prompt.
2. scan() — report secret-shaped matches as security findings.

Deterministic rules + a Shannon-entropy check for long opaque tokens. Not a
replacement for `gitleaks` (that runs too, in the sandbox) — this is the always-on
in-process guard.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

REDACTION = "«redacted:secret»"

_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key_id", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "aws_secret_access_key",
        re.compile(r"(?i)aws.{0,20}?(secret|key).{0,3}['\"]([0-9a-zA-Z/+]{40})['\"]"),
    ),
    ("github_pat", re.compile(r"gh[pousr]_[0-9A-Za-z]{36,}")),
    ("github_fine_grained", re.compile(r"github_pat_[0-9A-Za-z_]{60,}")),
    ("slack_token", re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}")),
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("openai_key", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}")),
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("stripe_key", re.compile(r"(?:sk|rk)_(?:live|test)_[0-9A-Za-z]{16,}")),
    (
        "private_key_block",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    ),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    (
        "generic_assignment",
        re.compile(
            r"(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)\b"
            r"\s*[:=]\s*['\"]([^'\"\s]{8,})['\"]"
        ),
    ),
    ("connection_string_pw", re.compile(r"(?i)://[^:\s/]+:([^@\s/]{6,})@")),
]

_ENTROPY_CANDIDATE = re.compile(r"['\"]([A-Za-z0-9+/_\-]{32,})['\"]")


@dataclass(slots=True)
class SecretHit:
    rule_id: str
    line: int
    preview: str  # already masked


def _shannon(s: str) -> float:
    if not s:
        return 0.0
    counts: dict[str, int] = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:3]}…{value[-2:]} ({len(value)} chars)"


def scan(text: str) -> list[SecretHit]:
    hits: list[SecretHit] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for rule_id, pattern in _RULES:
            for m in pattern.finditer(line):
                captured = m.group(m.lastindex) if m.lastindex else m.group(0)
                hits.append(SecretHit(rule_id, lineno, _mask(captured)))
        for m in _ENTROPY_CANDIDATE.finditer(line):
            token = m.group(1)
            if _shannon(token) >= 4.0 and not token.isalpha():
                hits.append(SecretHit("high_entropy_string", lineno, _mask(token)))
    return hits


def redact(text: str) -> str:
    redacted = text
    for _rule_id, pattern in _RULES:

        def _sub(m: re.Match[str]) -> str:
            if m.lastindex:
                full = m.group(0)
                return full.replace(m.group(m.lastindex), REDACTION)
            return REDACTION

        redacted = pattern.sub(_sub, redacted)

    def _entropy_sub(m: re.Match[str]) -> str:
        token = m.group(1)
        if _shannon(token) >= 4.0 and not token.isalpha():
            return m.group(0).replace(token, REDACTION)
        return m.group(0)

    return _ENTROPY_CANDIDATE.sub(_entropy_sub, redacted)


def contains_secret(text: str) -> bool:
    return bool(scan(text))
