"""NGO-led onboarding: Applicant -> Demo sent -> Approved / Rejected -> Supervised -> Trusted."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from onboarding import (
    REAPPLY_DAYS,
    TRUSTED_TASKS,
    assignment_check,
    reviewed_task_count,
    volunteer_status,
)
from skill_checks import expected_answers
from tech_bridge import SEED_TEMPLATES, AssignmentBlocked, assign_volunteer, score_students
from tenant_store import (
    accept_confidentiality,
    add_application_to_roster,
    approve_as_mentor,
    complete_workspace_project,
    create_account,
    give_star,
    initialize_tenant_store,
    list_applications,
    load_volunteer_profile,
    load_workspace,
    promote_to_mentor,
    review_demo,
    save_workspace,
    send_demo_project,
    submit_application,
    submit_demo,
    switch_to_real_data,
)

SHEETS = "Google Sheets/Excel"
REAL_TASK = {"id": "real-task", "skills": [SHEETS], "effort_hours": 1, "mission_area": "Food", "difficulty": "Beginner",
             "status": "Open", "assigned_student_id": None, "reuse_template_id": "tpl-volunteer-intake", "privacy_notes": "Sample data."}


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "tenants.sqlite3"
    initialize_tenant_store(path, json.loads(json.dumps(SEED_TEMPLATES)))
    return path


@pytest.fixture
def pantry(db):
    return create_account("Oak Cliff Community Pantry", "pantry@example.org", "pantry-password-123", db)


def roster(db, organization_id):
    return {student["name"]: student for student in load_workspace(organization_id, db)["students"]}


def token_for(db, student):
    return load_volunteer_profile(student["volunteer_profile_id"], db)["impact_token"]


def can_get_real_task(db, organization_id, name) -> bool:
    workspace = load_workspace(organization_id, db)
    student = next(item for item in workspace["students"] if item["name"] == name)
    in_matches = any(match["student"]["name"] == name for match in score_students(dict(REAL_TASK), workspace["students"], limit=None))
    try:
        assign_volunteer(dict(REAL_TASK), student, workspace["students"], workspace["projects"])
    except AssignmentBlocked:
        assert not in_matches
        return False
    assert in_matches
    return True


def apply_and_add(db, organization_id, name="Sam Ortiz", email="sam.ortiz@example.org"):
    submit_application(organization_id, {"name": name, "email": email, "skills": [SHEETS], "hours_per_week": 5, "causes": ["Food"]}, db)
    application = next(item for item in list_applications(organization_id, db) if item["email"] == email)
    add_application_to_roster(organization_id, application["id"], [SHEETS], db)
    return roster(db, organization_id)[name]


# ------------------------------------------------------------------ required


def test_no_real_task_before_approval_and_confidentiality(db, pantry):
    organization = pantry["organization_id"]
    sam = apply_and_add(db, organization)
    assert sam["onboarding_status"] == "Applicant" and not can_get_real_task(db, organization, "Sam Ortiz")

    send_demo_project(organization, sam["id"], SHEETS, database_path=db)
    assert roster(db, organization)["Sam Ortiz"]["onboarding_status"] == "Demo sent"
    assert not can_get_real_task(db, organization, "Sam Ortiz")

    submit_demo(token_for(db, sam), organization, sam["id"], expected_answers(SHEETS), db)
    assert roster(db, organization)["Sam Ortiz"]["onboarding_status"] == "Demo submitted"
    assert not can_get_real_task(db, organization, "Sam Ortiz")

    review_demo(organization, sam["id"], True, database_path=db)
    approved = roster(db, organization)["Sam Ortiz"]
    assert approved["onboarding_status"] == "Approved"
    assert not can_get_real_task(db, organization, "Sam Ortiz")  # approved, but no confidentiality agreement yet
    assert assignment_check(approved, REAL_TASK)["reason"] == "Must accept the confidentiality agreement first"

    with pytest.raises(PermissionError):
        accept_confidentiality("x" * 32, organization, sam["id"], db)
    accept_confidentiality(token_for(db, sam), organization, sam["id"], db)
    assert roster(db, organization)["Sam Ortiz"]["onboarding_status"] == "Supervised"
    assert can_get_real_task(db, organization, "Sam Ortiz")


def test_supervised_task_cannot_be_marked_done_without_mentor_approval(db, pantry):
    organization = pantry["organization_id"]
    people = roster(db, organization)
    workspace = load_workspace(organization, db)
    for task_id, name in (("supervised-task", "Noah Patel"), ("trusted-task", "Priya Shah")):
        workspace["projects"].append(dict(REAL_TASK, id=task_id, status="In progress", assigned_student_id=people[name]["id"]))
    save_workspace(organization, workspace["projects"], workspace["students"], db)

    assert people["Noah Patel"]["onboarding_status"] == "Supervised"
    with pytest.raises(ValueError, match="Mentor approved"):
        complete_workspace_project(organization, "supervised-task", "Guide", db)
    assert next(item for item in load_workspace(organization, db)["projects"] if item["id"] == "supervised-task")["status"] == "In progress"

    # Only NGO staff or a Mentor on this roster can approve; a Supervised volunteer can't.
    with pytest.raises(ValueError, match="Only NGO staff or a Mentor"):
        approve_as_mentor(organization, "supervised-task", people["Grace Kim"]["id"], db)
    approval = approve_as_mentor(organization, "supervised-task", people["Amina Yusuf"]["id"], db)
    assert approval["role"] == "Mentor" and approval["approved_by"] == "Amina Yusuf"
    complete_workspace_project(organization, "supervised-task", "Guide", db)

    # For a Trusted volunteer, mentor review is optional.
    assert people["Priya Shah"]["onboarding_status"] == "Trusted"
    complete_workspace_project(organization, "trusted-task", "Guide", db)
    done = {item["id"]: item["status"] for item in load_workspace(organization, db)["projects"]}
    assert done["supervised-task"] == done["trusted-task"] == "Done"


def test_trusted_only_after_three_approved_starred_tasks(db, pantry):
    organization = pantry["organization_id"]
    sam = apply_and_add(db, organization)
    send_demo_project(organization, sam["id"], SHEETS, database_path=db)
    submit_demo(token_for(db, sam), organization, sam["id"], expected_answers(SHEETS), db)
    review_demo(organization, sam["id"], True, database_path=db)
    accept_confidentiality(token_for(db, sam), organization, sam["id"], db)

    def finish(task_id, *, star):
        workspace = load_workspace(organization, db)
        workspace["projects"].append(dict(REAL_TASK, id=task_id, status="In progress", assigned_student_id=sam["id"]))
        save_workspace(organization, workspace["projects"], workspace["students"], db)
        approve_as_mentor(organization, task_id, None, db)  # NGO staff review
        complete_workspace_project(organization, task_id, "Guide", db)
        if star:
            give_star(organization, task_id, "", db)
        return roster(db, organization)["Sam Ortiz"]

    assert finish("task-1", star=True)["onboarding_status"] == "Supervised"
    assert finish("task-2", star=True)["reviewed_tasks"] == 2
    unstarred = finish("task-3", star=False)
    assert unstarred["onboarding_status"] == "Supervised" and unstarred["reviewed_tasks"] == 2
    assert assignment_check(unstarred, dict(REAL_TASK, data_sensitivity="Personal data"))["reason"].startswith("Personal data needs a Trusted volunteer")
    give_star(organization, "task-3", "", db)
    trusted = roster(db, organization)["Sam Ortiz"]
    assert trusted["onboarding_status"] == "Trusted" and trusted["reviewed_tasks"] == TRUSTED_TASKS
    assert assignment_check(trusted, dict(REAL_TASK, data_sensitivity="Personal data"))["ok"]

    # A starred task without mentor approval doesn't count.
    volunteer = {"id": "v", "onboarding": {"status": "Supervised"}}
    projects = [{"assigned_student_id": "v", "status": "Done", "thanks": {"star": True}, "mentor_approval": {"approved_by": "NGO staff"}}] * 2
    projects += [{"assigned_student_id": "v", "status": "Done", "thanks": {"star": True}}]
    assert reviewed_task_count(volunteer, projects) == 2 and volunteer_status(volunteer, projects) == "Supervised"


# ------------------------------------------------------------------ the rest of the flow


def test_applications_go_only_to_that_ngo(db, pantry):
    other = create_account("Garland Meals", "garland@example.org", "garland-password-123", db)
    submit_application(pantry["organization_id"], {"name": "Sam Ortiz", "email": "sam@example.org", "skills": [SHEETS]}, db)
    assert [item["name"] for item in list_applications(pantry["organization_id"], db) if not item["demo"]] == ["Sam Ortiz"]
    assert [item["name"] for item in list_applications(other["organization_id"], db) if not item["demo"]] == []
    assert "Sam Ortiz" not in roster(db, other["organization_id"])
    with pytest.raises(ValueError, match="already have your application"):
        submit_application(pantry["organization_id"], {"name": "Sam Ortiz", "email": "SAM@example.org", "skills": [SHEETS]}, db)


def test_rejection_needs_kind_feedback_and_reapply_waits_30_days(db, pantry):
    organization = pantry["organization_id"]
    alex = roster(db, organization)["Alex Rivera"]
    assert alex["onboarding_status"] == "Demo submitted"
    with pytest.raises(ValueError, match="feedback"):
        review_demo(organization, alex["id"], False, "  ", database_path=db)
    review_demo(organization, alex["id"], False, "Nice start! Check duplicate rows first.", database_path=db)
    rejected = roster(db, organization)["Alex Rivera"]
    assert rejected["onboarding_status"] == "Rejected" and not can_get_real_task(db, organization, "Alex Rivera")
    with pytest.raises(ValueError, match="apply again after"):
        submit_application(organization, {"name": "Alex Rivera", "email": alex["email"], "skills": [SHEETS]}, db)

    workspace = load_workspace(organization, db)
    entry = next(item for item in workspace["students"] if item["id"] == alex["id"])
    entry["onboarding"]["review"]["reviewed_at"] = (datetime.now(timezone.utc) - timedelta(days=REAPPLY_DAYS + 1)).isoformat()
    save_workspace(organization, workspace["projects"], workspace["students"], db)
    submit_application(organization, {"name": "Alex Rivera", "email": alex["email"], "skills": [SHEETS]}, db)
    application = next(item for item in list_applications(organization, db) if item["email"] == alex["email"])
    add_application_to_roster(organization, application["id"], [SHEETS], db)
    again = roster(db, organization)["Alex Rivera"]
    assert again["id"] == alex["id"] and again["onboarding_status"] == "Applicant"


def test_demo_deadline_and_only_the_volunteer_can_submit(db, pantry):
    organization = pantry["organization_id"]
    people = roster(db, organization)
    jordan = people["Jordan Ellis"]
    assert jordan["onboarding_status"] == "Demo sent"
    with pytest.raises(PermissionError):
        submit_demo(token_for(db, people["Priya Shah"]), organization, jordan["id"], expected_answers(SHEETS), db)
    workspace = load_workspace(organization, db)
    entry = next(item for item in workspace["students"] if item["id"] == jordan["id"])
    entry["onboarding"]["demo"]["deadline"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    save_workspace(organization, workspace["projects"], workspace["students"], db)
    with pytest.raises(ValueError, match="deadline has passed"):
        submit_demo(token_for(db, jordan), organization, jordan["id"], expected_answers(SHEETS), db)


def test_ngo_promotes_only_trusted_volunteers_to_mentor(db, pantry):
    organization = pantry["organization_id"]
    people = roster(db, organization)
    with pytest.raises(ValueError, match="Only Trusted"):
        promote_to_mentor(organization, people["Noah Patel"]["id"], db)
    promote_to_mentor(organization, people["Priya Shah"]["id"], db)
    workspace = load_workspace(organization, db)
    workspace["projects"].append(dict(REAL_TASK, id="task", status="In progress", assigned_student_id=people["Noah Patel"]["id"]))
    save_workspace(organization, workspace["projects"], workspace["students"], db)
    assert approve_as_mentor(organization, "task", people["Priya Shah"]["id"], db)["approved_by"] == "Priya S."


def test_real_data_needs_a_trusted_volunteer(db, pantry):
    organization = pantry["organization_id"]
    people = roster(db, organization)
    workspace = load_workspace(organization, db)
    workspace["projects"].append(dict(REAL_TASK, id="noah-work", status="In progress", assigned_student_id=people["Noah Patel"]["id"]))
    workspace["projects"].append(dict(REAL_TASK, id="priya-work", status="In progress", assigned_student_id=people["Priya Shah"]["id"]))
    save_workspace(organization, workspace["projects"], workspace["students"], db)
    with pytest.raises(ValueError, match="Trusted volunteer"):
        switch_to_real_data(organization, "noah-work", db)
    switch_to_real_data(organization, "priya-work", db)
    modes = {item["id"]: item.get("data_mode", "Sample data") for item in load_workspace(organization, db)["projects"]}
    assert modes == {**modes, "noah-work": "Sample data", "priya-work": "Real data"}


def test_demo_data_has_every_onboarding_stage(db, pantry):
    people = roster(db, pantry["organization_id"])
    assert [item["name"] for item in list_applications(pantry["organization_id"], db)] == ["Taylor Nguyen"]
    assert people["Jordan Ellis"]["onboarding_status"] == "Demo sent"
    assert people["Alex Rivera"]["onboarding_status"] == "Demo submitted"
    assert people["Noah Patel"]["onboarding_status"] == "Supervised" and people["Noah Patel"]["reviewed_tasks"] == 1
    assert people["Priya Shah"]["onboarding_status"] == "Trusted"
    assert people["Amina Yusuf"]["onboarding"]["mentor"] and people["Amina Yusuf"]["onboarding_status"] == "Trusted"
