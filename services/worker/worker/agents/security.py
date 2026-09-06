"""Security step: deterministic scanners (sandbox) + AI review over the diff.

AI findings never suppress or override deterministic ones.
"""

from __future__ import annotations

from worker.codeintel.secrets import scan as secret_scan
from worker.llm.base import LLMMessage
from worker.runtime.context import RunContext
from worker.runtime.schemas import SecurityReview
from worker.runtime.toolset import Toolset

_SEVERITY_MAP = {"LOW": "low", "MEDIUM": "medium", "HIGH": "high", "CRITICAL": "critical"}


def _bandit_findings(report: dict) -> list[dict]:
    out = []
    for r in (report or {}).get("results", []):
        out.append(
            {
                "source": "bandit",
                "severity": _SEVERITY_MAP.get(r.get("issue_severity", "LOW"), "low"),
                "rule_id": r.get("test_id"),
                "path": r.get("filename"),
                "line": r.get("line_number"),
                "message": r.get("issue_text", "")[:500],
                "deterministic": True,
            }
        )
    return out


def _pip_audit_findings(report) -> list[dict]:  # noqa: ANN001
    out = []
    deps = report if isinstance(report, list) else (report or {}).get("dependencies", [])
    for dep in deps or []:
        for vuln in dep.get("vulns", []) or []:
            out.append(
                {
                    "source": "pip_audit",
                    "severity": "high",
                    "rule_id": vuln.get("id"),
                    "path": None,
                    "line": None,
                    "message": f"{dep.get('name')} {dep.get('version')}: {vuln.get('description','')[:300]}",
                    "deterministic": True,
                }
            )
    return out


async def review_security(ctx: RunContext, diff: str, toolset: Toolset) -> list[dict]:
    findings: list[dict] = []

    # 1. Always-on in-process secret scan of the diff (added lines).
    added = "\n".join(
        ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")
    )
    for hit in secret_scan(added):
        findings.append(
            {
                "source": "detect_secrets",
                "severity": "high",
                "rule_id": hit.rule_id,
                "path": None,
                "line": hit.line,
                "message": f"secret-shaped value added ({hit.preview})",
                "deterministic": True,
            }
        )

    # 2. Deterministic scanners in the sandbox.
    scan_tool = toolset.registry
    if scan_tool.has("run_security_scan"):
        res = scan_tool.invoke("run_security_scan", {"tools": ["bandit", "pip_audit"]})
        if res.ok:
            scans = res.data.get("scans", {})
            findings += _bandit_findings(scans.get("bandit", {}).get("report", {}))
            findings += _pip_audit_findings(scans.get("pip_audit", {}).get("report", {}))

    # 3. AI review over the diff (advisory, additive).
    if diff.strip():
        ai = await ctx.structured(
            "security",
            [LLMMessage(role="user", content=f"# Diff under review\n{diff[:16000]}")],
            SecurityReview,
            purpose="security",
        )
        for issue in ai.issues:
            findings.append(
                {
                    "source": "ai_review",
                    "severity": issue.severity,
                    "rule_id": None,
                    "path": issue.path,
                    "line": issue.line,
                    "message": f"{issue.message} — fix: {issue.fix}",
                    "deterministic": False,
                }
            )

    return findings
