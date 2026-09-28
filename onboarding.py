"""NGO-led volunteer onboarding and the assignment gate.

Status path, per nonprofit (each nonprofit onboards its own volunteers on its private roster):
    Applicant -> Demo sent -> Demo submitted -> Approved / Rejected -> Supervised -> Trusted

Onboarding status is the only gate for real work. Supervised and Trusted volunteers can take
normal projects; personal data needs Trusted; vulnerable people also need a background check.
The per-skill proof ladder is shown as labels and weights the match score, but never gates.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from skill_checks import PRACTICE_TASKS, expected_answers, grade_practice_task
from volunteer_retention import (
    PERSONAL_DATA,
    VULNERABLE_PEOPLE,
    _join_words,
    badge_label,
    project_data_sensitivity,
    project_work_type,
    proof_label,
    skill_level,
)

APPLICANT, DEMO_SENT, DEMO_SUBMITTED = "Applicant", "Demo sent", "Demo submitted"
APPROVED, REJECTED, SUPERVISED, TRUSTED = "Approved", "Rejected", "Supervised", "Trusted"
STATUS_PATH = [APPLICANT, DEMO_SENT, "Approved / Rejected", SUPERVISED, TRUSTED]
STATUS_STEP = {APPLICANT: 0, DEMO_SENT: 1, DEMO_SUBMITTED: 1, APPROVED: 2, REJECTED: 2, SUPERVISED: 3, TRUSTED: 4}
TRUSTED_TASKS = 3
DEMO_DEADLINE_DAYS = 7
REAPPLY_DAYS = 30
NGO_STAFF = "NGO staff"

BLOCK_REASONS = {
    APPLICANT: "Still an applicant - send a demo project first",
    DEMO_SENT: "Demo project not submitted yet",
    DEMO_SUBMITTED: "Demo project is waiting for mentor review",
    APPROVED: "Must accept the confidentiality agreement first",
    REJECTED: "Demo project was not approved",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_onboarding(status: str = APPLICANT, **extra: Any) -> dict[str, Any]:
    return {"status": status, "demo": None, "review": None, "confidentiality_accepted_at": None,
            "seed_reviewed_tasks": 0, "mentor": False, **extra}


def new_demo(skill: str, deadline_days: int = DEMO_DEADLINE_DAYS, sent_at: datetime | None = None) -> dict[str, Any]:
    sent = sent_at or _now()
    return {
        "skill": skill, "title": PRACTICE_TASKS[skill]["title"], "sent_at": sent.isoformat(timespec="seconds"),
        "deadline": (sent + timedelta(days=deadline_days)).isoformat(timespec="seconds"),
        "answers": None, "submitted_at": None, "auto_check": None,
    }


def suggested_demo_skill(volunteer: dict[str, Any]) -> str:
    """The demo task suggested for a volunteer: their first listed skill that has a task."""
    return next((skill for skill in volunteer.get("skills", []) if skill in PRACTICE_TASKS), next(iter(PRACTICE_TASKS)))


def demo_overdue(demo: dict[str, Any] | None) -> bool:
    return bool(demo) and not demo.get("submitted_at") and _now() > datetime.fromisoformat(demo["deadline"])


def reapply_after(onboarding: dict[str, Any]) -> datetime | None:
    """For a rejected volunteer, when they may apply again (None if they can now)."""
    review = onboarding.get("review") or {}
    if onboarding.get("status") != REJECTED or not review.get("reviewed_at"):
        return None
    when = datetime.fromisoformat(review["reviewed_at"]) + timedelta(days=REAPPLY_DAYS)
    return when if when > _now() else None


# ---------------------------------------------------------------- status


def counts_toward_trusted(project: dict[str, Any], student_id: str) -> bool:
    """A reviewed task: done, mentor-approved, and starred by the nonprofit."""
    return (
        project.get("assigned_student_id") == student_id and project.get("status") == "Done"
        and bool(project.get("mentor_approval")) and bool(project.get("thanks", {}).get("star"))
    )


def reviewed_task_count(volunteer: dict[str, Any], projects: list[dict[str, Any]] | None = None) -> int:
    onboarding = volunteer.get("onboarding") or {}
    counted = sum(1 for project in projects or [] if counts_toward_trusted(project, volunteer.get("id")))
    return int(onboarding.get("seed_reviewed_tasks", 0) or 0) + counted


def volunteer_status(volunteer: dict[str, Any], projects: list[dict[str, Any]] | None = None) -> str:
    """Stored stage, except Supervised becomes Trusted automatically after 3 reviewed, starred tasks."""
    if projects is None and volunteer.get("onboarding_status"):
        return volunteer["onboarding_status"]
    stored = (volunteer.get("onboarding") or {}).get("status", APPLICANT)
    if stored == SUPERVISED and reviewed_task_count(volunteer, projects) >= TRUSTED_TASKS:
        return TRUSTED
    return stored


def annotate_onboarding(students: list[dict[str, Any]], projects: list[dict[str, Any]]) -> None:
    for student in students:
        student["reviewed_tasks"] = reviewed_task_count(student, projects)
        student.pop("onboarding_status", None)
        student["onboarding_status"] = volunteer_status(student, projects)


def is_mentor(volunteer: dict[str, Any]) -> bool:
    return bool((volunteer.get("onboarding") or {}).get("mentor")) and volunteer_status(volunteer) == TRUSTED


def mentor_review_required(volunteer: dict[str, Any] | None) -> bool:
    """Supervised volunteers need 'Mentor approved' before Done; for Trusted volunteers it's optional."""
    return volunteer is None or volunteer_status(volunteer) != TRUSTED


