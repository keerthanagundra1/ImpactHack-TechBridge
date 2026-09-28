"""Volunteer retention: privacy of shared views, positive-only thanks, pause, trust levels, private links."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tech_bridge import SEED_PROJECTS, SEED_STUDENTS, SEED_TEMPLATES, offer_next_volunteer, respond_to_offer, score_students
from tenant_store import (
    complete_workspace_project,
    create_account,
    find_profile_by_impact_token,
    give_star,
    initialize_tenant_store,
    list_notifications,
    load_shared_library,
    load_volunteer_profiles,
    load_workspace,
    respond_to_nudge,
    save_workspace,
    send_project_nudges,
    update_volunteer_settings,
)
from volunteer_retention import (
    certificate_html,
    display_name,
    public_profile,
    volunteer_impact,
)
from onboarding import assignment_check

PROJECT_ROOT = Path(__file__).parents[1]
NGO_NAMES = sorted({project["organization"] for project in SEED_PROJECTS} | {"Oak Cliff", "Oak Cliff Community Pantry"})


def copy(value):
    return json.loads(json.dumps(value))


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "tenants.sqlite3"
    initialize_tenant_store(path, copy(SEED_TEMPLATES))
    return path


@pytest.fixture
def pantry(db):
    """The seeded Oak Cliff pantry: its demo project is Done and was built by Priya."""
    return create_account("Oak Cliff Community Pantry", "pantry@example.org", "pantry-password-123", db)


def profile_named(db, name):
    return next(profile for profile in load_volunteer_profiles(db).values() if profile["name"] == name)


def student_named(students, name):
    return next(student for student in students if student["name"] == name)


def reuse_project(student_id, **extra):
    return {
        "id": "reuse-1", "organization": "Oak Cliff Community Pantry", "mission_area": "Animals",
        "problem_type": "Volunteer data consolidation", "problem_summary": "Merge volunteer sheets for Oak Cliff Community Pantry",
        "skills": ["Google Sheets/Excel"], "effort_hours": 1, "hours_wasted_per_week": 2, "status": "In progress",
        "reuse_template_id": "tpl-volunteer-intake", "assigned_student_id": student_id, "privacy_notes": "Use sample data.",
        "mentor_approval": {"approved_by": "Tech Bridge coordinator", "role": "Coordinator"},
        **extra,
    }


def all_shared_text(db):
    """Every notification (message + email preview) and every public profile, as one string."""
    profiles = load_volunteer_profiles(db)
    library = load_shared_library(db)
    parts = []
    for profile in profiles.values():
        for notification in list_notifications(profile["id"], db):
            parts += [notification["message"], notification["email_subject"], notification["email_body"]]
        parts.append(json.dumps(public_profile(profile, library)))
    return "\n".join(parts)


# ------------------------------------------------------------------ privacy


def test_notifications_email_previews_and_public_profiles_contain_no_ngo_names(db, pantry):
    workspace = load_workspace(pantry["organization_id"], db)
    oak_cliff = next(project for project in workspace["projects"] if not project.get("demo_scenario"))
    noah = student_named(workspace["students"], "Noah Patel")
    workspace["projects"].append(reuse_project(noah["id"]))
    workspace["projects"].append({
        "id": "open-1", "organization": "Oak Cliff Community Pantry", "mission_area": "Food",
        "problem_type": "Volunteer data consolidation", "problem_summary": "Oak Cliff Community Pantry needs a sheet",
        "skills": ["Google Sheets/Excel", "Apps Script"], "effort_hours": 8, "status": "Open", "assigned_student_id": None,
        "privacy_notes": "Use sample data.",
    })
    save_workspace(pantry["organization_id"], workspace["projects"], workspace["students"], db)

    give_star(pantry["organization_id"], oak_cliff["id"], "Oak Cliff Community Pantry thanks you! Call 214-555-0100 or pantry@example.org", db)
    complete_workspace_project(pantry["organization_id"], "reuse-1", "Guide", db)
    workspace = load_workspace(pantry["organization_id"], db)
    assert send_project_nudges(pantry["organization_id"], workspace["projects"][-1], workspace["students"], workspace["projects"], db) > 0

    shared = all_shared_text(db)
    for name in NGO_NAMES:
        assert name.casefold() not in shared.casefold(), name
    assert "214-555-0100" not in shared and "pantry@example.org" not in shared

    priya = profile_named(db, "Priya Shah")
    messages = [item["message"] for item in list_notifications(priya["id"], db)]
    assert any(message.startswith("Your Volunteer Sign-up Sheet just helped an animal shelter. It has now helped 6 nonprofits") for message in messages)
    assert "A nonprofit gave you a star! You earned Google Sheets and Apps Script badges." in messages
    assert all("Oak Cliff" not in note["note"] for note in priya["thank_you_notes"])
    certificate = certificate_html(priya, volunteer_impact(priya, load_shared_library(db)))
    assert not any(name in certificate for name in NGO_NAMES)


def test_public_profile_respects_name_consent(db):
    grace = profile_named(db, "Grace Kim")
    assert grace["show_name_consent"] is False
    assert public_profile(grace, load_shared_library(db)) is None
    priya = profile_named(db, "Priya Shah")
    assert public_profile(priya, load_shared_library(db))["display_name"] == "Priya S." == display_name(priya)


# ------------------------------------------------------------------ thanks


def test_no_badge_is_awarded_without_a_star(db, pantry):
    workspace = load_workspace(pantry["organization_id"], db)
    noah = student_named(workspace["students"], "Noah Patel")
    workspace["projects"].append(reuse_project(noah["id"]))
    save_workspace(pantry["organization_id"], workspace["projects"], workspace["students"], db)
    before = profile_named(db, "Noah Patel")

    complete_workspace_project(pantry["organization_id"], "reuse-1", "Guide", db)
    after = profile_named(db, "Noah Patel")
    assert after["badges"] == before["badges"] and after["stars"] == before["stars"]
    assert not any(item["type"] == "star" for item in list_notifications(after["id"], db))
    assert "thanks" not in next(item for item in load_workspace(pantry["organization_id"], db)["projects"] if item["id"] == "reuse-1")

    starred = give_star(pantry["organization_id"], "reuse-1", "", db)
    after_star = profile_named(db, "Noah Patel")
    assert starred["type"] == "star"
    assert after_star["stars"] == before["stars"] + 1
    assert after_star["badges"]["Google Sheets/Excel"] == before["badges"].get("Google Sheets/Excel", 0) + 1
    with pytest.raises(ValueError):
        give_star(pantry["organization_id"], "reuse-1", "", db)
    assert profile_named(db, "Noah Patel")["stars"] == after_star["stars"]


def test_a_star_needs_a_done_project(db, pantry):
    workspace = load_workspace(pantry["organization_id"], db)
    noah = student_named(workspace["students"], "Noah Patel")
    workspace["projects"].append(reuse_project(noah["id"]))
    save_workspace(pantry["organization_id"], workspace["projects"], workspace["students"], db)
    with pytest.raises(ValueError):
        give_star(pantry["organization_id"], "reuse-1", "", db)
    assert profile_named(db, "Noah Patel")["badges"] == {"Google Sheets/Excel": 1}


# ------------------------------------------------------------------ matching


def test_paused_volunteers_never_appear_in_matches(db, pantry):
    students = copy(SEED_STUDENTS)
    project = {"id": "p", "skills": ["Google Sheets/Excel", "Apps Script"], "effort_hours": 1, "mission_area": "Food",
               "difficulty": "Beginner", "status": "Open", "assigned_student_id": None, "privacy_notes": "Use sample data.",
               "reuse_template_id": "tpl-volunteer-intake"}
    assert "Jacob Miller" not in {match["student"]["name"] for match in score_students(project, students, limit=None)}

    for student in students:
        student["paused"] = student["paused"] or student["name"] in {"Priya Shah", "Noah Patel"}
    names = {match["student"]["name"] for match in score_students(project, students, limit=None)}
    assert names and not names & {"Priya Shah", "Noah Patel", "Jacob Miller"}

    offered = []
    offer_next_volunteer(project, students)
    while project.get("status") == "Offered":
        offered.append(project["invitations"][-1]["student_name"])
        respond_to_offer(project, False, students)
    assert offered and not set(offered) & {"Priya Shah", "Noah Patel", "Jacob Miller"}

    token = profile_named(db, "Daniel Okoye")["impact_token"]
    update_volunteer_settings(token, {"paused": True}, db)
    workspace = load_workspace(pantry["organization_id"], db)
    nudge_project = dict(project, id="nudge", invitations=[])
    send_project_nudges(pantry["organization_id"], nudge_project, workspace["students"], workspace["projects"], db)
    for name in ("Daniel Okoye", "Jacob Miller"):
        assert not any(item["type"] == "nudge" for item in list_notifications(profile_named(db, name)["id"], db))


def test_only_trusted_volunteers_are_matched_to_personal_data():
    base_volunteer = {"id": "v", "name": "Volunteer", "skills": ["Google Sheets/Excel"], "hours_per_week": 10,
                      "causes": ["Food"], "year": 4, "confidentiality_signed": True}
    supervised = dict(base_volunteer, id="supervised", onboarding={"status": "Supervised", "seed_reviewed_tasks": 2})
    trusted = dict(base_volunteer, id="trusted", onboarding={"status": "Supervised", "seed_reviewed_tasks": 3})
    base = {"skills": ["Google Sheets/Excel"], "effort_hours": 1, "mission_area": "Food", "difficulty": "Beginner"}
    personal_projects = [
        dict(base, reuse_template_id="tpl-volunteer-intake", data_sensitivity="Personal data"),
        dict(base, reuse_template_id="tpl-volunteer-intake", privacy_notes="Volunteer phone numbers are personal data."),
        dict(base, privacy_notes="Client health records.", effort_hours=8),
    ]
    for project in personal_projects:
        assert [match["student"]["id"] for match in score_students(project, [supervised, trusted], limit=None)] == ["trusted"]
        assert "needs a Trusted volunteer (2 of 3 reviewed tasks completed)" in assignment_check(supervised, project)["reason"]
    # Supervised volunteers take normal work, both setups and new builds.
    assert len(score_students(dict(base, reuse_template_id="tpl-volunteer-intake"), [supervised, trusted], limit=None)) == 2
    assert len(score_students(dict(base, effort_hours=8, data_sensitivity="Non-sensitive data"), [supervised, trusted], limit=None)) == 2
    assert score_students(personal_projects[0], [dict(trusted, confidentiality_signed=False)], limit=None) == []


# ------------------------------------------------------------------ private links


def test_invalid_impact_token_resolves_to_nothing(db):
    priya = profile_named(db, "Priya Shah")
    token = priya["impact_token"]
    assert find_profile_by_impact_token(token, db)["id"] == priya["id"]
    near_miss = token[:-1] + ("A" if token[-1] != "A" else "B")
    for bad in ["", "short", "x" * 32, near_miss, token.upper() if token.upper() != token else token + "x", None]:
        assert find_profile_by_impact_token(bad, db) is None
        assert update_volunteer_settings(bad, {"paused": True}, db) is None
    assert profile_named(db, "Priya Shah")["paused"] is False
    jordan = profile_named(db, "Jordan Ellis")
    nudge = next(item for item in list_notifications(jordan["id"], db) if item["type"] == "nudge")
    assert respond_to_nudge("x" * 32, nudge["id"], True, db) is None
    assert respond_to_nudge(priya["impact_token"], nudge["id"], True, db) is None  # someone else's nudge
    assert next(item for item in list_notifications(jordan["id"], db) if item["type"] == "nudge")["action"]["response"] is None


def test_invalid_impact_link_page_shows_nothing(tmp_path):
    """Render the real app with a bad ?impact= token: only an error, no volunteer data."""
    script = f"""
