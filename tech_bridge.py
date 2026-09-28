"""Core data, matching, and AI helpers for Tech Bridge."""

from __future__ import annotations

import json
import os
import re
import secrets
import smtplib
from datetime import datetime, timezone
from difflib import SequenceMatcher
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

from onboarding import (
    assignment_check,
    mentor_review_required,
    seed_onboarding,
    volunteer_status,
)
from volunteer_retention import (
    fallback_thank_you_note,
    format_skill_proofs,
    scrub_organization,
    seed_matching_fields,
    skill_score,
)

SKILLS = [
    "Google Sheets/Excel",
    "Apps Script",
    "Airtable/No-code",
    "Zapier/Make automation",
    "Python",
    "SQL/Databases",
    "Power BI/Tableau",
    "Data analysis",
    "Web design (HTML/CSS)",
    "WordPress/Squarespace/Wix",
    "JavaScript/React",
    "UX design",
    "Canva/Graphics",
    "Mobile apps",
    "CRM setup (e.g., HubSpot/Salesforce Nonprofit)",
]

MISSION_AREAS = [
    "Food",
    "Education",
    "Animals",
    "Women and families",
    "Health",
    "Environment",
    "Other",
]

STORAGE_PATH = Path(__file__).parent / "data" / "tech_bridge_data.json"
VOLUNTEER_HOURLY_VALUE = 36.14
MINIMUM_REUSE_SIMILARITY = 65
DEMO_SEED_VERSION = 6
PRIVATE_TEXT_REDACTIONS = [
    (re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE), "[email removed]"),
    (re.compile(r"(?<!\w)(?:\+?1[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]\d{4}(?!\w)"), "[phone removed]"),
]


def _template(
    template_id: str,
    title: str,
    mission: str,
    keywords: list[str],
    problem_type: str,
    solution: str,
    tools: list[str],
    skills: list[str],
    steps: list[str],
    estimated_build_hours: int = 8,
    built_by: str = "Priya Shah",
    reuse_count: int = 1,
    source_project_title: str = "Completed volunteer project",
    origin_staff_hours: int = 0,
    reuse_staff_hours: int = 0,
) -> dict[str, Any]:
    return {
        "id": template_id,
        "title": title,
        "mission_area": mission,
        "keywords": keywords,
        "problem_type": problem_type,
        "solution": solution,
        "tools": tools,
        "skills": skills,
        "steps": steps,
        "license": "Creative Commons Attribution 4.0 International (CC BY 4.0)",
        "data_free": True,
        "demo_template": True,
        "built_by": built_by,
        "reuse_count": reuse_count,
        "estimated_build_hours": estimated_build_hours,
        "source_project_status": "Done",
        "source_project_title": source_project_title,
        "origin_staff_hours_per_week": origin_staff_hours,
        "reuse_staff_hours_per_week": reuse_staff_hours,
        "handoff_guide": "## Day to day\n1. Open the approved shared tool.\n2. Follow the reusable steps listed on this card.\n3. Test changes with sample data and keep access restricted.\n\n## Fixes\n- Check the sharing settings if access fails.\n- Review the source row if a result looks wrong.\n- Ask the organization coordinator before changing an automation.",
    }


SEED_TEMPLATES = [
    _template(
        "tpl-volunteer-intake",
        "Volunteer Sign-up Sheet",
        "Food",
        ["volunteer", "excel", "spreadsheet", "combine", "duplicate", "intake"],
        "Volunteer data consolidation",
        "A simple signup form writes to one shared spreadsheet, with a review step for duplicates.",
        ["Google Forms", "Google Sheets"],
        ["Google Sheets/Excel", "Apps Script"],
        ["Create a signup form", "Connect responses to a shared sheet", "Add duplicate checks", "Test access and updates"],
        8,
        "Priya Shah",
        4,
        "Volunteer Sign-up Sheet",
        3,
        5,
    ),
    _template(
        "tpl-attendance-dashboard",
        "Attendance form and outcomes dashboard",
        "Education",
        ["attendance", "report", "funders", "learner", "paper", "dashboard"],
        "Attendance tracking and reporting",
        "A short attendance form feeds a spreadsheet that powers a basic outcomes dashboard.",
        ["Google Forms", "Google Sheets", "Looker Studio or Power BI"],
        ["Google Sheets/Excel", "Power BI/Tableau", "Data analysis"],
        ["Define the minimum fields", "Create the attendance form", "Connect a summary dashboard", "Review sharing permissions"],
        12,
        "Amina Yusuf",
        2,
        "Attendance form and outcomes dashboard",
        5,
        4,
    ),
    _template(
        "tpl-donor-thanks",
        "Private donor list with thank-you drafts",
        "Women and families",
        ["donor", "thank", "donation", "email", "fundraising"],
        "Donor follow-up workflow",
        "A restricted-access donor tracker creates thank-you email drafts for staff review before sending.",
        ["Airtable", "Email drafts"],
        ["Airtable/No-code", "Zapier/Make automation"],
        ["Limit access to authorized staff", "Create a minimal donor tracker", "Draft thank-you messages", "Test without real donor data"],
        6,
        "Marcus Johnson",
        2,
        "Private donor list with thank-you drafts",
        4,
        3,
    ),
    _template(
        "tpl-volunteer-scheduling",
        "Volunteer shifts with automatic reminders",
        "Environment",
        ["schedule", "shift", "remind", "garden", "volunteer", "text"],
        "Volunteer scheduling and reminders",
        "A shift signup sheet gives volunteers a clear schedule and sends advance reminders.",
        ["Google Sheets", "Email automation"],
        ["Google Sheets/Excel", "Apps Script"],
        ["Publish available shifts", "Collect signups", "Send a reminder before each shift", "Give a coordinator an override"],
        6,
        "Grace Kim",
        1,
        "Volunteer shifts with automatic reminders",
        3,
        2,
    ),
]


def _seed_student(
    name: str,
    major: str,
    year: int,
    skills: list[str],
    hours: int,
    causes: list[str],
    mode: str,
    bio: str = "",
) -> dict[str, Any]:
    return {
        **seed_matching_fields(name),
        "id": str(uuid4()),
        "name": name,
        "email": re.sub(r"[^a-z.]", "", name.casefold().replace(" ", ".")) + "@example.org",
        "major": major,
        "year": year,
        "skills": skills,
        "hours_per_week": hours,
        "causes": causes,
        "mode": mode,
        "bio": bio,
        "confidentiality_signed": name not in {"Alex Rivera", "Jordan Ellis"},
        "demo_student": True,
        "onboarding": seed_onboarding(name),
    }


def _with_status(student: dict[str, Any]) -> dict[str, Any]:
    student["onboarding_status"] = volunteer_status(student, [])
    return student


