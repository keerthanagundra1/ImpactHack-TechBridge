"""The demo sign-in from the app's secrets is recreated whenever a hosted app's storage resets."""

import json

import pytest

from tech_bridge import SEED_TEMPLATES
from tenant_store import authenticate, create_account, ensure_demo_account, initialize_tenant_store, load_workspace

DEMO = ("Bright Path Community Center (Demo)", "demo@example.org", "example@1234")


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "tenants.sqlite3"
    initialize_tenant_store(path, json.loads(json.dumps(SEED_TEMPLATES)))
    return path


def test_demo_account_is_created_with_demo_data_and_is_idempotent(db):
    first = ensure_demo_account(*DEMO, database_path=db)
    assert authenticate("DEMO@example.org", "example@1234", db)["organization_name"] == "Bright Path Community Center (Demo)"
    assert ensure_demo_account(*DEMO, database_path=db)["organization_id"] == first["organization_id"]
    workspace = load_workspace(first["organization_id"], db)
    assert len(workspace["students"]) > 30 and any(project.get("demo_scenario") for project in workspace["projects"])


def test_a_fresh_database_gets_the_demo_account_back(tmp_path):
    for run in range(2):  # each run is a new, empty database, like a hosted app after a restart
        path = tmp_path / f"reset-{run}.sqlite3"
        initialize_tenant_store(path, json.loads(json.dumps(SEED_TEMPLATES)))
        assert authenticate("demo@example.org", "example@1234", path) is None
        ensure_demo_account(*DEMO, database_path=path)
        assert authenticate("demo@example.org", "example@1234", path)


def test_the_secrets_password_wins_and_short_passwords_are_refused(db):
    create_account("Bright Path Community Center (Demo)", "demo@example.org", "an-older-password-1", db)
    ensure_demo_account(*DEMO, database_path=db)
    assert authenticate("demo@example.org", "example@1234", db)
    assert authenticate("demo@example.org", "an-older-password-1", db) is None
    with pytest.raises(ValueError, match="at least 12"):
        ensure_demo_account("Other Org", "other@example.org", "short", database_path=db)