import json, os, sys
sys.path.insert(0, {str(PROJECT_ROOT)!r})
os.chdir({str(PROJECT_ROOT)!r})
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("app.py", default_timeout=60)
at.query_params["impact"] = "not-a-real-token-but-long-enough-123"
at.run()
print(json.dumps({{"exceptions": len(at.exception), "errors": [e.value for e in at.error], "titles": len(at.title),
    "metrics": len(at.metric), "buttons": len(at.button), "markdown": [m.value for m in at.markdown if "<style>" not in m.value]}}))
"""
    env = dict(os.environ, TECH_BRIDGE_DATABASE=str(tmp_path / "app.sqlite3"))
    env.pop("ANTHROPIC_API_KEY", None)
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env, timeout=120)
    rendered = json.loads(result.stdout.strip().splitlines()[-1])
    assert rendered == {"exceptions": 0, "errors": ["This link is invalid or no longer active."], "titles": 0,
                        "metrics": 0, "buttons": 0, "markdown": []}


# ------------------------------------------------------------------ demo data and nudges


def test_demo_data_matches_the_story(db, pantry):
    priya = profile_named(db, "Priya Shah")
    library = load_shared_library(db)
    impact = volunteer_impact(priya, library)
    roster = {student["name"]: student for student in load_workspace(pantry["organization_id"], db)["students"]}
    assert priya["demo"] and roster["Priya Shah"]["onboarding_status"] == "Trusted" and priya["stars"] == 6
    assert priya["badges"] == {"Google Sheets/Excel": 5, "Apps Script": 3}
    assert impact["solutions"][0]["title"] == "Volunteer Sign-up Sheet" and impact["solutions"][0]["reuse_count"] == 4
    notifications = list_notifications(priya["id"], db)
    assert sorted(item["type"] for item in notifications) == ["reuse", "reuse", "star"]
    assert all(item["demo"] and item["email_body"] for item in notifications)
    assert len(priya["thank_you_notes"]) == 1
    jordan = profile_named(db, "Jordan Ellis")
    assert roster["Jordan Ellis"]["onboarding_status"] == "Demo sent"
    assert [item["action"]["response"] for item in list_notifications(jordan["id"], db) if item["type"] == "nudge"] == [None]
    assert profile_named(db, "Jacob Miller")["paused"] is True


def test_nudges_are_limited_to_one_per_volunteer_per_week(db, pantry):
    workspace = load_workspace(pantry["organization_id"], db)
    project = {"id": "open-1", "skills": ["Google Sheets/Excel"], "effort_hours": 6, "mission_area": "Food",
               "difficulty": "Beginner", "status": "Open", "assigned_student_id": None, "privacy_notes": "Use sample data."}
    first = send_project_nudges(pantry["organization_id"], project, workspace["students"], workspace["projects"], db)
    second = send_project_nudges(pantry["organization_id"], dict(project, id="open-2"), workspace["students"], workspace["projects"], db)
    assert first > 0 and second == 0