SEED_STUDENTS = [
    _seed_student('Priya Shah', 'Data Science', 3, ['Google Sheets/Excel', 'Apps Script', 'Data analysis'], 6, ['Food', 'Education'], 'In person', "Automates spreadsheet chores with Apps Script; built a pantry's volunteer sign-up merger."),
    _seed_student('Noah Patel', 'Software Engineering', 4, ['Apps Script', 'Google Sheets/Excel', 'SQL/Databases'], 9, ['Food', 'Environment'], 'In person', 'Writes Apps Script and SQL; likes turning manual weekly tasks into one-click reports.'),
    _seed_student('Amina Yusuf', 'Business Analytics', 2, ['Power BI/Tableau', 'Data analysis', 'Google Sheets/Excel'], 4, ['Food', 'Health'], 'In person', 'Builds Power BI dashboards that help small teams show outcomes to funders.'),
    _seed_student('Marcus Johnson', 'Information Systems', 1, ['Airtable/No-code', 'Zapier/Make automation', 'CRM setup (e.g., HubSpot/Salesforce Nonprofit)'], 6, ['Women and families', 'Education'], 'Hybrid', 'Sets up Airtable bases and Zapier automations for donor and volunteer follow-up.'),
    _seed_student('Grace Kim', 'Information Technology', 2, ['Airtable/No-code', 'Google Sheets/Excel', 'Zapier/Make automation'], 4, ['Women and families', 'Health'], 'In person', 'Organizes shift schedules and reminder automations in Airtable and Google Sheets.'),
    _seed_student('Caleb Brooks', 'Information Systems', 1, ['Google Sheets/Excel', 'Data analysis'], 3, ['Food', 'Health'], 'In person', 'Detail-oriented with spreadsheets; happy to clean up and document existing trackers.'),
    _seed_student('Aarav Mehta', 'Computer Science', 3, ['Python', 'SQL/Databases', 'Data analysis'], 8, ['Health', 'Education'], 'Remote', 'Writes Python scripts that clean messy exports and load them into simple databases.'),
    _seed_student('Hannah Okafor', 'Arts, Technology, and Emerging Communication', 2, ['Canva/Graphics', 'UX design', 'WordPress/Squarespace/Wix'], 6, ['Education', 'Women and families'], 'Hybrid', 'Designs flyers, social posts, and short explainer videos in Canva and Clipchamp.'),
    _seed_student('Lucas Ferreira', 'Software Engineering', 4, ['JavaScript/React', 'Web design (HTML/CSS)', 'UX design'], 8, ['Animals', 'Environment'], 'Remote', 'Front-end developer who builds accessible, mobile-friendly sites and forms.'),
    _seed_student('Zara Hussain', 'Business Analytics', 3, ['Power BI/Tableau', 'SQL/Databases', 'Data analysis'], 6, ['Health', 'Food'], 'Remote', 'Turns program data into Tableau dashboards with clear, funder-ready metrics.'),
    _seed_student('Ethan Walker', 'Information Systems', 2, ['CRM setup (e.g., HubSpot/Salesforce Nonprofit)', 'Airtable/No-code', 'Zapier/Make automation'], 5, ['Women and families', 'Health'], 'Hybrid', 'Configures HubSpot and Salesforce Nonprofit for donor and case follow-up workflows.'),
    _seed_student('Mia Thompson', 'Marketing', 1, ['Canva/Graphics', 'WordPress/Squarespace/Wix'], 4, ['Animals', 'Education'], 'In person', 'Creates adoption posters, newsletters, and simple Squarespace pages.'),
    _seed_student('Kevin Tran', 'Computer Engineering', 4, ['Mobile apps', 'JavaScript/React', 'Python'], 7, ['Health', 'Environment'], 'Remote', 'Builds cross-platform mobile apps; interested in check-in and outreach tools.'),
    _seed_student('Fatima Al-Sayed', 'Data Science', 4, ['Python', 'Data analysis', 'Power BI/Tableau'], 8, ['Education', 'Health'], 'Remote', 'Analyzes survey and outcomes data and presents results in plain language.'),
    _seed_student('Jacob Miller', 'Information Technology', 3, ['Google Sheets/Excel', 'Apps Script', 'Zapier/Make automation'], 5, ['Food', 'Environment'], 'In person', 'Connects Google Forms, Sheets, and email reminders so nothing falls through the cracks.'),
    _seed_student('Sara Nakamura', 'Arts, Technology, and Emerging Communication', 3, ['UX design', 'Web design (HTML/CSS)', 'Canva/Graphics'], 6, ['Education', 'Animals'], 'Hybrid', 'UX designer who runs quick usability tests with staff before anything is built.'),
    _seed_student('Daniel Okoye', 'Computer Science', 2, ['Python', 'Google Sheets/Excel', 'Apps Script'], 6, ['Food', 'Education'], 'Remote', 'Automates reports between Google Sheets and email with Apps Script and Python.'),
    _seed_student('Chloe Bennett', 'Marketing', 3, ['Canva/Graphics', 'WordPress/Squarespace/Wix', 'UX design'], 5, ['Women and families', 'Animals'], 'In person', 'Brand and social media designer; builds reusable Canva templates for small teams.'),
    _seed_student('Rohan Iyer', 'Software Engineering', 3, ['SQL/Databases', 'Python', 'JavaScript/React'], 7, ['Environment', 'Food'], 'Remote', 'Back-end developer comfortable with databases, APIs, and small internal tools.'),
    _seed_student('Emily Carter', 'Business Administration', 2, ['Airtable/No-code', 'Google Sheets/Excel', 'CRM setup (e.g., HubSpot/Salesforce Nonprofit)'], 4, ['Education', 'Women and families'], 'Hybrid', 'Sets up simple CRMs and trackers for enrollment and family follow-ups.'),
    _seed_student('Victor Alvarez', 'Information Systems', 4, ['Zapier/Make automation', 'Airtable/No-code', 'Google Sheets/Excel'], 8, ['Food', 'Health'], 'Remote', 'Automation specialist who links forms, sheets, and email with Make and Zapier.'),
    _seed_student('Nadia Rahman', 'Healthcare Management', 3, ['Data analysis', 'Google Sheets/Excel', 'Power BI/Tableau'], 5, ['Health', 'Women and families'], 'In person', 'Tracks outreach and screening data while keeping privacy rules front of mind.'),
    _seed_student('Tyler Robinson', 'Computer Science', 1, ['Web design (HTML/CSS)', 'JavaScript/React'], 4, ['Animals', 'Environment'], 'Remote', 'First-year web developer eager to build pet adoption and event pages.'),
    _seed_student('Leah Goldberg', 'Arts, Technology, and Emerging Communication', 4, ['Canva/Graphics', 'UX design', 'Web design (HTML/CSS)'], 7, ['Education', 'Health'], 'Hybrid', 'Produces short lesson videos and learner-friendly visual guides.'),
    _seed_student('Samuel Adeyemi', 'Data Science', 2, ['Python', 'SQL/Databases', 'Power BI/Tableau'], 6, ['Education', 'Food'], 'Remote', 'Builds attendance and outcomes dashboards backed by clean data models.'),
    _seed_student('Olivia Park', 'Marketing', 4, ['WordPress/Squarespace/Wix', 'Canva/Graphics', 'UX design'], 6, ['Women and families', 'Education'], 'In person', 'Manages WordPress sites and email newsletters for community programs.'),
    _seed_student('Arjun Nair', 'Software Engineering', 3, ['Mobile apps', 'JavaScript/React', 'UX design'], 8, ['Environment', 'Animals'], 'Remote', 'Mobile developer who builds volunteer check-in and field data collection apps.'),
    _seed_student('Jasmine Lee', 'Business Analytics', 1, ['Google Sheets/Excel', 'Data analysis', 'Canva/Graphics'], 3, ['Food', 'Education'], 'In person', 'Organized spreadsheet builder who also makes simple infographics for reports.'),
    _seed_student('Mohammed Karim', 'Information Technology', 3, ['SQL/Databases', 'Google Sheets/Excel', 'Apps Script'], 6, ['Health', 'Food'], 'Hybrid', 'Consolidates inventory and intake data into one reliable shared source.'),
    _seed_student('Isabel Moreno', 'Public Affairs', 2, ['Airtable/No-code', 'Canva/Graphics', 'Google Sheets/Excel'], 4, ['Women and families', 'Health'], 'In person', 'Bilingual (English/Spanish); builds intake forms and translated handouts.'),
    _seed_student('Ben Harrison', 'Computer Science', 4, ['JavaScript/React', 'SQL/Databases', 'Web design (HTML/CSS)'], 9, ['Education', 'Environment'], 'Remote', 'Full-stack developer for projects that outgrow spreadsheets.'),
    _seed_student('Keerti Reddy', 'Information Systems', 2, ['CRM setup (e.g., HubSpot/Salesforce Nonprofit)', 'Zapier/Make automation', 'Google Sheets/Excel'], 5, ['Education', 'Health'], 'Hybrid', 'Configures CRMs and automated thank-you and reminder emails.'),
    _seed_student('Ava Robinson', 'Arts, Technology, and Emerging Communication', 1, ['Canva/Graphics', 'WordPress/Squarespace/Wix'], 4, ['Animals', 'Environment'], 'In person', 'Photographer and designer for adoption profiles and event promotion.'),
    _seed_student('William Chen', 'Business Analytics', 4, ['Power BI/Tableau', 'Data analysis', 'SQL/Databases'], 7, ['Food', 'Women and families'], 'Remote', 'Builds impact dashboards and helps teams choose the few metrics that matter.'),
    _seed_student('Maya Singh', 'Data Science', 3, ['Data analysis', 'Python', 'Google Sheets/Excel'], 5, ['Environment', 'Health'], 'Hybrid', 'Cleans and analyzes field and survey data; writes clear handoff notes.'),
    _seed_student('Gabriel Santos', 'Software Engineering', 2, ['Web design (HTML/CSS)', 'WordPress/Squarespace/Wix', 'JavaScript/React'], 6, ['Animals', 'Food'], 'Remote', 'Builds and maintains small nonprofit websites on WordPress and Wix.'),
    _seed_student('Harper Davis', 'Marketing', 2, ['Canva/Graphics', 'UX design'], 4, ['Education', 'Animals'], 'In person', 'Makes social media graphics and short promo videos for events.'),
    _seed_student('Yusuf Demir', 'Computer Engineering', 3, ['Python', 'Zapier/Make automation', 'Apps Script'], 7, ['Environment', 'Food'], 'Remote', 'Automates data entry between forms, sheets, and email using Python and Make.'),
    _seed_student('Elena Petrova', 'Information Technology', 4, ['Airtable/No-code', 'CRM setup (e.g., HubSpot/Salesforce Nonprofit)', 'Data analysis'], 6, ['Health', 'Women and families'], 'Hybrid', 'Designs case-tracking bases with role-based access and privacy-safe views.'),
    _seed_student('Jordan Ellis', 'Computer Science', 1, ['Google Sheets/Excel', 'Web design (HTML/CSS)'], 3, ['Education', 'Food'], 'Remote', 'New volunteer comfortable with spreadsheets and basic web pages.'),
    _seed_student('Alex Rivera', 'Business Analytics', 2, ['Google Sheets/Excel', 'Python', 'Power BI/Tableau'], 5, ['Food', 'Education'], 'Hybrid', 'Lists Excel, Python and Power BI; hasn\'t completed a Tech Bridge project yet.'),
]
SEED_STUDENTS = [_with_status(student) for student in SEED_STUDENTS]


