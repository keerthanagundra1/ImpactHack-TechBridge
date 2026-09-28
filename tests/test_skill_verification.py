"""Skill proof labels: the proof ladder is shown and weights matches, and references stay coordinator-only."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from skill_checks import PRACTICE_TASKS, expected_answers, grade_practice_task
from tech_bridge import SEED_TEMPLATES, SKILLS
from tenant_store import (
    add_skill_evidence,
    complete_workspace_project,
    create_account,
    enrich_profile,
    give_star,
    initialize_tenant_store,
    list_skill_proofs,
    load_volunteer_profiles,
    load_workspace,
    review_demo,
    save_workspace,
)
from volunteer_retention import format_skill_proofs, proof_label, public_profile, skill_score

PROJECT_ROOT = Path(__file__).parents[1]
REFERENCE_SECRETS = ["Dr. Imani Okafor", "i.okafor@example.edu", "972-555-0147"]
SHEETS, POWER_BI = "Google Sheets/Excel", "Power BI/Tableau"


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "tenants.sqlite3"
    initialize_tenant_store(path, json.loads(json.dumps(SEED_TEMPLATES)))
    return path


@pytest.fixture
def pantry(db):
    return create_account("Oak Cliff Community Pantry", "pantry@example.org", "pantry-password-123", db)


def profile_named(db, name):
    return next(profile for profile in load_volunteer_profiles(db).values() if profile["name"] == name)


def test_proof_levels_are_sorted_and_weight_the_match_score():
    project = {"skills": [SHEETS, POWER_BI], "reuse_template_id": "tpl-volunteer-intake"}
    listed = {"skills": [SHEETS, POWER_BI]}
    assert skill_score(listed, project) == pytest.approx(0.2)
    assert skill_score(dict(listed, skill_levels={SHEETS: 2, POWER_BI: 3}), project) == pytest.approx(0.5)
    assert skill_score(dict(listed, badges={SHEETS: 1}, skill_levels={POWER_BI: 3}), project) == pytest.approx(0.8)
    shown = format_skill_proofs({"skills": [SHEETS, POWER_BI, "Python"], "badges": {SHEETS: 5}, "skill_levels": {POWER_BI: 3, "Python": 2}})
    assert shown.index("Nonprofit-verified x5") < shown.index("Skill check passed") < shown.index("Evidence")


def test_every_skill_has_a_demo_task_that_grades_by_rules():
    assert set(PRACTICE_TASKS) == set(SKILLS)
    for skill in SKILLS:
        assert grade_practice_task(skill, expected_answers(skill))["passed"], skill
    result = grade_practice_task(SHEETS, ["9", "4"])
    assert not result["passed"] and result["feedback"].startswith("Not yet")


def test_no_level_4_badge_without_an_ngo_star(db, pantry):
    organization = pantry["organization_id"]
    workspace = load_workspace(organization, db)
    alex = next(student for student in workspace["students"] if student["name"] == "Alex Rivera")
    level_4 = lambda: [proof for proof in list_skill_proofs(alex["volunteer_profile_id"], database_path=db) if proof["level"] == 4]

    add_skill_evidence(alex["volunteer_profile_id"], SHEETS, "Portfolio link", {"link": "https://portfolio.example.org/alex"}, database_path=db)
    review_demo(organization, alex["id"], True, "Clean work.", database_path=db)  # approved demo -> Level 3, not Level 4
    workspace = load_workspace(organization, db)
    workspace["projects"].append({"id": "alex-fix", "status": "In progress", "assigned_student_id": alex["id"], "skills": [SHEETS],
                                  "reuse_template_id": "tpl-volunteer-intake", "mission_area": "Food",
                                  "mentor_approval": {"approved_by": "NGO staff", "role": "NGO staff"}})
    save_workspace(organization, workspace["projects"], workspace["students"], db)
    complete_workspace_project(organization, "alex-fix", "Guide", db)
    assert level_4() == []
    assert proof_label(enrich_profile(profile_named(db, "Alex Rivera"), db), SHEETS) == "Skill check passed"

    give_star(organization, "alex-fix", "", db)
    assert [(proof["skill"], proof["source"]) for proof in level_4()] == [(SHEETS, "Star from a nonprofit")]
    assert proof_label(enrich_profile(profile_named(db, "Alex Rivera"), db), SHEETS) == "Nonprofit-verified x1"
    for profile in load_volunteer_profiles(db).values():
        assert len([proof for proof in list_skill_proofs(profile["id"], database_path=db) if proof["level"] == 4]) == sum(profile.get("badges", {}).values())


# ------------------------------------------------------------------ privacy of references


def test_reference_details_are_coordinator_only_in_data(db, pantry):
    kevin = profile_named(db, "Kevin Tran")
    ngo_proofs = json.dumps(list_skill_proofs(kevin["id"], database_path=db))
    coordinator_proofs = json.dumps(list_skill_proofs(kevin["id"], coordinator=True, database_path=db))
    workspace = json.dumps(load_workspace(pantry["organization_id"], db))
    shared = json.dumps(public_profile(kevin, []))
    for secret in REFERENCE_SECRETS:
        assert secret not in ngo_proofs and secret not in workspace and secret not in shared
        assert secret in coordinator_proofs


def _render(tmp_path, coordinator: bool) -> str:
    script = f"""
import json, os, sys
sys.path.insert(0, {str(PROJECT_ROOT)!r})
os.chdir({str(PROJECT_ROOT)!r})
from streamlit.testing.v1 import AppTest
import tenant_store
account = tenant_store.create_account("Oak Cliff Community Pantry", "pantry@example.org", "pantry-password-123")
at = AppTest.from_file("app.py", default_timeout=120)
at.session_state["tenant_account"] = account
at.session_state["coordinator_mode"] = {coordinator!r}
at.run()
if {coordinator!r}:
    box = at.selectbox(key="volunteer_view_pick")
    box.set_value(next(option for option in box.options if option.startswith("Kevin Tran"))).run()
parts = []
for kind in ("markdown", "caption", "text", "code", "info", "success", "warning", "error", "title", "subheader", "json"):
    parts += [str(getattr(element, "value", "")) for element in getattr(at, kind, [])]
for widget in list(at.selectbox) + list(at.text_input) + list(at.text_area) + list(at.multiselect) + list(at.radio):
    parts += [str(widget.label), str(getattr(widget, "options", "")), str(getattr(widget, "value", ""))]
print(json.dumps({{"exceptions": [e.message for e in at.exception], "text": "\\n".join(parts)}}))
"""
    env = dict(os.environ, TECH_BRIDGE_DATABASE=str(tmp_path / f"app-{coordinator}.sqlite3"))
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("TECH_BRIDGE_COORDINATOR_PASSCODE", None)
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env, timeout=600, encoding="utf-8")
    rendered = json.loads(result.stdout.strip().splitlines()[-1])
    assert rendered["exceptions"] == []
    return rendered["text"]


def test_reference_contact_details_never_appear_in_ngo_facing_views(tmp_path):
    """Render every tab of the signed-in nonprofit app: reference names and contacts never appear."""
    ngo_view = _render(tmp_path, coordinator=False)
    assert "Kevin Tran" in ngo_view  # the volunteer is on the roster...
    for secret in REFERENCE_SECRETS:
        assert secret not in ngo_view  # ...but their reference is not.
    coordinator_view = _render(tmp_path, coordinator=True)
    assert all(secret in coordinator_view for secret in REFERENCE_SECRETS)
