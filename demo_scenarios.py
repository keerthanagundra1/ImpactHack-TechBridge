"""Seeded demo scenarios: one ready-made example of each case, so a demo can start anywhere in the flow.

All records are labeled demo data. A scenario only changes a demo volunteer who is still in their
original seeded state, so anything already clicked through in a workspace is left alone.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from onboarding import APPROVED, DEMO_SENT, REJECTED, SUPERVISED, new_demo, new_onboarding
from skill_checks import expected_answers, grade_practice_task
from tech_bridge import HANDOFF_CHECKLIST, compose_invitation

# (id, what it shows, who, where to look)
SCENARIOS = [
    ("rejected", "Demo not approved: feedback sent, can reapply in 30 days", "Tyler Robinson", "Volunteers → Roster · Volunteer view → Mailbox"),
    ("expired", "Demo deadline passed: resend it", "Mia Thompson", "Volunteers → Roster (Resend demo project)"),
    ("approved", "Demo approved: waiting for the confidentiality agreement", "Harper Davis", "Volunteer view → My nonprofits"),
    ("offer", "Project offer waiting for the volunteer's reply", "Zara Hussain", "Matchboard · Volunteers → Project offers · Volunteer view → Mailbox"),
    ("supervised", "Supervised work waiting for Mentor approval", "Hannah Okafor", "Matchboard (Needs my action)"),
    ("review", "Changes requested, resubmitted, ready for review", "Daniel Okoye", "Matchboard · Volunteer view → Mailbox"),
    ("star", "Done, waiting for a star: one star from Trusted (2 of 3)", "Caleb Brooks", "Matchboard → Give a star"),
    ("personal", "Personal-data project: only Trusted volunteers are matched", "Donor tracker", "Matchboard (Open)"),
]


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def _fresh(student: dict[str, Any] | None) -> bool:
    """A demo volunteer still in their original seeded state (Supervised, no demo, no extra tasks)."""
    if not student or not student.get("demo_student"):
        return False
    onboarding = student.get("onboarding") or {}
    return (onboarding.get("status") == SUPERVISED and not onboarding.get("demo")
            and not onboarding.get("seed_reviewed_tasks") and bool(onboarding.get("demo_record")))


def _project(scenario: str, organization: str, now: datetime, **fields: Any) -> dict[str, Any]:
    return {
        "id": f"scenario-{scenario}", "organization": organization, "tech_comfort": "Basic", "difficulty": "Beginner",
        "why_this_solution": "Demo scenario.", "advanced_alternative": "", "tools": ["Google Sheets"], "library_consent": False,
        "status": "Open", "assigned_student_id": None, "handoff_guide": "", "data_mode": "Sample data",
        "created_at": _iso(now - timedelta(days=4)), "demo_project": True, "demo_scenario": scenario,
        "hours_wasted_per_week": 2, "build_effort_hours": fields.get("effort_hours", 1), **fields,
    }


def _accept(project: dict[str, Any], volunteer: dict[str, Any], base_url: str, sent: datetime) -> dict[str, Any]:
    invitation = compose_invitation(project, volunteer, base_url)
    invitation.update({"sent_at": _iso(sent), "delivery": "Demo inbox only (demo address)", "status": "Accepted",
                       "responded_at": _iso(sent + timedelta(hours=3))})
    project.setdefault("invitations", []).append(invitation)
    project.update({"assigned_student_id": volunteer["id"], "status": "In progress"})
    return invitation


def apply_scenarios(organization: str, students: list[dict[str, Any]], projects: list[dict[str, Any]], base_url: str) -> list[str]:
    """Add the demo scenarios to one workspace. Returns the scenario ids that were added."""
    if not any(student.get("demo_student") for student in students):
        return []  # Only workspaces with the seeded demo roster get demo scenarios.
    now = datetime.now(timezone.utc)
    people = {student.get("name"): student for student in students}
    existing = {project.get("id") for project in projects}
    added = []

    tyler = people.get("Tyler Robinson")
    if _fresh(tyler):
        demo = new_demo("Web design (HTML/CSS)", sent_at=now - timedelta(days=5))
        answers = ["src", "div"]
        demo.update({"answers": answers, "submitted_at": _iso(now - timedelta(days=4)), "auto_check": grade_practice_task("Web design (HTML/CSS)", answers)})
        tyler["onboarding"] = new_onboarding(REJECTED, demo=demo, demo_record=True, applied_at=_iso(now - timedelta(days=6)), review={
            "decision": "Rejected", "reviewed_by": "NGO staff", "reviewed_at": _iso(now - timedelta(days=3)),
            "feedback": "Thanks for trying! Look up the alt attribute and the <nav> element, then apply again.",
        })
        tyler["confidentiality_signed"] = False
        added.append("rejected")

    mia = people.get("Mia Thompson")
    if _fresh(mia):
        mia["onboarding"] = new_onboarding(DEMO_SENT, demo=new_demo("Canva/Graphics", sent_at=now - timedelta(days=10)),
                                           demo_record=True, applied_at=_iso(now - timedelta(days=11)))
        mia["confidentiality_signed"] = False
        added.append("expired")

    harper = people.get("Harper Davis")
    if _fresh(harper):
        demo = new_demo("Canva/Graphics", sent_at=now - timedelta(days=3))
        answers = expected_answers("Canva/Graphics")
        demo.update({"answers": answers, "submitted_at": _iso(now - timedelta(days=2)), "auto_check": grade_practice_task("Canva/Graphics", answers)})
        harper["onboarding"] = new_onboarding(APPROVED, demo=demo, demo_record=True, applied_at=_iso(now - timedelta(days=4)), review={
            "decision": "Approved", "reviewed_by": "Amina Yusuf", "reviewed_at": _iso(now - timedelta(days=1)),
            "feedback": "Great checklist - you caught the date and the QR code.",
        })
        harper["confidentiality_signed"] = False
        added.append("approved")

    zara = people.get("Zara Hussain")
    if _fresh(zara) and "scenario-offer" not in existing:
        project = _project("offer", organization, now, mission_area="Food", problem_type="Weekly pantry numbers dashboard",
                           problem_summary="Staff count visits by hand every Monday to report to funders.",
                           suggested_solution="A Power BI dashboard over the sample visit log, refreshed weekly.",
                           skills=["Power BI/Tableau"], tools=["Power BI"], effort_hours=10, build_effort_hours=10,
                           data_sensitivity="Non-sensitive data", reuse_template_id=None,
                           deliverables=["Agree on 3 numbers", "Build the dashboard", "Show staff how to refresh it"],
                           privacy_notes="Counts only; no names.")
        invitation = compose_invitation(project, zara, base_url)
        invitation.update({"sent_at": _iso(now - timedelta(hours=20)), "delivery": "Demo inbox only (demo address)"})
        project.update({"invitations": [invitation], "status": "Offered"})
        projects.insert(0, project)
        added.append("offer")

    hannah = people.get("Hannah Okafor")
    if _fresh(hannah) and "scenario-supervised" not in existing:
        project = _project("supervised", organization, now, mission_area="Education", problem_type="Event flyer templates",
                           problem_summary="Every event flyer is designed from scratch the night before.",
                           suggested_solution="A Canva brand kit with three editable flyer templates.",
                           skills=["Canva/Graphics"], tools=["Canva (free for nonprofits)"], effort_hours=6, build_effort_hours=6,
                           data_sensitivity="Non-sensitive data", reuse_template_id=None,
                           deliverables=["Collect logo and colors", "Build 3 templates", "Show staff how to edit them"],
                           privacy_notes="Only use photos with consent.")
        _accept(project, hannah, base_url, now - timedelta(days=3))
        projects.insert(0, project)
        added.append("supervised")

    daniel = people.get("Daniel Okoye")
    if _fresh(daniel) and "scenario-review" not in existing:
        project = _project("review", organization, now, mission_area="Environment", problem_type="Volunteer shift reminders setup",
                           problem_summary="Volunteers forget Saturday cleanup shifts.",
                           suggested_solution="Customize the library's shift sign-up sheet with automatic reminders.",
                           skills=["Google Sheets/Excel", "Apps Script"], effort_hours=1, build_effort_hours=6,
                           reuse_template_id="tpl-volunteer-scheduling", data_sensitivity="Sample data only",
                           deliverables=["Copy the shift sheet", "Turn on reminders", "Test with sample data"],
                           privacy_notes="Sample data while building.")
        _accept(project, daniel, base_url, now - timedelta(days=4))
        project["change_requests"] = [{"comment": "Please send reminders two days before, not one.", "requested_at": _iso(now - timedelta(days=2))}]
        project["completion"] = {
            "links": ["https://docs.google.com/spreadsheets/d/demo-shift-sheet"], "summary": "Shift sign-up sheet with reminders two days before each shift.",
            "how_to_use": "Add shifts in the Shifts tab; reminders go out automatically.", "notes": "", "checklist": list(HANDOFF_CHECKLIST),
            "submitted_by": daniel["name"], "submitted_at": _iso(now - timedelta(days=1)),
        }
        project["status"] = "Ready for review"
        projects.insert(0, project)
        added.append("review")

    caleb = people.get("Caleb Brooks")
    if _fresh(caleb) and "scenario-star" not in existing:
        caleb["onboarding"]["seed_reviewed_tasks"] = 2
        project = _project("star", organization, now, mission_area="Food", problem_type="Volunteer Sign-up Sheet setup",
                           problem_summary="Three volunteer spreadsheets are merged by hand every Friday.",
                           suggested_solution="Customize the library's Volunteer Sign-up Sheet.",
                           skills=["Google Sheets/Excel"], effort_hours=1, build_effort_hours=8, hours_wasted_per_week=3,
                           reuse_template_id="tpl-volunteer-intake", data_sensitivity="Sample data only",
                           deliverables=["Copy the sheet", "Load sample data", "Walk staff through it"], privacy_notes="Sample data while building.")
        _accept(project, caleb, base_url, now - timedelta(days=6))
        project.update({
            "status": "Done", "mentor_approval": {"approved_by": "Amina Yusuf", "role": "Mentor", "approved_at": _iso(now - timedelta(days=1)), "demo": True},
            "completion": {"links": ["https://docs.google.com/spreadsheets/d/demo-signup"], "summary": "One sign-up sheet with duplicate checks.",
                           "how_to_use": "Open it on Fridays.", "notes": "", "checklist": list(HANDOFF_CHECKLIST),
                           "submitted_by": caleb["name"], "submitted_at": _iso(now - timedelta(days=2))},
            "handoff_guide": "## Demo handoff\n\nOpen the sign-up sheet every Friday. Test changes with sample data.",
        })
        projects.insert(0, project)
        added.append("star")

    if "scenario-personal" not in existing:
        projects.insert(0, _project(
            "personal", organization, now, mission_area="Women and families", problem_type="Donor thank-you tracker",
            problem_summary="Thank-you notes to donors are tracked in a paper notebook.",
            suggested_solution="Customize the library's private donor list with thank-you drafts.",
            skills=["Airtable/No-code", "Zapier/Make automation"], tools=["Airtable"], effort_hours=1, build_effort_hours=6,
            reuse_template_id="tpl-donor-thanks", data_sensitivity="Personal data",
            deliverables=["Restrict access", "Set up the donor list", "Draft thank-you messages"],
            privacy_notes="Donor names and gifts are personal data. Restrict access to authorized staff.",
        ))
        added.append("personal")
    return added