def _seed_project(
    organization: str,
    mission: str,
    comfort: str,
    problem: str,
    template_id: str | None,
    wasted: int,
    difficulty: str,
    effort: int,
    privacy: str,
) -> dict[str, Any]:
    template = next((item for item in SEED_TEMPLATES if item["id"] == template_id), None)
    if template is None:
        template = next((item for item in SEED_TEMPLATES if item["mission_area"] == mission), None)
    if template is None and mission == "Animals":
        template = {
            "problem_type": "Accessible shelter website workflow",
            "solution": "Build a focused, accessible website workflow that lets shelter staff keep approved pet and intake information current.",
            "tools": ["Web design tools"],
            "skills": ["Web design (HTML/CSS)", "UX design"],
            "steps": ["Review current site needs", "Design the staff update flow", "Build and test with sample content", "Document maintenance steps"],
        }
    if template is None:
        template = SEED_TEMPLATES[0]
    return {
        "id": str(uuid4()),
        "organization": organization,
        "mission_area": mission,
        "tech_comfort": comfort,
        "problem_summary": problem,
        "problem_type": template["problem_type"],
        "hours_wasted_per_week": wasted,
        "suggested_solution": template["solution"],
        "why_this_solution": "It uses familiar, low-cost tools that staff can keep updated without a developer.",
        "advanced_alternative": "A custom database or web app, only if the workflow outgrows these tools.",
        "tools": template["tools"],
        "skills": template["skills"],
        "difficulty": difficulty,
        "effort_hours": effort,
        "build_effort_hours": effort,
        "deliverables": template["steps"],
        "privacy_notes": privacy,
        "reuse_template_id": template_id,
        "reuse_reason": "A data-free starter pattern already exists; a volunteer can adapt it in about an hour.",
        "library_consent": False,
        "status": "Open",
        "assigned_student_id": None,
        "data_mode": "Sample data",
        "handoff_guide": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "demo_project": True,
    }


def _complete_seed_project(
    project: dict[str, Any],
    student_name: str,
    *,
    library_template_id: str | None = None,
    reuse: bool = False,
    consent: bool = True,
) -> dict[str, Any]:
    student = next(item for item in SEED_STUDENTS if item["name"] == student_name)
    project["status"] = "Done"
    project["assigned_student_id"] = student["id"]
    project["mentor_approval"] = {"approved_by": "Amina Yusuf", "role": "Mentor", "approved_at": "2026-05-01T18:00:00+00:00", "demo": True}
    project["library_consent"] = consent
    project["handoff_guide"] = "## Demo handoff\n\nUse the approved shared tool, follow the project steps, and keep data access limited to authorized staff. Test updates with sample data."
    if library_template_id:
        project["library_template_id"] = library_template_id
    if reuse:
        project["build_effort_hours"] = 8
        project["library_match_similarity"] = 88
        project["reuse_reason"] = "A completed data-free solution was customized for this nonprofit."
    return project


SEED_PROJECTS = [
    _complete_seed_project(
        _seed_project("Oak Cliff Community Pantry", "Food", "Basic", "Every Friday, we copy volunteer names from three Excel files into one list. It takes 3 hours.", "tpl-volunteer-intake", 3, "Beginner", 8, "Volunteer phone numbers are personal data. Restrict sheet access to pantry staff; use sample data during setup."),
        "Priya Shah", library_template_id="tpl-volunteer-intake",
    ),
    _complete_seed_project(
        _seed_project("North Dallas Food Share", "Food", "Basic", "We copy volunteer names from three spreadsheets into one list.", "tpl-volunteer-intake", 1, "Beginner", 1, "Volunteer contact data stays in this nonprofit's restricted workspace."),
        "Noah Patel", reuse=True,
    ),
    _complete_seed_project(
        _seed_project("Garland Meals", "Food", "Basic", "We copy volunteer names from several spreadsheets every week and it takes forever.", "tpl-volunteer-intake", 1, "Beginner", 1, "Volunteer contact data stays in this nonprofit's restricted workspace."),
        "Marcus Johnson", reuse=True,
    ),
    _complete_seed_project(
        _seed_project("Irving Youth League", "Food", "Basic", "We combine volunteer spreadsheets before weekly events.", "tpl-volunteer-intake", 1, "Beginner", 1, "Volunteer contact data stays in this nonprofit's restricted workspace."),
        "Caleb Brooks", reuse=True,
    ),
    _seed_project("Paws of Plano Rescue", "Animals", "Basic", "Our shelter website needs a multilingual, accessible intake workflow that our current platform cannot support.", None, 2, "Intermediate", 18, "Do not publish adopter, foster, or client information. Use sample content for the new site."),
    _complete_seed_project(
        _seed_project("Bright Futures Tutoring", "Education", "Some", "We track learner attendance on paper and can't show funders our results.", "tpl-attendance-dashboard", 5, "Intermediate", 12, "Learner attendance can be sensitive. Use minimum fields and share aggregate results only."),
        "Amina Yusuf", library_template_id="tpl-attendance-dashboard",
    ),
    _complete_seed_project(
        _seed_project("Safe Harbor Women's Center", "Women and families", "Basic", "Thanking donors takes our director hours every month.", "tpl-donor-thanks", 4, "Beginner", 6, "Sensitive donor information. Restrict access to authorized staff and review every draft before sending."),
        "Marcus Johnson", library_template_id="tpl-donor-thanks",
    ),
    _complete_seed_project(
        _seed_project("Richardson Community Garden", "Environment", "Basic", "Volunteer shift scheduling happens over group texts and people forget.", "tpl-volunteer-scheduling", 3, "Beginner", 6, "Volunteer contact details are personal data. Share only with coordinators."),
        "Grace Kim", library_template_id="tpl-volunteer-scheduling",
    ),
]


def new_demo_state() -> dict[str, Any]:
    return {
        "projects": json.loads(json.dumps(SEED_PROJECTS)),
        "students": json.loads(json.dumps(SEED_STUDENTS)),
        "templates": json.loads(json.dumps(SEED_TEMPLATES)),
        "demo_seed_version": DEMO_SEED_VERSION,
    }


def load_state(path: Path = STORAGE_PATH) -> dict[str, Any]:
    """Read local JSON state, initializing or recovering with labeled demo data."""
    if not path.exists():
        state = new_demo_state()
        save_state(state, path)
        return state
    try:
        with path.open("r", encoding="utf-8") as file:
            state = json.load(file)
        if not all(key in state for key in ("projects", "students", "templates")):
            raise ValueError("State is missing required collections")
        if int(state.get("demo_seed_version", 0)) < DEMO_SEED_VERSION:
            old_demo_students = [student for student in state["students"] if student.get("demo_student")]
            new_demo_students = json.loads(json.dumps(SEED_STUDENTS))
            new_students_by_name = {student["name"]: student for student in new_demo_students}
            old_to_new_student_ids = {
                student["id"]: new_students_by_name[student["name"]]["id"]
                for student in old_demo_students if student["name"] in new_students_by_name
            }
            preserved_projects = [project for project in state["projects"] if not project.get("demo_project")]
            for project in preserved_projects:
                assigned_id = project.get("assigned_student_id")
                if assigned_id in old_to_new_student_ids:
                    project["assigned_student_id"] = old_to_new_student_ids[assigned_id]
                project.setdefault("build_effort_hours", project.get("effort_hours", 8))
                project.setdefault("library_consent", False)
            state["projects"] = json.loads(json.dumps(SEED_PROJECTS)) + preserved_projects
            state["students"] = new_demo_students + [student for student in state["students"] if not student.get("demo_student")]
            state["templates"] = json.loads(json.dumps(SEED_TEMPLATES)) + [template for template in state["templates"] if not template.get("demo_template")]
            state["demo_seed_version"] = DEMO_SEED_VERSION
            save_state(state, path)
        return state
    except (OSError, json.JSONDecodeError, ValueError):
        return new_demo_state()


def save_state(state: dict[str, Any], path: Path = STORAGE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=True, indent=2)
    temporary.replace(path)


def _extract_json(text: str) -> Any:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _anthropic_text(prompt: str, max_tokens: int = 1400) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5"),
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return "\n".join(block.text for block in response.content if getattr(block, "type", "") == "text")


def _keyword_template(problem: str, templates: list[dict[str, Any]]) -> dict[str, Any] | None:
    text = problem.casefold()
    scored = []
    for template in templates:
        if template.get("id") == "tpl-volunteer-intake" and not re.search(
            r"\b(excel|spreadsheet|spreadsheets|sheets?|files?|combine|merge|duplicate|consolidat\w*)\b",
            text,
        ):
            continue
        score = sum(1 for keyword in template.get("keywords", []) if keyword.casefold() in text)
        if score:
            scored.append((score, template))
    return max(scored, key=lambda item: item[0])[1] if scored else None


def _similarity_terms(text: str) -> set[str]:
    text = re.sub(r"\bsign[ -]?up\b", " signup ", text.casefold())
    terms = set(re.findall(r"[a-z0-9]+", text))
    terms -= {"a", "an", "and", "are", "by", "for", "from", "how", "in", "into", "is", "it", "of", "on", "our", "the", "this", "to", "we", "with", "you", "your", "every", "week", "several", "names", "takes", "forever", "one", "list", "need", "needs", "help", "want", "get", "make", "workflow", "process", "staff", "team", "creation", "create", "building", "build", "new", "simple"}
    groups = {
        "volunteer": {"volunteers", "volunteer"},
        "spreadsheet": {"spreadsheet", "spreadsheets", "excel", "sheets", "sheet", "csv"},
        "consolidate": {"copy", "combine", "combining", "merge", "merger", "merging", "consolidate", "consolidation"},
        "signup": {"signup", "signups", "form", "forms", "intake"},
        "donor": {"donor", "donors", "donation", "donations"},
        "thank": {"thank", "thanks", "thanking"},
        "email": {"email", "emails"},
    }
    for canonical, variants in groups.items():
        if terms & variants:
            terms.difference_update(variants)
            terms.add(canonical)
    return terms


