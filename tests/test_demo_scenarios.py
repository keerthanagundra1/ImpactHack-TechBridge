"""Seeded demo scenarios: each case exists in a new workspace and behaves as described."""

import json

import pytest

from demo_scenarios import SCENARIOS
from tech_bridge import SEED_TEMPLATES, score_students
from tenant_store import (
    accept_confidentiality,
    approve_as_mentor,
    complete_workspace_project,
    create_account,
    give_star,
    initialize_tenant_store,
    load_volunteer_profile,
    load_workspace,
    reset_workspace,
    send_demo_project,
    volunteer_mailbox,
)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "tenants.sqlite3"
    initialize_tenant_store(path, json.loads(json.dumps(SEED_TEMPLATES)))
    return path


@pytest.fixture
def pantry(db):
    return create_account("Oak Cliff Community Pantry", "pantry@example.org", "pantry-password-123", db)


def workspace(db, organization):
    data = load_workspace(organization, db)
    return {student["name"]: student for student in data["students"]}, {project["id"]: project for project in data["projects"]}


def mails(db, student, organization, kind):
    return [mail for mail in volunteer_mailbox(student["volunteer_profile_id"], organization, db) if mail["type"] == kind]


def test_every_scenario_is_seeded_and_labeled(db, pantry):
    people, projects = workspace(db, pantry["organization_id"])
    assert len(SCENARIOS) >= 5
    assert people["Tyler Robinson"]["onboarding_status"] == "Rejected"
    assert people["Mia Thompson"]["onboarding_status"] == "Demo sent"
    assert people["Harper Davis"]["onboarding_status"] == "Approved"
    assert projects["scenario-offer"]["status"] == "Offered"
    assert projects["scenario-supervised"]["status"] == "In progress"
    assert projects["scenario-review"]["status"] == "Ready for review"
    assert projects["scenario-star"]["status"] == "Done"
    assert projects["scenario-personal"]["status"] == "Open"
    assert all(project["demo_project"] for key, project in projects.items() if key.startswith("scenario-"))


def test_scenarios_show_up_in_the_right_mailboxes(db, pantry):
    organization = pantry["organization_id"]
    people, _ = workspace(db, organization)
    rejected = mails(db, people["Tyler Robinson"], organization, "demo_rejected")[0]
    assert "alt attribute" in rejected["body"] and not rejected["needs_reply"]
    expired = mails(db, people["Mia Thompson"], organization, "demo")[0]
    assert expired["status"] == "Expired"
    assert mails(db, people["Harper Davis"], organization, "demo_approved")[0]["needs_reply"]
    assert mails(db, people["Zara Hussain"], organization, "invite")[0]["needs_reply"]
    changes = mails(db, people["Daniel Okoye"], organization, "changes")[0]
    assert changes["status"] == "Resubmitted" and "two days before" in changes["body"]


def test_scenarios_play_forward(db, pantry):
    organization = pantry["organization_id"]
    people, _ = workspace(db, organization)
    # Expired demo can be resent.
    send_demo_project(organization, people["Mia Thompson"]["id"], "Canva/Graphics", database_path=db)
    # Approved volunteer accepts the agreement and becomes Supervised.
    token = load_volunteer_profile(people["Harper Davis"]["volunteer_profile_id"], db)["impact_token"]
    accept_confidentiality(token, organization, people["Harper Davis"]["id"], db)
    # Supervised work can't be marked done until a Mentor approves it.
    with pytest.raises(ValueError, match="Mentor approved"):
        complete_workspace_project(organization, "scenario-supervised", "Guide", db)
    approve_as_mentor(organization, "scenario-review", people["Amina Yusuf"]["id"], db)
    complete_workspace_project(organization, "scenario-review", "Guide", db)
    # One star makes Caleb Trusted.
    assert people["Caleb Brooks"]["onboarding_status"] == "Supervised" and people["Caleb Brooks"]["reviewed_tasks"] == 2
    give_star(organization, "scenario-star", "Thank you, Caleb!", db)
    people, projects = workspace(db, organization)
    assert people["Caleb Brooks"]["onboarding_status"] == "Trusted"
    assert mails(db, people["Caleb Brooks"], organization, "trusted")
    assert people["Mia Thompson"]["onboarding_status"] == "Demo sent" and people["Harper Davis"]["onboarding_status"] == "Supervised"
    assert projects["scenario-review"]["status"] == "Done"
    # The personal-data project only matches Trusted volunteers.
    matches = score_students(projects["scenario-personal"], list(people.values()), limit=None)
    assert matches and all(match["student"]["onboarding_status"] == "Trusted" for match in matches)


def test_reset_restores_the_scenarios(db, pantry):
    organization = pantry["organization_id"]
    workspace(db, organization)  # scenarios are added the first time the workspace opens
    give_star(organization, "scenario-star", "", db)
    reset_workspace(organization, db)
    people, projects = workspace(db, organization)
    assert people["Caleb Brooks"]["onboarding_status"] == "Supervised" and "thanks" not in projects["scenario-star"]
