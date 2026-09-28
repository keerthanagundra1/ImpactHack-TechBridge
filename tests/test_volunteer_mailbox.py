"""The volunteer mailbox: every email scenario, its reply, and privacy."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from skill_checks import expected_answers
from tech_bridge import SEED_PROJECTS, SEED_TEMPLATES, request_changes
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
    respond_to_invitation,
    review_demo,
    save_workspace,
    send_demo_project,
    submit_application,
    submit_demo,
    volunteer_mailbox,
)
from tech_bridge import offer_next_volunteer
from volunteer_mailbox import REPLY_GUIDE

SHEETS = "Google Sheets/Excel"
TASK = {"skills": [SHEETS], "effort_hours": 1, "mission_area": "Food", "difficulty": "Beginner", "status": "Open",
        "assigned_student_id": None, "reuse_template_id": "tpl-volunteer-intake", "privacy_notes": "Sample data.",
        "problem_type": "Volunteer data consolidation", "problem_summary": "Merge sign-up sheets", "suggested_solution": "Shared sheet",
        "deliverables": ["Set it up"]}


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "tenants.sqlite3"
    initialize_tenant_store(path, json.loads(json.dumps(SEED_TEMPLATES)))
    return path


@pytest.fixture
def pantry(db):
    return create_account("Oak Cliff Community Pantry", "pantry@example.org", "pantry-password-123", db)


def sam(db, organization):
    return next(student for student in load_workspace(organization, db)["students"] if student["name"] == "Sam Ortiz")


def mail_of(db, student, organization=None, kind=None):
    mails = volunteer_mailbox(student["volunteer_profile_id"], organization, db)
    return [mail for mail in mails if kind is None or mail["type"] == kind]


def token(db, student):
    return load_volunteer_profile(student["volunteer_profile_id"], db)["impact_token"]


def test_every_scenario_lands_in_the_mailbox_with_the_right_reply(db, pantry):
    organization = pantry["organization_id"]
    submit_application(organization, {"name": "Sam Ortiz", "email": "sam.ortiz@example.org", "skills": [SHEETS], "causes": ["Food"]}, db)
    application = next(item for item in list_applications(organization, db) if item["name"] == "Sam Ortiz")
    add_application_to_roster(organization, application["id"], [SHEETS], db)
    assert [mail["type"] for mail in mail_of(db, sam(db, organization))] == ["added"]

    send_demo_project(organization, sam(db, organization)["id"], SHEETS, database_path=db)
    demo_mail = mail_of(db, sam(db, organization), kind="demo")[0]
    assert demo_mail["needs_reply"] and demo_mail["status"] == "Waiting for the demo"
    submit_demo(token(db, sam(db, organization)), organization, sam(db, organization)["id"], expected_answers(SHEETS), db)
    assert not mail_of(db, sam(db, organization), kind="demo")[0]["needs_reply"]

    review_demo(organization, sam(db, organization)["id"], True, "Clean work!", database_path=db)
    approved = mail_of(db, sam(db, organization), kind="demo_approved")[0]
    assert approved["needs_reply"] and "Feedback: Clean work!" in approved["body"]
    accept_confidentiality(token(db, sam(db, organization)), organization, sam(db, organization)["id"], db)
    assert mail_of(db, sam(db, organization), kind="demo_approved")[0]["status"] == "Agreement accepted"
    assert mail_of(db, sam(db, organization), kind="welcome")

    # Project offers: three tasks, each accepted from the volunteer's own mailbox, mentor-approved, done, starred.
    for number in range(1, 4):
        workspace = load_workspace(organization, db)
        project = dict(TASK, id=f"task-{number}", organization="Oak Cliff Community Pantry")
        workspace["projects"].append(project)
        offer_next_volunteer(project, workspace["students"], workspace["projects"], student_id=sam(db, organization)["id"])
        save_workspace(organization, workspace["projects"], workspace["students"], db)
        offer = next(mail for mail in mail_of(db, sam(db, organization), kind="invite") if mail["project_id"] == f"task-{number}")
        assert offer["needs_reply"] and "Oak Cliff Community Pantry" in offer["body"]
        respond_to_invitation(token(db, sam(db, organization)), organization, f"task-{number}", True, db)
        if number == 1:  # the nonprofit asks for changes once
            workspace = load_workspace(organization, db)
            request_changes(next(item for item in workspace["projects"] if item["id"] == "task-1"), "Please add a Totals tab")
            save_workspace(organization, workspace["projects"], workspace["students"], db)
            changes = mail_of(db, sam(db, organization), kind="changes")[0]
            assert changes["needs_reply"] and "Please add a Totals tab" in changes["body"]
        approve_as_mentor(organization, f"task-{number}", None, db)
        complete_workspace_project(organization, f"task-{number}", "Guide", db)
        give_star(organization, f"task-{number}", "", db)
    assert [mail["status"] for mail in mail_of(db, sam(db, organization), kind="invite")] == ["Accepted"] * 3
    assert len(mail_of(db, sam(db, organization), kind="star")) == 3
    assert mail_of(db, sam(db, organization), kind="trusted")
    promote_to_mentor(organization, sam(db, organization)["id"], db)
    kinds = {mail["type"] for mail in mail_of(db, sam(db, organization))}
    assert {"added", "demo", "demo_approved", "welcome", "invite", "changes", "star", "trusted", "mentor"} <= kinds
    assert all(kind in REPLY_GUIDE for kind in kinds)


def test_declining_an_offer_passes_it_on_and_only_the_volunteer_can_reply(db, pantry):
    organization = pantry["organization_id"]
    workspace = load_workspace(organization, db)
    project = dict(TASK, id="offer", organization="Oak Cliff Community Pantry")
    workspace["projects"].append(project)
    first = offer_next_volunteer(project, workspace["students"], workspace["projects"])
    save_workspace(organization, workspace["projects"], workspace["students"], db)
    people = {student["id"]: student for student in load_workspace(organization, db)["students"]}
    with pytest.raises(PermissionError):
        respond_to_invitation("x" * 32, organization, "offer", True, db)
    someone_else = next(student for student in people.values() if student["id"] != first["student_id"])
    with pytest.raises(PermissionError):
        respond_to_invitation(token(db, someone_else), organization, "offer", True, db)
    respond_to_invitation(token(db, people[first["student_id"]]), organization, "offer", False, db)
    assert mail_of(db, people[first["student_id"]], kind="invite")[0]["status"] == "Declined"
    stored = next(item for item in load_workspace(organization, db)["projects"] if item["id"] == "offer")
    assert stored["status"] == "Offered" and stored["invitations"][-1]["student_id"] != first["student_id"]


def test_rejected_and_expired_demos(db, pantry):
    organization = pantry["organization_id"]
    people = {student["name"]: student for student in load_workspace(organization, db)["students"]}
    review_demo(organization, people["Alex Rivera"]["id"], False, "Nice start! Re-check the duplicates.", database_path=db)
    rejected = mail_of(db, people["Alex Rivera"], kind="demo_rejected")[0]
    assert not rejected["needs_reply"] and "Re-check the duplicates" in rejected["body"]

    workspace = load_workspace(organization, db)
    jordan = next(item for item in workspace["students"] if item["name"] == "Jordan Ellis")
    jordan["onboarding"]["demo"]["deadline"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    save_workspace(organization, workspace["projects"], workspace["students"], db)
    expired = mail_of(db, jordan, kind="demo")[0]
    assert expired["status"] == "Expired" and not expired["needs_reply"]
    send_demo_project(organization, jordan["id"], "Web design (HTML/CSS)", database_path=db)  # resend after the deadline
    fresh = mail_of(db, jordan, kind="demo")[0]
    assert fresh["needs_reply"] and "Accessible page basics" in fresh["body"]


def test_mailbox_privacy(db, pantry):
    organization = pantry["organization_id"]
    other = create_account("Garland Meals", "garland@example.org", "garland-password-123", db)
    people = {student["name"]: student for student in load_workspace(organization, db)["students"]}
    workspace = load_workspace(other["organization_id"], db)
    project = dict(TASK, id="garland-offer", organization="Garland Meals")
    workspace["projects"].append(project)
    offer_next_volunteer(project, workspace["students"], workspace["projects"], student_id=next(
        student["id"] for student in workspace["students"] if student["name"] == "Noah Patel"))
    save_workspace(other["organization_id"], workspace["projects"], workspace["students"], db)

    noah = people["Noah Patel"]
    assert any(mail["project_id"] == "garland-offer" for mail in mail_of(db, noah, kind="invite"))  # his own mailbox
    assert not any(mail.get("project_id") == "garland-offer" for mail in mail_of(db, noah, organization))  # the pantry's view
    names = {project["organization"] for project in SEED_PROJECTS} | {"Oak Cliff", "Garland Meals"}
    for mail in mail_of(db, people["Alex Rivera"]) + mail_of(db, people["Jordan Ellis"]) + mail_of(db, noah):
        if mail["type"] not in {"invite", "changes"}:  # offers and change requests come from the nonprofit itself
            assert not any(name in mail["subject"] + mail["body"] + mail["summary"] for name in names), mail["type"]