def find_duplicate_project(
    projects: list[dict[str, Any]],
    organization: str,
    summary: str,
    threshold: float = 0.78,
) -> dict[str, Any] | None:
    normalized_organization = re.sub(r"\W+", " ", organization.casefold()).strip()
    normalized_summary = re.sub(r"\W+", " ", summary.casefold()).strip()
    if not normalized_organization or not normalized_summary:
        return None
    candidates = []
    for project in projects:
        existing_organization = re.sub(r"\W+", " ", project.get("organization", "").casefold()).strip()
        if existing_organization != normalized_organization:
            continue
        existing_summary = re.sub(r"\W+", " ", project.get("problem_summary", "").casefold()).strip()
        if not existing_summary:
            continue
        summary_tokens = set(normalized_summary.split())
        existing_tokens = set(existing_summary.split())
        token_overlap = len(summary_tokens & existing_tokens) / max(1, min(len(summary_tokens), len(existing_tokens)))
        similarity = max(SequenceMatcher(None, normalized_summary, existing_summary).ratio(), token_overlap)
        if normalized_summary == existing_summary or similarity >= threshold:
            candidates.append((similarity, project))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def library_similarity(problem: str, template: dict[str, Any]) -> int:
    template_text = " ".join([
        template.get("title", ""), template.get("problem_type", ""),
        " ".join(template.get("keywords", [])),
    ])
    problem_terms = _similarity_terms(problem)
    template_terms = _similarity_terms(template_text)
    matched = len(problem_terms & template_terms)
    if matched >= 3:
        return 88
    if matched == 2:
        return 74
    if matched == 1:
        return 55
    return 0


MISSION_CONTEXT = {
    "Food": {"audience": "clients and volunteers", "focus": "pantry and meal programs", "records": "distribution days, volunteer shifts, or supply counts"},
    "Education": {"audience": "learners and families", "focus": "classes and tutoring programs", "records": "sessions, lesson materials, or learner progress"},
    "Animals": {"audience": "adopters and fosters", "focus": "animal care and adoptions", "records": "animal care tasks, foster placements, or adoption follow-ups"},
    "Women and families": {"audience": "families served", "focus": "family support services", "records": "referrals, resource requests, or follow-ups"},
    "Health": {"audience": "patients and community members", "focus": "health outreach programs", "records": "outreach events, screenings, or referrals"},
    "Environment": {"audience": "volunteers and community members", "focus": "cleanup and conservation events", "records": "events, sites, or volunteer turnout"},
    "Other": {"audience": "the people you serve", "focus": "your programs", "records": "tasks, requests, or follow-ups"},
}


def _mission_context(mission: str) -> dict[str, str]:
    return MISSION_CONTEXT.get(mission, MISSION_CONTEXT["Other"])


def _task_pattern(problem: str, mission: str) -> dict[str, Any] | None:
    """Pick a new-build pattern from the task described, worded for the mission audience."""
    context = _mission_context(mission)
    if re.search(r"\b(videos?|youtube|vlogs?|filming|film|screencasts?)\b", problem, re.IGNORECASE):
        return {
            "id": "new-video-content-kit",
            "problem_type": "Educational video production" if mission == "Education" else "Video content production",
            "solution": f"A repeatable short-video kit for {context['audience']}: a script and storyboard template, simple phone or screen recording, quick edits in Canva or Clipchamp, and an organized playlist staff can keep adding to.",
            "why_this_solution": f"The request is about creating videos for {context['focus']}, so a reusable recording and editing workflow fits better than a data tracker.",
            "tools": ["Canva or Clipchamp", "YouTube (unlisted) or Google Drive", "Google Docs script template"],
            "skills": ["Canva/Graphics", "UX design"],
            "steps": ["Pick the first 3 video topics", "Create a script and storyboard template", "Record and edit a pilot video with staff", "Set up the playlist and train staff to publish"],
            "estimated_build_hours": 10,
            "privacy_notes": "Get written consent before recording anyone, avoid showing minors' faces or names, and keep drafts in restricted folders.",
        }
    if re.search(r"\b(flyers?|posters?|social media|instagram|facebook|graphics?|brochures?|newsletters?|marketing)\b", problem, re.IGNORECASE):
        return {
            "id": "new-outreach-graphics-kit",
            "problem_type": "Outreach design templates",
            "solution": f"A Canva brand kit with editable flyer, social post, and newsletter templates so staff can promote {context['focus']} to {context['audience']} without starting from scratch.",
            "why_this_solution": "The request is about outreach materials, so reusable design templates save the most staff time.",
            "tools": ["Canva (free for nonprofits)"],
            "skills": ["Canva/Graphics", "UX design"],
            "steps": ["Collect logo, colors, and example posts", "Build the brand kit", "Create 3-5 editable templates", "Show staff how to reuse them"],
            "estimated_build_hours": 6,
            "privacy_notes": "Only use photos of people who have given consent, and never include personal details in public posts.",
        }
    if re.search(r"\b(website|web site|webpage|web page|landing page)\b", problem, re.IGNORECASE):
        return {
            "id": "new-simple-website",
            "problem_type": "Website update workflow",
            "solution": f"A simple, accessible website on a no-code builder with pages staff can update themselves, focused on what {context['audience']} need to find about {context['focus']}.",
            "why_this_solution": "The request is about a website, so a no-code builder keeps it maintainable by staff after the volunteer leaves.",
            "tools": ["WordPress, Squarespace, or Wix"],
            "skills": ["WordPress/Squarespace/Wix", "Web design (HTML/CSS)", "UX design"],
            "steps": ["List the pages and key information", "Set up the site and templates", "Build and test with sample content", "Train staff to edit pages"],
            "estimated_build_hours": 12,
        }
    if re.search(r"\b(surveys?|feedback|evaluations?|questionnaires?)\b", problem, re.IGNORECASE):
        return {
            "id": "new-feedback-survey",
            "problem_type": "Feedback collection and summary",
            "solution": f"A short feedback form for {context['audience']} that feeds a sheet with an automatic summary of results for {context['focus']}.",
            "why_this_solution": "The request is about gathering feedback, so a form with a built-in summary gives staff answers without manual tallying.",
            "tools": ["Google Forms", "Google Sheets"],
            "skills": ["Google Sheets/Excel", "Data analysis"],
            "steps": ["Agree on 5-8 questions", "Build the form", "Create the summary sheet", "Test and share the link"],
            "estimated_build_hours": 6,
            "privacy_notes": "Make responses anonymous where possible and restrict access to the response sheet.",
        }
    return None


