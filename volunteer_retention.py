"""Volunteer retention: impact, thanks, proof ladder labels, settings, and credit.

Privacy rule for everything here: shared views (library, public profiles, notifications,
email previews) show work, credit, and totals only. They never name the nonprofit a
volunteer worked for or the nonprofit that gave a star; other nonprofits are referred to
by mission type only (for example "an animal shelter").
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

# ---- proof ladder (per skill, per volunteer)
PROOF_LEVELS = {1: "Self-listed", 2: "Evidence", 3: "Skill check passed", 4: "Nonprofit-verified"}
PROOF_ICONS = {0: "·", 1: "📝", 2: "📎", 3: "✅", 4: "🏅"}
PROOF_WEIGHTS = {0: 0.0, 1: 0.2, 2: 0.4, 3: 0.6, 4: 1.0}
EVIDENCE_TYPES = ["Portfolio link", "Reference", "Certificate with verification link"]
REFERENCE_RELATIONSHIPS = ["Manager", "Professor", "Client", "Past nonprofit"]

# ---- project work type and data sensitivity
WORK_SETUP = "Setup of a proven fix"
WORK_NEW_BUILD = "New build"
SAMPLE_DATA, NON_SENSITIVE, PERSONAL_DATA, VULNERABLE_PEOPLE = (
    "Sample data only", "Non-sensitive data", "Personal data", "Vulnerable people",
)
DATA_SENSITIVITY = [SAMPLE_DATA, NON_SENSITIVE, PERSONAL_DATA, VULNERABLE_PEOPLE]
DATA_MODES = ["Sample data", "Real data"]
_VULNERABLE = re.compile(
    r"\b(child|children|kids|minors?|youth|teens?|survivors?|domestic violence|abuse|refugees?|elderly|seniors?|vulnerable)\b",
    re.IGNORECASE,
)
_PERSONAL_DATA = re.compile(
    r"\b(personal data|phone numbers?|contact (?:data|details|info\w*)|donors?|clients?|patients?|health|medical"
    r"|learners?|adopters?|fosters?|addresses)\b",
    re.IGNORECASE,
)

REUSE_TARGET_HOURS = 1
NEW_BUILD_MAX_HOURS = 25
NUDGE_INTERVAL_DAYS = 7
MILESTONE_THRESHOLDS = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]

DISPLAY_NAME_CHOICES = {
    "full": "Full name",
    "initial": "First name + last initial",
    "nickname": "Nickname",
}
ANONYMOUS_CREDIT = "a Tech Bridge volunteer"

MISSION_PHRASES = {
    "Food": "a food pantry",
    "Education": "an education nonprofit",
    "Animals": "an animal shelter",
    "Women and families": "a family support nonprofit",
    "Health": "a community health nonprofit",
    "Environment": "an environmental group",
    "Other": "a nonprofit",
}

# Fields copied from a volunteer's global profile onto each workspace roster entry so matching sees them.
MATCHING_PROFILE_KEYS = (
    "stars", "badges", "skill_levels", "identity_verified", "background_check_cleared",
    "paused", "causes", "hours_per_week", "skills",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def mission_phrase(mission: str | None) -> str:
    return MISSION_PHRASES.get(mission or "Other", MISSION_PHRASES["Other"])


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    return f"{count} {singular if count == 1 else (plural_form or singular + 's')}"


# ---------------------------------------------------------------- proof ladder


def skill_level(volunteer: dict[str, Any], skill: str) -> int:
    """Highest proof for one skill: 1 self-listed, 2 evidence, 3 skill check, 4 nonprofit star badge."""
    level = 1 if skill in volunteer.get("skills", []) else 0
    level = max(level, int(volunteer.get("skill_levels", {}).get(skill, 0) or 0))
    if int(volunteer.get("badges", {}).get(skill, 0) or 0) > 0:
        level = 4
    return level


def proof_label(volunteer: dict[str, Any], skill: str) -> str:
    level = skill_level(volunteer, skill)
    if level == 4:
        return f"Nonprofit-verified x{int(volunteer.get('badges', {}).get(skill, 0))}"
    return PROOF_LEVELS.get(level, "Not listed")


def skill_proof_lines(volunteer: dict[str, Any]) -> list[dict[str, Any]]:
    """Skills sorted strongest proof first: Nonprofit-verified > Skill check passed > Evidence > Self-listed."""
    skills = set(volunteer.get("skills", [])) | set(volunteer.get("skill_levels", {})) | {
        skill for skill, count in volunteer.get("badges", {}).items() if count
    }
    lines = []
    for skill in skills:
        level = skill_level(volunteer, skill)
        if level:
            lines.append({
                "skill": skill, "level": level, "label": proof_label(volunteer, skill), "icon": PROOF_ICONS[level],
                "count": int(volunteer.get("badges", {}).get(skill, 0) or 0),
            })
    return sorted(lines, key=lambda line: (-line["level"], -line["count"], line["skill"]))


def format_skill_proofs(volunteer: dict[str, Any]) -> str:
    return " · ".join(f"{line['icon']} {badge_label(line['skill'])} - {line['label']}" for line in skill_proof_lines(volunteer))


# ---------------------------------------------------------------- project work type and data


def project_work_type(project: dict[str, Any]) -> str:
    return WORK_SETUP if project.get("reuse_template_id") else WORK_NEW_BUILD


def project_data_sensitivity(project: dict[str, Any]) -> str:
    explicit = project.get("data_sensitivity")
    if explicit in DATA_SENSITIVITY:
        return explicit
    notes = project.get("privacy_notes", "") or ""
    if _VULNERABLE.search(notes):
        return VULNERABLE_PEOPLE
    if _PERSONAL_DATA.search(notes):
        return PERSONAL_DATA
    if project.get("reuse_template_id"):
        return SAMPLE_DATA
    return NON_SENSITIVE


def skill_score(volunteer: dict[str, Any], project: dict[str, Any]) -> float:
    """Proof-weighted skill fit: Level 4 = 1.0, Level 3 = 0.6, Level 2 = 0.4, Level 1 = 0.2."""
    required = list(dict.fromkeys(project.get("skills", [])))
    if not required:
        return 1.0
    return sum(PROOF_WEIGHTS[skill_level(volunteer, skill)] for skill in required) / len(required)


def effort_warning(project: dict[str, Any]) -> str | None:
    effort = int(project.get("effort_hours", 0) or 0)
    if project.get("reuse_template_id"):
        if effort > REUSE_TARGET_HOURS + 1:
            return f"Reuse projects should take about {REUSE_TARGET_HOURS} hour to customize; this one is set to {effort} hours."
        return None
    if effort >= NEW_BUILD_MAX_HOURS:
        return f"New builds should stay under {NEW_BUILD_MAX_HOURS} volunteer hours; this one is {effort}. Consider splitting it into smaller projects."
    return None


# ---------------------------------------------------------------- names and credit


def display_name(profile: dict[str, Any]) -> str:
    name = (profile.get("name") or "").strip()
    choice = profile.get("display_name_choice", "initial")
    if choice == "nickname" and (profile.get("nickname") or "").strip():
        return profile["nickname"].strip()
    if choice == "full" and name:
        return name
    parts = name.split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[-1][0].upper()}."
    return name or ANONYMOUS_CREDIT


def public_credit_name(profile: dict[str, Any] | None) -> str:
    if not profile or not profile.get("show_name_consent", True):
        return ANONYMOUS_CREDIT
    return display_name(profile)


def builder_credit(template: dict[str, Any], profiles_by_id: dict[str, dict[str, Any]]) -> str:
    """'Built by ...' line for a library solution, honoring the builder's consent."""
    builder_id = template.get("builder_volunteer_id")
    if builder_id:
        return f"Built by {public_credit_name(profiles_by_id.get(builder_id))}"
    return f"Built by {template.get('built_by') or ANONYMOUS_CREDIT}"