def progress_text(volunteer: dict[str, Any]) -> str:
    done = min(int(volunteer.get("reviewed_tasks", reviewed_task_count(volunteer)) or 0), TRUSTED_TASKS)
    return f"{done} of {TRUSTED_TASKS} reviewed tasks completed"


# ---------------------------------------------------------------- assignment gate


def assignment_check(volunteer: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    """Whether a volunteer may take a real project at this nonprofit: ok, blocking reason, and a 'why' line."""
    status = volunteer_status(volunteer)
    sensitivity = project_data_sensitivity(project)
    required = list(dict.fromkeys(project.get("skills", [])))
    reasons = []
    if volunteer.get("paused"):
        reasons.append("Paused - taking a break")
    if status not in (SUPERVISED, TRUSTED):
        reasons.append(BLOCK_REASONS.get(status, "Not approved yet"))
    elif not volunteer.get("confidentiality_signed", False):
        reasons.append(BLOCK_REASONS[APPROVED])
    missing = [skill for skill in required if skill_level(volunteer, skill) == 0]
    if required and len(missing) * 2 > len(required):
        reasons.append(f"Doesn't list {_join_words([badge_label(skill) for skill in missing])}")
    if sensitivity in (PERSONAL_DATA, VULNERABLE_PEOPLE) and status == SUPERVISED:
        reasons.append(f"{sensitivity} needs a Trusted volunteer ({progress_text(volunteer)})")
    if sensitivity == VULNERABLE_PEOPLE and not volunteer.get("background_check_cleared"):
        reasons.append("Needs a background check cleared by the coordinator")
    if reasons:
        return {"ok": False, "reason": " · ".join(reasons), "why": ""}
    rule = sensitivity if sensitivity in (PERSONAL_DATA, VULNERABLE_PEOPLE) else project_work_type(project)
    listed = [skill for skill in required if skill not in missing]
    skills = ", ".join(f"{badge_label(skill)} ({proof_label(volunteer, skill)})" for skill in listed) or "open to all skills"
    role = f"{status}{' · Mentor' if is_mentor(volunteer) else ''}"
    return {"ok": True, "reason": "", "why": f"{role} · {rule}: {skills}"}


def real_data_check(project: dict[str, Any], volunteer: dict[str, Any] | None) -> tuple[bool, str]:
    """Projects start in Sample data mode. Real data only with a Trusted volunteer who meets the project's rule."""
    if volunteer is None:
        return False, "No volunteer assigned"
    if volunteer_status(volunteer) != TRUSTED:
        return False, f"Real data needs a Trusted volunteer ({progress_text(volunteer)})"
    if not volunteer.get("confidentiality_signed", False):
        return False, BLOCK_REASONS[APPROVED]
    if project_data_sensitivity(project) == VULNERABLE_PEOPLE and not volunteer.get("background_check_cleared"):
        return False, "Needs a background check cleared by the coordinator"
    return True, ""


# ---------------------------------------------------------------- demo data (labeled)

SHEETS = "Google Sheets/Excel"


def seed_onboarding(name: str) -> dict[str, Any]:
    """Seeded roster volunteers were onboarded earlier (Supervised), except the showcase volunteers below."""
    now = _now()
    supervised = {"confidentiality_accepted_at": "2026-02-01T18:00:00+00:00", "demo_record": True}
    if name in {"Priya Shah", "Marcus Johnson", "Lucas Ferreira"}:
        return new_onboarding(SUPERVISED, seed_reviewed_tasks=3, **supervised)
    if name == "Amina Yusuf":
        return new_onboarding(SUPERVISED, seed_reviewed_tasks=3, mentor=True, **supervised)
    if name == "Noah Patel":
        return new_onboarding(SUPERVISED, seed_reviewed_tasks=1, **supervised)
    if name == "Alex Rivera":
        demo = new_demo(SHEETS, sent_at=now - timedelta(days=2))
        answers = expected_answers(SHEETS)
        demo.update({"answers": answers, "submitted_at": (now - timedelta(days=1)).isoformat(timespec="seconds"),
                     "auto_check": grade_practice_task(SHEETS, answers)})
        return new_onboarding(DEMO_SUBMITTED, demo=demo, demo_record=True, applied_at=(now - timedelta(days=3)).isoformat(timespec="seconds"))
    if name == "Jordan Ellis":
        return new_onboarding(DEMO_SENT, demo=new_demo(SHEETS, sent_at=now), demo_record=True,
                              applied_at=(now - timedelta(days=1)).isoformat(timespec="seconds"))
    return new_onboarding(SUPERVISED, **supervised)


SEED_APPLICATION = {
    "name": "Taylor Nguyen", "email": "taylor.nguyen@example.org", "phone": "555-0100",
    "skills": ["Canva/Graphics", "WordPress/Squarespace/Wix"], "hours_per_week": 4,
    "causes": ["Animals", "Education"], "note": "I design flyers for my student club and would love to help with outreach.",
    "show_name_consent": True, "display_name_choice": "initial", "nickname": "", "demo": True,
}