def fallback_scope(
    organization: str,
    mission: str,
    comfort: str,
    problem: str,
    templates: list[dict[str, Any]],
) -> dict[str, Any]:
    ranked_library = sorted(
        ((library_similarity(problem, template), template) for template in templates),
        key=lambda item: item[0],
        reverse=True,
    )
    library_similarity_score, library_match = ranked_library[0] if ranked_library else (0, None)
    if library_similarity_score < MINIMUM_REUSE_SIMILARITY:
        library_match = None
    # A clearly described task (videos, graphics, website, feedback) outranks incidental keyword overlap.
    clear_task = _task_pattern(problem, mission) is not None
    if clear_task and library_similarity_score < 88:
        library_match = None
    seed_pattern = None if clear_task else _keyword_template(problem, SEED_TEMPLATES)
    solution_pattern = library_match or seed_pattern
    food_distribution = bool(
        not library_match
        and re.search(r"\b(distribut\w*|deliver\w*)\b", problem, re.IGNORECASE)
        and re.search(r"\b(food|meal|pantry)\b", problem, re.IGNORECASE)
    )
    if food_distribution:
        solution_pattern = {
            "id": "new-food-distribution-coordination",
            "problem_type": "Food distribution volunteer coordination",
            "solution": "A weekly volunteer roster with distribution shifts, assigned locations, and a simple confirmation checklist, so coordinators can see who is covering each food delivery.",
            "why_this_solution": "This addresses coordinating volunteers for food distribution, rather than combining volunteer spreadsheets.",
            "tools": ["Google Sheets", "Google Forms"],
            "skills": ["Google Sheets/Excel", "Data analysis"],
            "steps": ["List distribution shifts and locations", "Collect volunteer availability", "Assign and confirm coverage", "Share a weekly roster with coordinators"],
            "estimated_build_hours": 8,
        }
    if solution_pattern is None:
        if mission == "Animals" and re.search(r"\b(website|web site|site)\b", problem, re.IGNORECASE):
            solution_pattern = {
                "id": "new-animal-shelter-website",
                "problem_type": "Accessible shelter website workflow",
                "solution": "Build a focused, accessible website workflow that lets shelter staff keep approved pet and intake information current.",
                "why_this_solution": "No existing library solution covers this shelter website need, so this is scoped as a new build.",
                "tools": ["Web design tools"],
                "skills": ["Web design (HTML/CSS)", "UX design"],
                "steps": ["Review current site needs", "Design the staff update flow", "Build and test with sample content", "Document maintenance steps"],
                "estimated_build_hours": 18,
            }
        elif re.search(r"\b(book|books|library|catalog|catalogue|inventory)\b", problem, re.IGNORECASE):
            solution_pattern = {
                "id": "new-book-inventory",
                "problem_type": "Book inventory organization",
                "solution": "A shared book inventory sheet with title, category, location, and status, so staff can sort, label, and find books.",
                "why_this_solution": "The request is about organizing books, so a simple searchable catalog is a closer fit than an attendance workflow.",
                "tools": ["Google Sheets"],
                "skills": ["Google Sheets/Excel", "Data analysis"],
                "steps": ["Agree on book categories", "Create the inventory sheet", "Add and check an initial set of books", "Show staff how to update the catalog"],
                "estimated_build_hours": 6,
            }
        else:
            solution_pattern = _task_pattern(problem, mission)
        if solution_pattern is None:
            context = _mission_context(mission)
            solution_pattern = {
                "id": "new-general-workflow",
                "problem_type": "Workflow improvement",
                "solution": f"Map the steps described, then set up a simple staff-editable tracker or checklist for {context['focus']}, such as {context['records']}. Confirm fields and access with staff before building.",
                "why_this_solution": f"No existing pattern clearly matches this request, so this starts with a small discovery step and a tracker shaped around {context['focus']}.",
                "tools": ["Google Sheets/Excel"],
                "skills": ["Google Sheets/Excel", "Data analysis"],
                "steps": ["Confirm the current steps with staff", "Agree on the minimum fields", "Build a small test version", "Review privacy and train staff"],
                "estimated_build_hours": 8,
            }
    similarity = library_similarity_score if library_match else 0
    summary = problem.strip().rstrip(".?!")
    return {
        "problem_summary": summary[:240],
        "problem_type": solution_pattern["problem_type"],
        "hours_wasted_per_week": 3,
        "suggested_solution": solution_pattern["solution"],
        "why_this_solution": solution_pattern.get("why_this_solution", "This is a small, familiar-tool workflow that staff can maintain without a custom app."),
        "advanced_alternative": "A custom application, only if the workflow grows beyond the simple version.",
        "tools": solution_pattern["tools"],
        "skills": solution_pattern["skills"],
        "difficulty": "Beginner" if comfort == "None" else "Intermediate",
        "effort_hours": 1 if library_match else int(solution_pattern.get("estimated_build_hours", 8)),
        "deliverables": solution_pattern["steps"][:5],
        "privacy_notes": solution_pattern.get("privacy_notes", "Use sample data while building. Restrict access to any personal or sensitive records."),
        "matching_template_id": library_match["id"] if library_match else None,
        "library_match_similarity": similarity,
        "reuse_reason": f"This existing data-free pattern is {similarity}% similar; about one hour is needed to customize it." if library_match else "",
    }


def scope_problem(
    organization: str,
    mission: str,
    comfort: str,
    problem: str,
    templates: list[dict[str, Any]],
) -> tuple[dict[str, Any], str | None]:
    """Scope a request with Claude, falling back to transparent keyword rules."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return fallback_scope(organization, mission, comfort, problem, templates), None

    catalog = [
        {key: template[key] for key in ("id", "title", "problem_type", "solution", "skills", "data_free")}
        for template in templates
    ]
    prompt = f"""You help small nonprofits turn a technology pain point into a small, volunteer-ready project.
Organization: {organization}. Mission: {mission}. Staff tech comfort: {comfort}.
Problem: {problem}

Existing library (every entry is a data-free template, not nonprofit records):
{json.dumps(catalog, ensure_ascii=True)}