def badge_label(skill: str) -> str:
    short = re.sub(r"\s*\(.*?\)\s*", " ", skill).strip()
    return short.split("/")[0].strip() or skill


def badge_lines(badges: dict[str, int]) -> list[str]:
    ordered = sorted(badges.items(), key=lambda item: (-int(item[1]), item[0]))
    return [f"{badge_label(skill)} - verified by a nonprofit (x{count})" for skill, count in ordered if count]


def _join_words(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


# ---------------------------------------------------------------- privacy scrubbing


_EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\w)(?:\+?1[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]\d{4}(?!\w)")


def _organization_name_variants(organization: str) -> list[str]:
    words = (organization or "").split()
    variants = {" ".join(words[:end]) for end in range(2, len(words) + 1)}
    if len(words) == 1:
        variants.add(words[0])
    return sorted((variant for variant in variants if len(variant) >= 3), key=len, reverse=True)


def scrub_organization(text: str, organization: str) -> str:
    """Remove a nonprofit's name (and its leading words) plus contact details from shared text."""
    for variant in _organization_name_variants(organization):
        text = re.sub(re.escape(variant), "our nonprofit", text, flags=re.IGNORECASE)
    text = _EMAIL.sub("[email removed]", text)
    return _PHONE.sub("[phone removed]", text).strip()


def fallback_thank_you_note(project: dict[str, Any], volunteer_first_name: str = "") -> str:
    greeting = f"Thank you, {volunteer_first_name}!" if volunteer_first_name else "Thank you!"
    hours = int(project.get("hours_wasted_per_week", 0) or 0)
    what = (project.get("problem_type") or "new workflow").lower()
    saving = f" It already saves our team about {hours} hours every week." if hours else ""
    return f"{greeting} The {what} you set up made a real difference.{saving} We're grateful for your time and care."


# ---------------------------------------------------------------- messages and email previews


def impact_link(token: str, base_url: str) -> str:
    return f"{base_url.rstrip('/')}/?{urlencode({'impact': token})}"


def template_total_staff_hours(template: dict[str, Any]) -> int:
    return int(template.get("origin_staff_hours_per_week", 0) or 0) + int(template.get("reuse_staff_hours_per_week", 0) or 0)


def reuse_message(template: dict[str, Any], mission: str | None) -> str:
    helped = 1 + int(template.get("reuse_count", 0) or 0)
    return (
        f"Your {template.get('title', 'solution')} just helped {mission_phrase(mission)}. "
        f"It has now helped {helped} nonprofits and saves them about {template_total_staff_hours(template)} staff hours every week."
    )


def star_message(skills: list[str]) -> str:
    labels = list(dict.fromkeys(badge_label(skill) for skill in skills))
    if not labels:
        return "A nonprofit gave you a star!"
    return f"A nonprofit gave you a star! You earned {_join_words(labels)} badges."


NUDGE_MESSAGE = "A new project matching your skills just came in. Interested?"

EMAIL_SUBJECTS = {
    "reuse": "Your work just helped another nonprofit",
    "star": "A nonprofit gave you a star",
    "nudge": "A new project matching your skills",
    "demo": "Your Tech Bridge demo project",
    "onboarding": "An update on your volunteer application",
    "added": "You're on a nonprofit's volunteer roster",
    "demo_approved": "Your demo project was approved",
    "demo_rejected": "Feedback on your demo project",
    "welcome": "You're ready for real tasks",
    "trusted": "You're now Trusted",
    "mentor": "You're now a Mentor",
}


def notification_email(
    profile: dict[str, Any],
    notification_type: str,
    message: str,
    base_url: str,
    extra: str = "",
) -> tuple[str, str]:
    """The email the volunteer would receive. Demo only: nothing is sent."""
    first_name = (profile.get("name") or "there").split()[0]
    body = f"Hi {first_name},\n\n{message}\n"
    if extra:
        body += f"\n{extra}\n"
    body += (
        f"\nSee your impact, badges and settings on your private page (no password needed):\n"
        f"{impact_link(profile.get('impact_token', ''), base_url)}\n\n"
        "Thank you for volunteering with Tech Bridge.\n"
        "You can pause new project requests any time from your private page."
    )
    return EMAIL_SUBJECTS.get(notification_type, "Tech Bridge update"), body


def nudge_details(project: dict[str, Any]) -> str:
    kind = "reuse (about 1 hour to customize)" if project.get("reuse_template_id") else f"new build (about {project.get('effort_hours', 0)} volunteer hours)"
    skills = ", ".join(project.get("skills", [])) or "open to all skills"
    return f"Project: {project.get('problem_type', 'Volunteer project')} for {mission_phrase(project.get('mission_area'))}\nType: {kind}\nSkills: {skills}"


# ---------------------------------------------------------------- impact summaries


def built_solutions(profile_id: str, templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [template for template in templates if template.get("builder_volunteer_id") == profile_id]


def volunteer_impact(profile: dict[str, Any], templates: list[dict[str, Any]]) -> dict[str, Any]:
    """Totals for one volunteer. Projects they completed count once each; reuses of their solutions add more."""
    solutions = built_solutions(profile.get("id", ""), templates)
    completed = profile.get("completed_projects", [])
    reuse_reach = sum(int(template.get("reuse_count", 0) or 0) for template in solutions)
    staff_hours = sum(int(item.get("hours_saved_per_week", 0) or 0) for item in completed) + sum(
        int(template.get("reuse_staff_hours_per_week", 0) or 0) for template in solutions
    )
    return {
        "nonprofits_helped": len(completed) + reuse_reach,
        "projects_completed": len(completed),
        "staff_hours_saved_per_week": staff_hours,
        "stars": int(profile.get("stars", 0) or 0),
        "badges": badge_lines(profile.get("badges", {})),
        "solutions": [
            {
                "title": template.get("title", "Solution"),
                "reuse_count": int(template.get("reuse_count", 0) or 0),
                "nonprofits_helped": 1 + int(template.get("reuse_count", 0) or 0),
                "staff_hours_saved_per_week": template_total_staff_hours(template),
            }
            for template in solutions
        ],
    }


def public_profile(profile: dict[str, Any], templates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Shareable profile: credit and totals only. None if the volunteer has not consented."""
    if not profile.get("show_name_consent", True):
        return None
    impact = volunteer_impact(profile, templates)
    return {
        "display_name": display_name(profile),
        "stars": impact["stars"],
        "badges": impact["badges"],
        "nonprofits_helped": impact["nonprofits_helped"],
        "staff_hours_saved_per_week": impact["staff_hours_saved_per_week"],
        "solutions": impact["solutions"],
        "demo": bool(profile.get("demo")),
    }


def milestone_message(nonprofits_helped: int) -> str | None:
    reached = [threshold for threshold in MILESTONE_THRESHOLDS if nonprofits_helped >= threshold]
    return f"Our volunteers have helped {reached[-1]} nonprofits!" if reached else None


def linkedin_snippet(profile: dict[str, Any], impact: dict[str, Any]) -> str:
    badges = ", ".join(
        f"{badge_label(skill)} (x{count})"
        for skill, count in sorted(profile.get("badges", {}).items(), key=lambda item: -int(item[1]))
    )
    text = (
        f"I volunteer with Tech Bridge, building simple tools for nonprofits. My work has helped "
        f"{plural(impact['nonprofits_helped'], 'nonprofit')} and saves their staff about "
        f"{impact['staff_hours_saved_per_week']} hours every week."
    )
    if badges:
        text += f" Skill badges verified by nonprofits: {badges}."
    return text + " #TechForGood #Volunteering"


def certificate_html(profile: dict[str, Any], impact: dict[str, Any]) -> str:
    """A printable certificate. Lists work by mission type only, never by nonprofit name."""
    escape = html.escape
    projects = "".join(
        f"<li>{escape(item.get('title', 'Volunteer project'))} <span>for {escape(mission_phrase(item.get('mission_area')))}</span></li>"
        for item in profile.get("completed_projects", [])
    ) or "<li>No completed projects yet</li>"
    badges = "".join(f"<li>{escape(line)}</li>" for line in impact["badges"]) or "<li>No badges yet</li>"
    demo = '<p class="demo">DEMO DATA - fictional volunteer record</p>' if profile.get("demo") else ""
    issued = datetime.now(timezone.utc).strftime("%B %d, %Y")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Tech Bridge certificate - {escape(profile.get('name', ''))}</title>
<style>
body {{ font-family: Georgia, serif; background:#f6f8f5; color:#192b28; margin:0; padding:2rem; }}
.card {{ max-width:760px; margin:auto; background:white; border:3px double #166b52; padding:2.5rem 3rem; }}
h1 {{ text-align:center; font-size:2rem; margin:.2rem 0; }} h2 {{ font-size:1.05rem; color:#166b52; margin-top:1.6rem; }}
.eyebrow {{ text-align:center; text-transform:uppercase; letter-spacing:.12em; font:700 .75rem sans-serif; color:#166b52; }}
.name {{ text-align:center; font-size:1.7rem; margin:1.2rem 0 .3rem; }} .lead {{ text-align:center; }}
li span {{ color:#64716d; }} .demo {{ text-align:center; font:700 .8rem sans-serif; color:#e36f51; }}
.foot {{ margin-top:2rem; font:.8rem sans-serif; color:#64716d; text-align:center; }}
</style></head><body><div class="card">
<div class="eyebrow">Tech Bridge</div><h1>Certificate of Volunteer Impact</h1>{demo}
<p class="name">{escape(profile.get('name', ''))}</p>
<p class="lead">has helped <strong>{impact['nonprofits_helped']}</strong> nonprofits and saves their staff about
<strong>{impact['staff_hours_saved_per_week']}</strong> hours every week.<br>Stars from nonprofits: {impact['stars']}</p>
<h2>Projects completed ({impact['projects_completed']})</h2><ul>{projects}</ul>
<h2>Skill badges</h2><ul>{badges}</ul>
<p class="foot">Issued {issued}. Nonprofits are listed by mission type only to protect their privacy.</p>
</div></body></html>"""


# ---------------------------------------------------------------- demo seed data (all labeled demo)


def _done(title: str, mission: str, kind: str, hours: int, skills: list[str], when: str) -> dict[str, Any]:
    return {
        "title": title, "mission_area": mission, "kind": kind, "hours_saved_per_week": hours,
        "skills": skills, "completed_at": when, "demo": True,
    }


def _proof(skill: str, level: int, source: str = "Practice task passed", private: dict[str, str] | None = None) -> dict[str, Any]:
    assert level in (2, 3), "Level 4 proofs come only from nonprofit stars"
    return {"skill": skill, "level": level, "source": source, "confirmed_by": "Tech Bridge coordinator", "private": private or {}}


SHEETS, SCRIPT = "Google Sheets/Excel", "Apps Script"

# Keyed by seed volunteer name. Anything not listed here uses DEFAULT_SEED_PROFILE.
RETENTION_SEED: dict[str, dict[str, Any]] = {
    "Priya Shah": {
        "stars": 6, "display_name_choice": "initial",
        "badges": {SHEETS: 5, SCRIPT: 3},
        "completed_projects": [
            _done("Volunteer Sign-up Sheet", "Food", "new build", 3, [SHEETS, SCRIPT], "2026-03-14T18:00:00+00:00"),
            _done("Volunteer shifts with automatic reminders", "Environment", "reuse", 2, [SHEETS, SCRIPT], "2026-04-02T18:00:00+00:00"),
            _done("Volunteer Sign-up Sheet", "Education", "reuse", 2, [SHEETS], "2026-05-09T18:00:00+00:00"),
            _done("Attendance form and outcomes dashboard", "Education", "reuse", 3, [SHEETS], "2026-06-20T18:00:00+00:00"),
            _done("Supply count tracker", "Food", "new build", 2, [SHEETS, SCRIPT], "2026-07-18T18:00:00+00:00"),
            _done("Event sign-in sheet", "Health", "new build", 1, [SHEETS], "2026-08-22T18:00:00+00:00"),
        ],
        "thank_you_notes": [{
            "note": "Thank you, Priya! Our Friday volunteer list used to take three hours. Now it's ready before our first shift starts.",
            "mission_area": "Food", "created_at": "2026-09-12T16:30:00+00:00", "demo": True,
        }],
    },
    "Amina Yusuf": {
        "stars": 9, "display_name_choice": "full",
        "badges": {"Power BI/Tableau": 6, "Data analysis": 5, SHEETS: 3},
        "completed_projects": [
            _done("Attendance form and outcomes dashboard", "Education", "new build", 5, ["Power BI/Tableau", "Data analysis"], "2026-02-11T18:00:00+00:00"),
            *[_done("Outcomes dashboard", mission, "new build", 2, ["Power BI/Tableau"], f"2026-0{month}-10T18:00:00+00:00")
              for month, mission in zip(range(3, 9), ["Health", "Food", "Education", "Health", "Women and families", "Food"])],
            _done("Funder report template", "Education", "reuse", 1, ["Data analysis"], "2026-09-01T18:00:00+00:00"),
            _done("Screening follow-up tracker", "Health", "new build", 2, [SHEETS], "2026-09-15T18:00:00+00:00"),
        ],
    },
    "Marcus Johnson": {
        "stars": 3, "display_name_choice": "full",
        "badges": {"Airtable/No-code": 3, "Zapier/Make automation": 2},
        "completed_projects": [
            _done("Private donor list with thank-you drafts", "Women and families", "new build", 4, ["Airtable/No-code", "Zapier/Make automation"], "2026-04-18T18:00:00+00:00"),
            _done("Volunteer Sign-up Sheet", "Food", "reuse", 1, [SHEETS], "2026-06-06T18:00:00+00:00"),
            _done("Donor follow-up automation", "Education", "reuse", 2, ["Zapier/Make automation"], "2026-08-08T18:00:00+00:00"),
        ],
    },
    "Lucas Ferreira": {
        "stars": 4, "display_name_choice": "initial",
        "badges": {"Web design (HTML/CSS)": 4, "UX design": 3, "JavaScript/React": 1},
        "completed_projects": [
            _done("Accessible event page", mission, "new build", 1, ["Web design (HTML/CSS)", "UX design"], f"2026-0{month}-05T18:00:00+00:00")
            for month, mission in zip(range(4, 8), ["Animals", "Environment", "Animals", "Education"])
        ],
    },
    "Grace Kim": {
        # Consent off: her library solution shows "Built by a Tech Bridge volunteer".
        "stars": 1, "show_name_consent": False,
        "badges": {SHEETS: 1, SCRIPT: 1},
        "completed_projects": [
            _done("Volunteer shifts with automatic reminders", "Environment", "new build", 3, [SHEETS, SCRIPT], "2026-05-23T18:00:00+00:00"),
        ],
    },
    "Noah Patel": {
        "stars": 1, "badges": {SHEETS: 1},
        "completed_projects": [_done("Volunteer Sign-up Sheet", "Food", "reuse", 1, [SHEETS], "2026-04-25T18:00:00+00:00")],
    },
    "Caleb Brooks": {
        "completed_projects": [_done("Volunteer Sign-up Sheet", "Food", "reuse", 1, [SHEETS], "2026-07-11T18:00:00+00:00")],
    },
    # Level 3 skill checks, each after a first completed Setup of a proven fix.
    "Hannah Okafor": {
        "proofs": [_proof("Canva/Graphics", 3), _proof("UX design", 3)],
        "completed_projects": [_done("Outreach design templates", "Education", "reuse", 2, ["Canva/Graphics"], "2026-06-12T18:00:00+00:00")],
    },
    "Zara Hussain": {
        "proofs": [_proof("Power BI/Tableau", 3), _proof("Data analysis", 3)],
        "completed_projects": [_done("Attendance form and outcomes dashboard", "Health", "reuse", 2, ["Power BI/Tableau"], "2026-07-02T18:00:00+00:00")],
    },
    "Aarav Mehta": {
        "proofs": [_proof("Python", 3), _proof("SQL/Databases", 3)],
        "completed_projects": [_done("Volunteer Sign-up Sheet", "Health", "reuse", 1, [SHEETS], "2026-07-30T18:00:00+00:00")],
    },
    "Ethan Walker": {
        "proofs": [_proof("CRM setup (e.g., HubSpot/Salesforce Nonprofit)", 3), _proof("Airtable/No-code", 2, "Evidence: certificate with verification link",
                   {"link": "https://verify.example.org/cert/AT-20931"})],
        "completed_projects": [_done("Private donor list with thank-you drafts", "Health", "reuse", 1, ["Airtable/No-code"], "2026-08-14T18:00:00+00:00")],
    },
    # Level 2 evidence only. Reference names and contact details are coordinator-only.
    "Sara Nakamura": {"proofs": [_proof("UX design", 2, "Evidence: portfolio link", {"link": "https://portfolio.example.org/sara-n"})]},
    "Kevin Tran": {"proofs": [_proof("Mobile apps", 2, "Evidence: reference (professor)", {
        "reference_name": "Dr. Imani Okafor", "relationship": "Professor",
        "contact": "i.okafor@example.edu · 972-555-0147",
    })]},
    "Emily Carter": {"proofs": [_proof("Airtable/No-code", 2, "Evidence: certificate with verification link", {"link": "https://verify.example.org/cert/AT-11872"})]},
    # Alex: every skill self-listed; the demo project is submitted and waiting for mentor review.
    "Alex Rivera": {"display_name_choice": "initial"},
    # New volunteer: identity verified only, has a pending nudge.
    "Jordan Ellis": {"display_name_choice": "nickname", "nickname": "Jordan E."},
    # Paused volunteer: never matched or invited.
    "Jacob Miller": {"paused": True},
}

DEFAULT_SEED_PROFILE: dict[str, Any] = {
    "stars": 0, "badges": {}, "identity_verified": True, "background_check_cleared": False,
    "paused": False, "show_name_consent": True, "display_name_choice": "initial", "nickname": "",
    "completed_projects": [], "thank_you_notes": [], "proofs": [],
}

# Demo notifications, keyed by seed volunteer name. created_at is fixed so demo nudges don't block real ones forever.
SEED_NOTIFICATIONS: dict[str, list[dict[str, Any]]] = {
    "Priya Shah": [
        {
            "type": "reuse", "read": True, "created_at": "2026-07-11T19:00:00+00:00",
            "message": "Your Volunteer Sign-up Sheet just helped a food pantry. It has now helped 4 nonprofits and saves them about 6 staff hours every week.",
        },
        {
            "type": "star", "read": False, "created_at": "2026-09-12T16:30:00+00:00",
            "message": "A nonprofit gave you a star! You earned Google Sheets and Apps Script badges.",
            "extra": "Their thank-you note:\n\"Thank you, Priya! Our Friday volunteer list used to take three hours. Now it's ready before our first shift starts.\"",
        },
        {
            "type": "reuse", "read": False, "created_at": "2026-09-20T15:00:00+00:00",
            "message": "Your Volunteer Sign-up Sheet just helped an education nonprofit. It has now helped 5 nonprofits and saves them about 8 staff hours every week.",
        },
    ],
    "Jordan Ellis": [
        {
            "type": "nudge", "read": False, "created_at": "2026-09-25T14:00:00+00:00",
            "message": NUDGE_MESSAGE,
            "extra": "Project: Volunteer data consolidation for a food pantry\nType: reuse (about 1 hour to customize)\nSkills: Google Sheets/Excel",
            "action": {"demo": True, "response": None},
        },
    ],
}


def seed_profile_fields(name: str) -> dict[str, Any]:
    fields = json.loads(json.dumps(DEFAULT_SEED_PROFILE))
    fields.update(json.loads(json.dumps(RETENTION_SEED.get(name, {}))))
    return fields


def seed_matching_fields(name: str) -> dict[str, Any]:
    """The matching-relevant fields of a seed volunteer, as they appear after profile enrichment."""
    fields = seed_profile_fields(name)
    levels: dict[str, int] = {}
    for proof in fields["proofs"]:
        levels[proof["skill"]] = max(levels.get(proof["skill"], 0), proof["level"])
    for skill, count in fields["badges"].items():
        if count:
            levels[skill] = 4
    return {
        "stars": fields["stars"], "badges": fields["badges"], "skill_levels": levels,
        "identity_verified": fields["identity_verified"], "background_check_cleared": fields["background_check_cleared"],
        "paused": fields["paused"],
    }
