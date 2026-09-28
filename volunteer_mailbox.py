"""The volunteer's mailbox: every email Tech Bridge would send them, and how each reply works.

No real email is sent in the demo. Onboarding and notification emails never name a nonprofit;
project offers and change requests come from the nonprofit that sent them (the volunteer's own work).
"""

from __future__ import annotations

from typing import Any

from onboarding import APPROVED, DEMO_SENT, REAPPLY_DAYS, demo_overdue
from skill_checks import PRACTICE_TASKS
from volunteer_retention import notification_email

MAIL_ICONS = {
    "invite": "📩", "changes": "✏️", "nudge": "👋", "added": "🙌", "demo": "🧪", "demo_approved": "✅",
    "demo_rejected": "💬", "welcome": "🤝", "star": "⭐", "reuse": "🔁", "trusted": "🛡️", "mentor": "🎓",
}

# type -> (how the volunteer replies, what happens next)
REPLY_GUIDE: dict[str, tuple[str, str]] = {
    "invite": (
        "Accept or Decline",
        "Accept: the project is theirs and moves to In progress, and their private project page opens. "
        "Decline: the card goes to the next best match, or back to Open if nobody is left. "
        "No reply: it stays pending, and the nonprofit can record the reply on the Matchboard.",
    ),
    "nudge": (
        "Accept or Not now",
        "Accept: if the project is still open, they get the project card; if someone already has it, the nonprofit sees they're interested. "
        "Not now: nothing changes. Nudges are limited to one a week, and paused volunteers get none.",
    ),
    "added": ("No reply needed", "Next, the nonprofit sends a short demo project."),
    "demo": (
        "Submit the demo on their private link",
        "Submitted before the deadline: it goes to Volunteers → Demo reviews for a mentor. "
        "No reply by the deadline: it expires, and the nonprofit can send a new one from the roster.",
    ),
    "demo_approved": (
        "Accept the confidentiality agreement on their private link",
        "Accepting makes them Supervised: they can be matched to real tasks, and a mentor reviews their first three. "
        "Until they accept, they aren't matched.",
    ),
    "demo_rejected": ("No reply needed", f"They see the mentor's feedback and can reapply through the nonprofit's form after {REAPPLY_DAYS} days."),
    "welcome": ("No reply needed", "Project offers can now arrive. Each task needs Mentor approval before it's marked done."),
    "changes": (
        "Update the work and resubmit the handoff on their project page",
        "Resubmitting moves the project back to Ready for review, and the mentor reviews it again.",
    ),
    "star": ("No reply needed", "The star adds a verified badge for each skill on the project; the thank-you note shows on their private page."),
    "reuse": ("No reply needed", "The reuse count and staff hours saved update on their private page."),
    "trusted": ("No reply needed", "Mentor review becomes optional, and they can take personal-data projects at that nonprofit."),
    "mentor": ("No reply needed", "They can now review demo projects and approve Supervised volunteers' work for that nonprofit."),
}

# Onboarding emails are built from the roster record, so these stored notification types are skipped.
DERIVED_TYPES = {"demo", "onboarding", "demo_approved", "demo_rejected", "added", "welcome", "trusted", "mentor"}


def _mail(kind: str, *, subject: str, body: str, summary: str, created_at: str, status: str = "", needs_reply: bool = False,
          demo: bool = False, **extra: Any) -> dict[str, Any]:
    return {"type": kind, "subject": subject, "body": body, "summary": summary, "created_at": created_at or "",
            "status": status, "needs_reply": needs_reply, "demo": demo, **extra}