First identify the actual task and friction described. Keep problem_summary and suggested_solution directly aligned with that task; do not choose a solution based only on mission area. Then tailor suggested_solution, tools, and skills to the mission area's audience (for example, learners for Education, adopters for Animals). If the description is ambiguous, propose a small discovery step instead of an unrelated project. Prefer the simplest tools staff can maintain. Keep a new build under 25 volunteer hours. Compare against the library and estimate library_match_similarity from 0 to 100. Only return a matching_template_id if similarity is at least {MINIMUM_REUSE_SIMILARITY}; otherwise use null. A reused solution takes about 1 volunteer hour to customize. Use skills only from this fixed list: {json.dumps(SKILLS)}.
Flag personal or sensitive data and how to protect it. Return ONLY one JSON object with keys: problem_summary, problem_type, hours_wasted_per_week (integer), suggested_solution, why_this_solution, advanced_alternative (string), tools (list), skills (list), difficulty (Beginner|Intermediate|Advanced), effort_hours (integer), deliverables (3-5 strings), privacy_notes, matching_template_id (id or null), library_match_similarity (integer), reuse_reason (string)."""
    try:
        result = _extract_json(_anthropic_text(prompt))
        if not isinstance(result, dict):
            raise ValueError("Expected a JSON object")
        return validate_scope(result, templates), "claude"
    except Exception as error:  # API, parsing, and validation failures all use the demo-safe fallback.
        return fallback_scope(organization, mission, comfort, problem, templates), str(error)


def validate_scope(result: dict[str, Any], templates: list[dict[str, Any]]) -> dict[str, Any]:
    allowed_ids = {template["id"] for template in templates if template.get("data_free")}
    def text_list(value: Any, limit: int) -> list[str]:
        if not isinstance(value, list):
            return []
        return [item.strip()[:300] for item in value if isinstance(item, str) and item.strip()][:limit]

    skills = [skill for skill in text_list(result.get("skills"), len(SKILLS)) if skill in SKILLS]
    deliverables = text_list(result.get("deliverables"), 5)
    if len(deliverables) < 3:
        deliverables = (deliverables + ["Review the workflow with staff", "Test with sample data", "Write a short handoff guide"])[:3]
    try:
        effort = int(result.get("effort_hours", 8))
    except (TypeError, ValueError):
        effort = 8
    effort = min(max(effort, 1), 24)
    try:
        hours_wasted = int(result.get("hours_wasted_per_week", 0) or 0)
    except (TypeError, ValueError):
        hours_wasted = 0
    template_id = result.get("matching_template_id")
    if template_id not in allowed_ids:
        template_id = None
    try:
        similarity = max(0, min(int(result.get("library_match_similarity", 0) or 0), 100))
    except (TypeError, ValueError):
        similarity = 0
    if similarity < MINIMUM_REUSE_SIMILARITY:
        template_id = None
    if template_id is None:
        similarity = 0
    return {
        "problem_summary": str(result.get("problem_summary", ""))[:500],
        "problem_type": str(result.get("problem_type", "Workflow improvement"))[:120],
        "hours_wasted_per_week": max(0, min(hours_wasted, 168)),
        "suggested_solution": str(result.get("suggested_solution", ""))[:1200],
        "why_this_solution": str(result.get("why_this_solution", ""))[:800],
        "advanced_alternative": str(result.get("advanced_alternative", ""))[:800],
        "tools": text_list(result.get("tools"), 8),
        "skills": skills,
        "difficulty": result.get("difficulty") if result.get("difficulty") in {"Beginner", "Intermediate", "Advanced"} else "Beginner",
        "effort_hours": effort,
        "deliverables": deliverables,
        "privacy_notes": str(result.get("privacy_notes", "Use sample data and restrict access to personal records."))[:1000],
        "matching_template_id": template_id,
        "library_match_similarity": similarity,
        "reuse_reason": str(result.get("reuse_reason", ""))[:500],
    }


def extract_bio_skills(bio: str) -> tuple[list[str], str | None]:
    if not bio.strip():
        return [], None
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return _fallback_bio_skills(bio), None
    prompt = f"Map this volunteer bio to exact skill names from the list only. Return ONLY a JSON array. Skills: {json.dumps(SKILLS)}\nBio: {bio}"
    try:
        result = _extract_json(_anthropic_text(prompt, max_tokens=400))
        if isinstance(result, list):
            return [skill for skill in result if skill in SKILLS], None
        raise ValueError("Expected a JSON list")
    except Exception as error:
        return _fallback_bio_skills(bio), str(error)


def _fallback_bio_skills(bio: str) -> list[str]:
    text = bio.casefold()
    aliases = {
        "Google Sheets/Excel": ["spreadsheet", "google sheets", "excel"],
        "Apps Script": ["apps script", "google apps script"],
        "Airtable/No-code": ["airtable", "no-code", "no code"],
        "Zapier/Make automation": ["zapier", "make.com", "automation"],
        "Python": ["python"],
        "SQL/Databases": ["sql", "database"],
        "Power BI/Tableau": ["power bi", "tableau"],
        "Data analysis": ["data analysis", "analytics"],
        "Web design (HTML/CSS)": ["html", "css", "web design"],
        "WordPress/Squarespace/Wix": ["wordpress", "squarespace", "wix"],
        "JavaScript/React": ["javascript", "react"],
        "UX design": ["ux", "user experience"],
        "Canva/Graphics": ["canva", "graphic design"],
        "Mobile apps": ["mobile app", "ios", "android"],
        "CRM setup (e.g., HubSpot/Salesforce Nonprofit)": ["crm", "salesforce", "hubspot"],
    }
    return [skill for skill, phrases in aliases.items() if any(phrase in text for phrase in phrases)]


def score_students(
    project: dict[str, Any],
    students: list[dict[str, Any]],
    projects: list[dict[str, Any]] | None = None,
    limit: int | None = 3,
) -> list[dict[str, Any]]:
    required = list(dict.fromkeys(project.get("skills", [])))
    active_assignments: dict[str, int] = {}
    for active_project in projects or []:
        student_id = active_project.get("assigned_student_id")
        if student_id and active_project.get("status") in {"Matched", "In progress", "Ready for review"}:
            active_assignments[student_id] = active_assignments.get(student_id, 0) + 1
    ranked = []
    for student in students:
        check = assignment_check(student, project)
        if not check["ok"]:
            continue  # Hidden: doesn't meet this project's rule (or paused).
        matched = sorted(set(required) & set(student.get("skills", [])))
        fit = skill_score(student, project)
        enough_time = int(student.get("hours_per_week", 0)) * 4 >= int(project.get("effort_hours", 0))
        cause_matches = set(project.get("mission_area", "").casefold().split()) & {
            word for cause in student.get("causes", []) for word in cause.casefold().split()
        }
        cause_fit = project.get("mission_area", "").casefold() in {
            cause.casefold() for cause in student.get("causes", [])
        }
        advanced_fit = project.get("difficulty") != "Advanced" or int(student.get("year") or 1) >= 3
        score = 0.6 * fit + 0.2 * int(enough_time) + 0.1 * int(cause_fit or bool(cause_matches)) + 0.1 * int(advanced_fit)
        reasons = [f"{len(matched)}/{len(required)} skills"] if required else ["open to all skills"]
        reasons.append(f"{student.get('hours_per_week', 0)} hrs/wk" + (" covers effort" if enough_time else "; limited availability"))
        reasons.append("mission match" if cause_fit or cause_matches else "cause interests differ")
        active_count = active_assignments.get(student.get("id"), 0)
        reasons.append(f"{active_count} active assignments")
        ranked.append({
            "student": student,
            "score": round(score, 4),
            "skill_coverage": fit,
            "active_assignments": active_count,
            "reason": " · ".join(reasons),
            "why": check["why"],
            "skill_proofs": format_skill_proofs(student),
            "matched_skills": matched,
        })
    return sorted(
        ranked,
        key=lambda item: (
            item["score"],
            int(item["student"].get("year") or 1),
            -item["active_assignments"],
        ),
        reverse=True,
    )[:limit]


APP_BASE_URL = os.environ.get("TECH_BRIDGE_BASE_URL", "http://localhost:8501")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def volunteer_portal_link(token: str, base_url: str = APP_BASE_URL) -> str:
    return f"{base_url.rstrip('/')}/?{urlencode({'invite': token})}"


DEMO_EMAIL_DOMAINS = {"example.org", "example.com", "example.net"}


def send_invitation_email(invitation: dict[str, Any]) -> str:
    """Send the invitation over SMTP when configured; otherwise it stays in the demo inbox. Returns a delivery status."""
    return send_email(invitation.get("to", ""), invitation.get("subject", ""), invitation.get("body", ""))


def send_email(to: str, subject: str, body: str) -> str:
    """Send a plain-text email over SMTP when configured. Returns a delivery status; never raises."""
    recipient = (to or "").strip()
    host = os.environ.get("SMTP_HOST", "").strip()
    if not recipient:
        return "Demo inbox only (no email on file)"
    if recipient.rsplit("@", 1)[-1].casefold() in DEMO_EMAIL_DOMAINS:
        return "Demo inbox only (demo address)"
    if not host:
        return "Demo inbox only (email not configured)"
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USERNAME", "")
    message["To"] = recipient
    message.set_content(body)
    try:
        with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=15) as server:
            server.starttls()
            if os.environ.get("SMTP_USERNAME"):
                server.login(os.environ["SMTP_USERNAME"], os.environ.get("SMTP_PASSWORD", ""))
            server.send_message(message)
    except Exception as error:  # Delivery problems must not block the offer flow.
        return f"Email failed: {error.__class__.__name__}"
    return "Emailed"


def find_invitation_by_token(project: dict[str, Any], token: str) -> dict[str, Any] | None:
    return next(
        (item for item in project.get("invitations", []) if item.get("token") and secrets.compare_digest(item["token"], token)),
        None,
    )


def library_link(query: str, base_url: str = APP_BASE_URL) -> str:
    return f"{base_url.rstrip('/')}/?{urlencode({'library_search': query})}"


def search_library(
    query: str,
    templates: list[dict[str, Any]],
    limit: int | None = None,
) -> list[tuple[int, dict[str, Any]]]:
    """Rank library templates by shared terms with the query; an empty query lists everything."""
    query_terms = _similarity_terms(query or "")
    if not query_terms:
        return [(0, template) for template in templates][:limit]
    ranked = []
    for template in templates:
        template_text = " ".join([
            template.get("title", ""), template.get("problem_type", ""), template.get("solution", ""),
            template.get("mission_area", ""), " ".join(template.get("keywords", [])),
            " ".join(template.get("tools", [])), " ".join(template.get("skills", [])),
        ])
        shared = len(query_terms & _similarity_terms(template_text))
        if shared:
            ranked.append((round(100 * shared / len(query_terms)), template))
    ranked.sort(key=lambda item: (item[0], int(item[1].get("reuse_count", 0))), reverse=True)
    return ranked[:limit]


def compose_invitation(
    project: dict[str, Any],
    volunteer: dict[str, Any],
    base_url: str = APP_BASE_URL,
) -> dict[str, Any]:
    link = library_link(project.get("problem_type", ""), base_url)
    token = secrets.token_urlsafe(24)
    portal = volunteer_portal_link(token, base_url)
    deliverables = "\n".join(f"- {item}" for item in project.get("deliverables", []))
    body = (
        f"Hi {volunteer.get('name', 'there')},\n\n"
        f"{project.get('organization', 'A nonprofit')} needs help with: {project.get('problem_summary', '')}\n\n"
        f"Suggested solution: {project.get('suggested_solution', '')}\n"
        f"Skills: {', '.join(project.get('skills', [])) or 'Open to all skills'}\n"
        f"Estimated effort: {project.get('effort_hours', 0)} volunteer hours · Difficulty: {project.get('difficulty', 'Beginner')}\n"
        f"Privacy: {project.get('privacy_notes', '')}\n\n"
        f"Deliverables:\n{deliverables}\n\n"
        f"Before you start, check the solution library for a similar past project you can reuse:\n{link}\n\n"
        f"Accept or decline here (this private link is just for you):\n{portal}\n\n"
        "If you decline, the project goes to the next matching volunteer. "
        "If you accept, use the same link to track the work and submit a data-free version to the library when you're done."
    )
    return {
        "id": uuid4().hex,
        "student_id": volunteer.get("id"),
        "student_name": volunteer.get("name", ""),
        "to": volunteer.get("email", ""),
        "subject": f"Volunteer project: {project.get('problem_type', 'Tech Bridge project')}",
        "body": body,
        "library_link": link,
        "token": token,
        "portal_link": portal,
        "sent_at": _now(),
        "status": "Pending",
    }


def pending_invitation(project: dict[str, Any]) -> dict[str, Any] | None:
    return next((item for item in project.get("invitations", []) if item.get("status") == "Pending"), None)


def offer_next_volunteer(
    project: dict[str, Any],
    students: list[dict[str, Any]],
    projects: list[dict[str, Any]] | None = None,
    student_id: str | None = None,
    base_url: str = APP_BASE_URL,
) -> dict[str, Any] | None:
    """Email the project card to the best remaining match (or a chosen one) and mark the project Offered."""
    if project.get("assigned_student_id") or pending_invitation(project):
        return None
    declined = set(project.get("declined_student_ids", []))
    eligible = [
        match for match in score_students(project, students, projects, limit=None)
        if match["student"].get("id") not in declined and match["student"].get("confidentiality_signed", False)
    ]
    if student_id:
        eligible = [match for match in eligible if match["student"].get("id") == student_id]
    if not eligible:
        project["status"] = "Open"
        return None
    invitation = compose_invitation(project, eligible[0]["student"], base_url)
    invitation["delivery"] = send_invitation_email(invitation)
    project.setdefault("invitations", []).append(invitation)
    project["status"] = "Offered"
    return invitation


class AssignmentBlocked(ValueError):
    """The volunteer doesn't meet this project's assignment rule."""


def assign_volunteer(
    project: dict[str, Any],
    volunteer: dict[str, Any],
    students: list[dict[str, Any]],
    projects: list[dict[str, Any]] | None = None,
    base_url: str = APP_BASE_URL,
) -> dict[str, Any]:
    """Offer the project to one chosen volunteer, or raise AssignmentBlocked with the reason."""
    check = assignment_check(volunteer, project)
    if not check["ok"]:
        raise AssignmentBlocked(check["reason"])
    if not volunteer.get("confidentiality_signed", False):
        raise AssignmentBlocked("Needs a signed confidentiality agreement")
    if project.get("assigned_student_id") or pending_invitation(project):
        raise AssignmentBlocked("This project already has a volunteer or a pending offer")
    if volunteer.get("id") in project.get("declined_student_ids", []):
        raise AssignmentBlocked("They already declined this project")
    invitation = offer_next_volunteer(project, students, projects, student_id=volunteer["id"], base_url=base_url)
    if invitation is None:
        raise AssignmentBlocked("They can't be offered this project right now")
    return invitation


def respond_to_offer(
    project: dict[str, Any],
    accepted: bool,
    students: list[dict[str, Any]],
    projects: list[dict[str, Any]] | None = None,
    base_url: str = APP_BASE_URL,
) -> dict[str, Any] | None:
    """Record the volunteer's reply. Accepting assigns them; declining offers the next match, which is returned."""
    invitation = pending_invitation(project)
    if invitation is None:
        return None
    invitation["responded_at"] = _now()
    if accepted:
        invitation["status"] = "Accepted"
        project["assigned_student_id"] = invitation["student_id"]
        project["status"] = "In progress"
        return None
    invitation["status"] = "Declined"
    project.setdefault("declined_student_ids", []).append(invitation["student_id"])
    project["status"] = "Open"
    return offer_next_volunteer(project, students, projects, base_url=base_url)


