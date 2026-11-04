"""Subject + context for the daily health report email."""

from typing import Any, Dict

from app.managers.health_check_manager import HealthReport

SUBJECT_PREFIX = "Cause List Checker health"


def build_health_subject(report: HealthReport) -> str:
    total, failed, warnings = (
        len(report.checks),
        len(report.failed),
        len(report.warnings),
    )
    date = report.generated_at[:10]
    if failed:
        return f"❌ {SUBJECT_PREFIX}: {failed} of {total} checks failed ({date})"
    if warnings:
        return f"⚠️ {SUBJECT_PREFIX}: OK with {warnings} warning(s) ({date})"
    return f"✅ {SUBJECT_PREFIX}: all {total} checks OK ({date})"


def build_health_email(report: HealthReport) -> Dict[str, Any]:
    """Return {"subject": ..., "context": ...} for healthcheck_template.html."""
    return {"subject": build_health_subject(report), "context": {"report": report}}