def onboarding_mails(student: dict[str, Any], organization_id: str, profile: dict[str, Any], base_url: str) -> list[dict[str, Any]]:
    """The onboarding emails this volunteer got from one nonprofit, rebuilt from its roster record."""
    onboarding = student.get("onboarding") or {}
    demo = onboarding.get("demo") or {}
    review = onboarding.get("review") or {}
    status = onboarding.get("status")
    context = {"organization_id": organization_id, "student_id": student.get("id"), "demo": bool(onboarding.get("demo_record"))}
    mails = []

    def add(kind: str, message: str, created_at: str | None, extra: str = "", **fields: Any) -> None:
        if not created_at:
            return
        subject, body = notification_email(profile, kind, message, base_url, extra)
        mails.append(_mail(kind, subject=subject, body=body, summary=message, created_at=created_at,
                           id=f"{kind}-{organization_id}-{student.get('id')}-{created_at}", **context, **fields))

    add("added", "A nonprofit added you to its volunteer roster. Next up: a short demo project.", onboarding.get("applied_at"))
    if demo:
        waiting = status == DEMO_SENT and not demo.get("submitted_at")
        demo_status = ("Expired" if demo_overdue(demo) else "Waiting for the demo") if waiting else f"Submitted {str(demo.get('submitted_at', ''))[:10]}"
        minutes = PRACTICE_TASKS.get(demo.get("skill"), {}).get("minutes", 10)
        add("demo", "A nonprofit sent you a short demo project. It uses fake sample data only.", demo.get("sent_at"),
            f"Demo project: {demo.get('title', '')} (about {minutes} minutes)\nDue: {str(demo.get('deadline', ''))[:10]}",
            status=demo_status, needs_reply=waiting and not demo_overdue(demo))
    if review.get("decision") == "Approved":
        waiting = status == APPROVED
        add("demo_approved", "Your demo project was approved! Accept the confidentiality agreement on your private page to start real tasks.",
            review.get("reviewed_at"), f"Feedback: {review['feedback']}" if review.get("feedback") else "",
            status="Waiting for the agreement" if waiting else "Agreement accepted", needs_reply=waiting)
    elif review.get("decision") == "Rejected":
        add("demo_rejected", f"Thanks for your demo project. It isn't approved this time; you can apply again in {REAPPLY_DAYS} days.",
            review.get("reviewed_at"), f"Feedback: {review.get('feedback', '')}")
    add("welcome", "You're all set! You can now be matched to real tasks. A mentor reviews your first 3.",
        onboarding.get("confidentiality_accepted_at"))
    add("trusted", "You're now Trusted at a nonprofit you volunteer with. Mentor review is optional for your work there.",
        onboarding.get("trusted_at"))
    add("mentor", "A nonprofit made you a Mentor. You can now review demo projects and newer volunteers' work there.",
        onboarding.get("mentor_at"))
    return mails


def mail_from_notification(notification: dict[str, Any]) -> dict[str, Any]:
    action = notification.get("action") or {}
    waiting = notification["type"] == "nudge" and not action.get("response")
    return _mail(
        notification["type"], subject=notification["email_subject"], body=notification["email_body"],
        summary=notification["message"], created_at=notification["created_at"],
        status=action.get("response") or ("Waiting for a reply" if notification["type"] == "nudge" else ""),
        needs_reply=waiting, demo=notification.get("demo", False), id=f"n-{notification['id']}",
        notification_id=notification["id"], organization_id=action.get("organization_id"), read=notification["read"],
    )


def mail_from_invitation(invitation: dict[str, Any], project: dict[str, Any], organization_id: str) -> dict[str, Any]:
    pending = invitation.get("status", "Pending") == "Pending"
    return _mail(
        "invite", subject=invitation["subject"], body=invitation["body"],
        summary=f"{project.get('organization', 'A nonprofit')} offered you a project: {project.get('problem_type', '')}",
        created_at=invitation.get("sent_at", ""), status=invitation.get("status", "Pending"), needs_reply=pending,
        demo=bool(project.get("demo_project")), id=f"i-{invitation['id']}", organization_id=organization_id,
        project_id=project["id"], student_id=invitation.get("student_id"), portal_link=invitation.get("portal_link", ""),
    )


def mail_from_change_request(change: dict[str, Any], subject: str, body: str, project: dict[str, Any],
                             organization_id: str, portal_link: str) -> dict[str, Any]:
    latest = change is (project.get("change_requests") or [None])[-1]
    waiting = latest and project.get("status") == "In progress"
    return _mail(
        "changes", subject=subject, body=body, summary=f"{project.get('organization', 'The nonprofit')} asked for changes: {change.get('comment', '')}",
        created_at=change.get("requested_at", ""), status="Waiting for the update" if waiting else "Resubmitted",
        needs_reply=waiting, demo=bool(project.get("demo_project")), id=f"c-{project['id']}-{change.get('requested_at', '')}",
        organization_id=organization_id, project_id=project["id"], portal_link=portal_link,
    )


def sort_mail(mails: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(mails, key=lambda mail: mail.get("created_at") or "", reverse=True)