REVIEW_STATUS = "Ready for review"
ACTIVE_STATUSES = {"Matched", "In progress", REVIEW_STATUS}
HANDOFF_CHECKLIST = [
    "Ownership of every file, form, and account is transferred to the nonprofit",
    "My personal access has been removed or will be removed after review",
    "Only sample data was used while building",
    "The nonprofit's staff can open every link above",
]


def submit_completion(
    project: dict[str, Any],
    links: list[str],
    summary: str,
    how_to_use: str,
    notes: str,
    checklist: list[str],
    volunteer_name: str,
) -> dict[str, Any]:
    """Volunteer hands the work over; the nonprofit must review before it counts as done."""
    completion = {
        "links": [link.strip() for link in links if link.strip()],
        "summary": summary.strip(),
        "how_to_use": how_to_use.strip(),
        "notes": notes.strip(),
        "checklist": [item for item in checklist if item in HANDOFF_CHECKLIST],
        "submitted_by": volunteer_name,
        "submitted_at": _now(),
    }
    project["completion"] = completion
    project["status"] = REVIEW_STATUS
    return completion


def request_changes(project: dict[str, Any], comment: str) -> None:
    project.setdefault("change_requests", []).append({"comment": comment.strip(), "requested_at": _now()})
    project["status"] = "In progress"
    project.pop("mentor_approval", None)  # The changed work needs a fresh review.


MENTOR_APPROVAL_REQUIRED = "This volunteer is Supervised: a Mentor must click \"Mentor approved\" before the project can be marked done."


def require_mentor_approval(project: dict[str, Any], volunteer: dict[str, Any] | None = None) -> None:
    """Supervised volunteers' work needs 'Mentor approved' before Done; for Trusted volunteers it's optional."""
    if project.get("status") != "Done" and not project.get("mentor_approval") and mentor_review_required(volunteer):
        raise ValueError(MENTOR_APPROVAL_REQUIRED)


def completion_notice(project: dict[str, Any], review_link: str) -> tuple[str, str]:
    completion = project.get("completion", {})
    links = "\n".join(f"- {link}" for link in completion.get("links", [])) or "- (no links provided)"
    subject = f"Ready for review: {project.get('problem_type', 'volunteer project')}"
    body = (
        f"{completion.get('submitted_by', 'Your volunteer')} has finished \"{project.get('problem_summary', '')}\" and handed it over for your review.\n\n"
        f"What was built:\n{completion.get('summary', '')}\n\n"
        f"Where to find it:\n{links}\n\n"
        f"How to use it:\n{completion.get('how_to_use', '')}\n\n"
        f"Review it, then confirm it's complete or request changes on the Matchboard:\n{review_link}\n\n"
        "After you confirm, you can add a data-free version to the shared library."
    )
    return subject, body


def changes_requested_notice(project: dict[str, Any], comment: str, portal_link: str) -> tuple[str, str]:
    subject = f"Changes requested: {project.get('problem_type', 'volunteer project')}"
    body = (
        f"{project.get('organization', 'The nonprofit')} reviewed your handoff and asked for changes:\n\n{comment}\n\n"
        f"Update the work, then submit the handoff again here:\n{portal_link}"
    )
    return subject, body


def choose_starting_point(project: dict[str, Any], template: dict[str, Any] | None) -> None:
    """Volunteer picks a library match to customize, or builds from scratch."""
    if template is None:
        if project.get("reuse_template_id"):
            project["effort_hours"] = int(project.get("build_effort_hours", project.get("effort_hours", 1)))
        project["reuse_template_id"] = None
        return
    if not project.get("reuse_template_id"):
        project["build_effort_hours"] = int(project.get("build_effort_hours", project.get("effort_hours", 1)))
    project["reuse_template_id"] = template["id"]
    project["effort_hours"] = 1
    project["build_effort_hours"] = int(template.get("estimated_build_hours", project["build_effort_hours"]))


def record_template_reuse(templates: list[dict[str, Any]], template_id: str) -> bool:
    for template in templates:
        if template.get("id") == template_id:
            template["reuse_count"] = int(template.get("reuse_count", 0)) + 1
            return True
    return False


def complete_project(
    project: dict[str, Any],
    templates: list[dict[str, Any]],
    handoff_guide: str,
    volunteer: dict[str, Any] | None = None,
) -> None:
    require_mentor_approval(project, volunteer)
    if project.get("status") != "Done" and project.get("reuse_template_id"):
        record_template_reuse(templates, project["reuse_template_id"])
    project["status"] = "Done"
    project["handoff_guide"] = handoff_guide


def organization_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").casefold())


def projects_for_organization(projects: list[dict[str, Any]], organization_name: str) -> list[dict[str, Any]]:
    key = organization_key(organization_name)
    return [project for project in projects if organization_key(project.get("organization", "")) == key]


def impact_summary(
    projects: list[dict[str, Any]],
    templates: list[dict[str, Any]],
) -> dict[str, int | float | str]:
    completed = [project for project in projects if project.get("status") == "Done"]
    reused = [project for project in completed if project.get("reuse_template_id")]
    contributed = sum(
        int(project.get("effort_hours", 0))
        for project in projects if project.get("status") in {"In progress", "Ready for review", "Done"}
    )
    proven_solutions = [
        template for template in templates
        if template.get("data_free") and template.get("source_project_status") == "Done"
    ]
    most_reused = max(proven_solutions, key=lambda template: int(template.get("reuse_count", 0)), default=None)
    reuse_count = int(most_reused.get("reuse_count", 0)) if most_reused else 0
    nonprofits_reached = 1 + reuse_count if most_reused else 0
    nonprofit_label = "nonprofit" if nonprofits_reached == 1 else "nonprofits"
    headline = (
        f"{most_reused['title']}: 1 volunteer project -> {nonprofits_reached} {nonprofit_label} helped"
        if most_reused else "No completed reusable solutions yet"
    )
    reuse_reaches = [1 + int(template.get("reuse_count", 0)) for template in proven_solutions]
    return {
        "new_builds": sum(1 for project in completed if not project.get("reuse_template_id")),
        "nonprofits_helped": len({project.get("organization") for project in completed if project.get("organization")}),
        "staff_hours_saved_per_week": sum(int(project.get("hours_wasted_per_week", 0)) for project in completed),
        "volunteer_hours_saved_by_reuse": sum(
            max(0, int(project.get("build_effort_hours", project.get("effort_hours", 0))) - int(project.get("effort_hours", 0)))
            for project in reused
        ),
        "volunteer_hours_contributed": contributed,
        "volunteer_time_value": round(contributed * VOLUNTEER_HOURLY_VALUE, 2),
        "projects_posted": len(projects),
        "projects_matched": sum(1 for project in projects if project.get("status") in {"Matched", "In progress", "Ready for review", "Done"}),
        "projects_completed": len(completed),
        "headline_volunteer_projects": 1 if most_reused else 0,
        "headline_nonprofits_helped": nonprofits_reached,
        "headline": headline,
        "average_reuse_reach": round(
            sum(reuse_reaches) / len(reuse_reaches), 1
        ) if reuse_reaches else 0.0,
    }


def _completion_sections(completion: dict[str, Any]) -> str:
    sections = ""
    if completion.get("links"):
        sections += "\n## Where to find it\n" + "\n".join(f"- {link}" for link in completion["links"]) + "\n"
    if completion.get("how_to_use"):
        sections += f"\n## How to use it\n{completion['how_to_use']}\n"
    if completion.get("notes"):
        sections += f"\n## Notes from the volunteer\n{completion['notes']}\n"
    return sections


def generate_handoff(project: dict[str, Any], volunteer: dict[str, Any] | None) -> tuple[str, str | None]:
    builder = volunteer.get("name", "the volunteer team") if volunteer else "the volunteer team"
    details = {
        "problem": project.get("problem_summary", ""),
        "solution": project.get("suggested_solution", ""),
        "tools": project.get("tools", []),
        "deliverables": project.get("deliverables", []),
        "privacy_notes": project.get("privacy_notes", ""),
        "volunteer_handoff": project.get("completion", {}),
    }
    if os.environ.get("ANTHROPIC_API_KEY"):
        prompt = f"""Write a concise, plain-language Markdown handoff guide for a nonprofit staff member with {project.get('tech_comfort', 'basic')} tech comfort. Project details: {json.dumps(details, ensure_ascii=True)}. Built by volunteer: {builder}. Include what was built; numbered day-to-day steps; exactly 3 likely problems and fixes; what NOT to change; and who to contact (the volunteer and Tech Bridge). Never invent credentials or real contact details. No jargon."""
        try:
            return _anthropic_text(prompt, max_tokens=1100), None
        except Exception as error:
            warning = str(error)
    else:
        warning = None
    guide = f"""# Project handoff: {project.get('problem_type', 'Workflow project')}

## What was built
{project.get('completion', {}).get('summary') or project.get('suggested_solution', 'A simple workflow for the nonprofit team.')}
{_completion_sections(project.get('completion', {}))}
## Day to day
1. Open the team's approved shared tool.
2. Follow the steps in the deliverables: {'; '.join(project.get('deliverables', []))}.
3. Check the result before sharing or sending anything.

## Three likely problems
1. **A form or link stops working:** check its sharing settings and reconnect the approved destination.
2. **A record looks wrong or duplicated:** pause updates, correct the source row, and test with sample data.
3. **A staff member cannot access it:** ask the organization administrator to grant access; do not make the file public.

## What not to change
Do not broaden access to personal records, remove review steps, or change automations before testing with sample data.

## Privacy reminder
{project.get('privacy_notes', 'Use the minimum data needed and limit access to authorized staff.')}

## Who to contact
For this project, contact {builder} through the nonprofit's agreed channel. For program support, contact the Tech Bridge project coordinator.
"""
    return guide, warning


def _scrub_known_private_text(text: str, project: dict[str, Any], builder: str) -> str:
    for private_value in (project.get("organization", ""), builder):
        if private_value:
            text = re.sub(re.escape(private_value), "[name removed]", text, flags=re.IGNORECASE)
    for pattern, replacement in PRIVATE_TEXT_REDACTIONS:
        text = pattern.sub(replacement, text)
    return text.strip()


def sanitize_library_draft(
    project: dict[str, Any], builder: str,
) -> tuple[dict[str, Any], str | None]:
    """Prepare a generic library template and guide; require human review before publication."""
    details = {
        "organization_to_remove": project.get("organization", ""),
        "volunteer_name_to_remove_from_content": builder,
        "problem_summary": project.get("problem_summary", ""),
        "problem_type": project.get("problem_type", ""),
        "solution": project.get("suggested_solution", ""),
        "tools": project.get("tools", []),
        "skills": project.get("skills", []),
        "steps": project.get("deliverables", []),
    }
    warning = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        prompt = f"""Prepare a public, reusable solution-library draft from this project. The data below is private; do not repeat the organization name, volunteer name, any person name, email, phone number, record, credential, or organization-specific detail. Keep only a generic workflow pattern. Write a plain-language generic handoff guide with numbered steps, 3 common fixes, and what not to change. Return ONLY JSON with keys: title, problem_type, summary, tools (list), skills (list from this fixed list only), keywords (list of generic search terms), steps (list), handoff_guide (Markdown). Fixed skills: {json.dumps(SKILLS)}. Private project details: {json.dumps(details, ensure_ascii=True)}"""
        try:
            result = _extract_json(_anthropic_text(prompt, max_tokens=1200))
            if not isinstance(result, dict):
                raise ValueError("Expected a JSON object")
            raw = {
                "title": result.get("title", "Reusable workflow starter"),
                "problem_type": result.get("problem_type", "Workflow improvement"),
                "summary": result.get("summary", "A simple workflow pattern for a nonprofit team."),
                "tools": result.get("tools", []),
                "skills": result.get("skills", []),
                "keywords": result.get("keywords", []),
                "steps": result.get("steps", []),
                "handoff_guide": result.get("handoff_guide", ""),
            }
        except Exception as error:
            warning = str(error)
            raw = {}
    else:
        raw = {}

    if not raw:
        pattern = _keyword_template(project.get("problem_summary", ""), SEED_TEMPLATES)
        raw = {
            "title": pattern["title"] if pattern else f"{project.get('problem_type', 'Workflow')} starter",
            "problem_type": pattern["problem_type"] if pattern else project.get("problem_type", "Workflow improvement"),
            "summary": pattern["solution"] if pattern else project.get("suggested_solution", "A simple workflow pattern for a nonprofit team."),
            "tools": pattern["tools"] if pattern else project.get("tools", []),
            "skills": pattern["skills"] if pattern else project.get("skills", []),
            "keywords": pattern["keywords"] if pattern else list(_similarity_terms(project.get("problem_type", ""))),
            "steps": pattern["steps"] if pattern else project.get("deliverables", []),
            "handoff_guide": "## Reusable handoff guide\n\n" + (pattern["solution"] if pattern else project.get("suggested_solution", "Use the approved shared tool.")) + "\n\n" + "\n".join(f"{index}. {step}" for index, step in enumerate(pattern["steps"] if pattern else project.get("deliverables", []), start=1)) + "\n\nTest changes with sample data and keep access restricted to authorized staff.",
        }
        if os.environ.get("ANTHROPIC_API_KEY") and not warning:
            warning = "AI returned no usable draft; a local draft was prepared."
    def clean(value: Any, default: str = "") -> str:
        return _scrub_known_private_text(str(value or default)[:4000], project, builder)

    title = clean(raw.get("title"), "Reusable workflow starter") or "Reusable workflow starter"
    summary = clean(raw.get("summary"), "A simple workflow pattern for a nonprofit team.")
    steps = [clean(step) for step in raw.get("steps", []) if isinstance(step, str) and clean(step)][:8] if isinstance(raw.get("steps"), list) else []
    tools = [clean(tool) for tool in raw.get("tools", []) if isinstance(tool, str) and clean(tool)][:8] if isinstance(raw.get("tools"), list) else []
    skills = [skill for skill in raw.get("skills", []) if isinstance(skill, str) and skill in SKILLS][:len(SKILLS)] if isinstance(raw.get("skills"), list) else []
    keywords = [clean(keyword).casefold() for keyword in raw.get("keywords", []) if isinstance(keyword, str) and clean(keyword)][:12] if isinstance(raw.get("keywords"), list) else []
    guide = clean(raw.get("handoff_guide"), "## Reusable handoff guide\n\nUse the approved shared tool, test with sample data, and keep access restricted.")
    return {
        "title": title,
        "problem_type": clean(raw.get("problem_type"), "Workflow improvement"),
        "summary": summary,
        "tools": tools,
        "skills": skills,
        "keywords": keywords,
        "steps": steps,
        "handoff_guide": guide,
    }, warning


def build_template_from_project(
    project: dict[str, Any], draft: dict[str, Any], builder: str, builder_volunteer_id: str | None = None,
) -> dict[str, Any]:
    """Create a data-free template from the reviewed public draft."""
    return {
        "id": f"tpl-{uuid4().hex[:10]}",
        "title": draft["title"][:100],
        "mission_area": project.get("mission_area", "Other"),
        "keywords": draft["keywords"],
        "problem_type": draft["problem_type"],
        "solution": draft["summary"][:1000],
        "tools": draft["tools"],
        "skills": draft["skills"],
        "steps": draft["steps"][:8],
        "license": "Creative Commons Attribution 4.0 International (CC BY 4.0)",
        "data_free": True,
        "demo_template": False,
        "built_by": builder,
        "reuse_count": 0,
        "estimated_build_hours": int(project.get("build_effort_hours", project.get("effort_hours", 8))),
        "source_project_status": "Done",
        "source_project_title": project.get("problem_type", "Completed volunteer project"),
        "builder_volunteer_id": builder_volunteer_id,
        "origin_staff_hours_per_week": int(project.get("hours_wasted_per_week", 0) or 0),
        "reuse_staff_hours_per_week": 0,
        "handoff_guide": draft["handoff_guide"],
    }


def suggest_thank_you_note(project: dict[str, Any], volunteer: dict[str, Any] | None) -> tuple[str, str | None]:
    """Draft a short thank-you note for the nonprofit to edit. Never includes the nonprofit's name."""
    first_name = (volunteer or {}).get("name", "").split()[0] if (volunteer or {}).get("name") else ""
    fallback = fallback_thank_you_note(project, first_name)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return fallback, None
    details = {
        "what_was_built": project.get("completion", {}).get("summary") or project.get("suggested_solution", ""),
        "problem_type": project.get("problem_type", ""),
        "staff_hours_saved_per_week": project.get("hours_wasted_per_week", 0),
    }
    prompt = f"""Write a warm, specific thank-you note (2-3 sentences, under 60 words) from a nonprofit's staff to a student volunteer named {first_name or 'the volunteer'}. Do not name the nonprofit, any staff member, client, or place. Plain text only, no greeting line or signature. Project: {json.dumps(details, ensure_ascii=True)}"""
    try:
        text = _anthropic_text(prompt, max_tokens=200).strip()
        return (scrub_organization(text, project.get("organization", "")) or fallback), None
    except Exception as error:
        return fallback, str(error)