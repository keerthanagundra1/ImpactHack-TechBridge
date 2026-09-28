"""Local prototype auth and tenant-scoped persistence for Tech Bridge."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from datetime import datetime, timedelta, timezone

from tech_bridge import (
    APP_BASE_URL,
    MISSION_AREAS,
    SEED_PROJECTS,
    SEED_STUDENTS,
    SEED_TEMPLATES,
    STORAGE_PATH,
    changes_requested_notice,
    find_invitation_by_token,
    load_state,
    offer_next_volunteer,
    pending_invitation,
    require_mentor_approval,
    respond_to_offer,
    score_students,
)
from onboarding import (
    APPLICANT,
    APPROVED,
    DEMO_DEADLINE_DAYS,
    DEMO_SENT,
    DEMO_SUBMITTED,
    NGO_STAFF,
    REJECTED,
    SEED_APPLICATION,
    SUPERVISED,
    TRUSTED,
    annotate_onboarding,
    demo_overdue,
    is_mentor,
    new_demo,
    new_onboarding,
    real_data_check,
    reapply_after,
    seed_onboarding,
    volunteer_status,
)
from demo_scenarios import apply_scenarios
from skill_checks import PRACTICE_TASKS, grade_practice_task
from volunteer_mailbox import (
    DERIVED_TYPES,
    mail_from_change_request,
    mail_from_invitation,
    mail_from_notification,
    onboarding_mails,
    sort_mail,
)
from volunteer_retention import (
    DEFAULT_SEED_PROFILE,
    DISPLAY_NAME_CHOICES,
    MATCHING_PROFILE_KEYS,
    NUDGE_INTERVAL_DAYS,
    NUDGE_MESSAGE,
    SEED_NOTIFICATIONS,
    EVIDENCE_TYPES,
    PROOF_LEVELS,
    display_name,
    notification_email,
    now_iso,
    nudge_details,
    reuse_message,
    scrub_organization,
    seed_profile_fields,
    star_message,
)

DATABASE_PATH = Path(os.environ.get(
    "TECH_BRIDGE_DATABASE",
    str(Path(__file__).parent / "data" / "tech_bridge_tenants.sqlite3"),
))
PBKDF2_ITERATIONS = 310_000
MIN_PASSWORD_LENGTH = 12


def _connect(database_path: Path = DATABASE_PATH) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def _connection(database_path: Path = DATABASE_PATH):
    connection = _connect(database_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _organization_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def _hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)


def _seeded_workspace(organization_name: str) -> dict[str, list[dict[str, Any]]]:
    organization_key = _organization_key(organization_name)
    projects = [
        project for project in SEED_PROJECTS
        if _organization_key(project["organization"]) == organization_key
    ]
    volunteers = json.loads(json.dumps(SEED_STUDENTS))
    return {"projects": json.loads(json.dumps(projects)), "students": volunteers}


def initialize_tenant_store(
    database_path: Path = DATABASE_PATH,
    initial_library: list[dict[str, Any]] | None = None,
) -> None:
    with _connection(database_path) as connection:
        connection.execute("BEGIN")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS organizations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                organization_key TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS accounts (
                email TEXT PRIMARY KEY COLLATE NOCASE,
                organization_id TEXT NOT NULL UNIQUE REFERENCES organizations(id),
                password_salt BLOB NOT NULL,
                password_hash BLOB NOT NULL
            );
            CREATE TABLE IF NOT EXISTS private_workspaces (
                organization_id TEXT PRIMARY KEY REFERENCES organizations(id),
                projects_json TEXT NOT NULL,
                volunteers_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS shared_library (
                singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                solutions_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS volunteer_profiles (
                id TEXT PRIMARY KEY,
                identity_key TEXT NOT NULL UNIQUE,
                impact_token TEXT NOT NULL UNIQUE,
                profile_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id TEXT PRIMARY KEY,
                volunteer_id TEXT NOT NULL REFERENCES volunteer_profiles(id),
                type TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                read INTEGER NOT NULL DEFAULT 0,
                email_subject TEXT NOT NULL,
                email_body TEXT NOT NULL,
                action_json TEXT NOT NULL DEFAULT '{}',
                demo INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS notifications_by_volunteer ON notifications(volunteer_id, created_at);
            CREATE TABLE IF NOT EXISTS concerns (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL REFERENCES organizations(id),
                project_id TEXT NOT NULL,
                volunteer_id TEXT,
                note TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS skill_proofs (
                id TEXT PRIMARY KEY,
                volunteer_id TEXT NOT NULL REFERENCES volunteer_profiles(id),
                skill TEXT NOT NULL,
                level INTEGER NOT NULL CHECK (level BETWEEN 1 AND 4),
                source TEXT NOT NULL,
                confirmed_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                private_details_json TEXT NOT NULL DEFAULT '{}',
                demo INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS skill_proofs_by_volunteer ON skill_proofs(volunteer_id, skill);
            CREATE TABLE IF NOT EXISTS applications (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL REFERENCES organizations(id),
                application_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'New',
                created_at TEXT NOT NULL,
                demo INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS applications_by_organization ON applications(organization_id, status);
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        existing_library = connection.execute(
            "SELECT solutions_json FROM shared_library WHERE singleton_id = 1"
        ).fetchone()
        if existing_library is None:
            if initial_library is None:
                # A fresh server (no legacy JSON file) starts with the built-in, data-free demo solutions.
                legacy_state = load_state() if STORAGE_PATH.exists() else None
                initial_library = legacy_state["templates"] if legacy_state else json.loads(json.dumps(SEED_TEMPLATES))
            connection.execute(
                "INSERT INTO shared_library(singleton_id, solutions_json) VALUES (1, ?)",
                (json.dumps(initial_library, ensure_ascii=True),),
            )
        seeded = connection.execute("SELECT value FROM app_meta WHERE key = 'retention_seed_version'").fetchone()
        if seeded is None or int(seeded["value"]) < RETENTION_SEED_VERSION:
            _seed_retention(connection)
            connection.execute(
                "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('retention_seed_version', ?)",
                (str(RETENTION_SEED_VERSION),),
            )


def create_account(
    organization_name: str,
    email: str,
    password: str,
    database_path: Path = DATABASE_PATH,
) -> dict[str, str]:
    organization_name = organization_name.strip()
    email = email.strip().casefold()
    if len(organization_name) < 2:
        raise ValueError("Enter your nonprofit's name.")
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise ValueError("Enter a valid email address.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Use a password with at least {MIN_PASSWORD_LENGTH} characters.")
    organization_key = _organization_key(organization_name)
    if not organization_key:
        raise ValueError("Enter a valid nonprofit name.")

    initialize_tenant_store(database_path)
    organization_id = str(uuid4())
    salt = secrets.token_bytes(16)
    password_hash = _hash_password(password, salt)
    workspace = _seeded_workspace(organization_name)
    try:
        with _connection(database_path) as connection:
            connection.execute(
                "INSERT INTO organizations(id, name, organization_key) VALUES (?, ?, ?)",
                (organization_id, organization_name, organization_key),
            )
            connection.execute(
                "INSERT INTO accounts(email, organization_id, password_salt, password_hash) VALUES (?, ?, ?, ?)",
                (email, organization_id, salt, password_hash),
            )
            connection.execute(
                "INSERT INTO private_workspaces(organization_id, projects_json, volunteers_json) VALUES (?, ?, ?)",
                (
                    organization_id,
                    json.dumps(workspace["projects"], ensure_ascii=True),
                    json.dumps(workspace["students"], ensure_ascii=True),
                ),
            )
    except sqlite3.IntegrityError as error:
        raise ValueError("An account already exists for this email or nonprofit.") from error
    return {"organization_id": organization_id, "organization_name": organization_name, "email": email}


def authenticate(
    email: str,
    password: str,
    database_path: Path = DATABASE_PATH,
) -> dict[str, str] | None:
    initialize_tenant_store(database_path)
    with _connection(database_path) as connection:
        row = connection.execute(
            """SELECT accounts.email, accounts.password_salt, accounts.password_hash,
                      organizations.id AS organization_id, organizations.name AS organization_name
               FROM accounts JOIN organizations ON organizations.id = accounts.organization_id
               WHERE accounts.email = ? COLLATE NOCASE""",
            (email.strip(),),
        ).fetchone()
    if row is None:
        return None
    attempted_hash = _hash_password(password, row["password_salt"])
    if not hmac.compare_digest(attempted_hash, row["password_hash"]):
        return None
    return {
        "email": row["email"],
        "organization_id": row["organization_id"],
        "organization_name": row["organization_name"],
    }


def ensure_demo_account(
    organization_name: str,
    email: str,
    password: str,
    database_path: Path = DATABASE_PATH,
) -> dict[str, str]:
    """Make sure the demo sign-in from the app's secrets exists, so it survives a hosted app's storage resets.

    Creates the account if it's missing; if the email exists with another password, the secrets' password wins.
    """
    account = authenticate(email, password, database_path)
    if account:
        return account
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Use a password with at least {MIN_PASSWORD_LENGTH} characters.")
    with _connection(database_path) as connection:
        exists = connection.execute("SELECT 1 FROM accounts WHERE email = ? COLLATE NOCASE", (email.strip(),)).fetchone()
        if exists:
            salt = secrets.token_bytes(16)
            connection.execute(
                "UPDATE accounts SET password_salt = ?, password_hash = ? WHERE email = ? COLLATE NOCASE",
                (salt, _hash_password(password, salt), email.strip()),
            )
    if exists:
        return authenticate(email, password, database_path)
    return create_account(organization_name, email, password, database_path)


def load_workspace(
    organization_id: str,
    database_path: Path = DATABASE_PATH,
) -> dict[str, list[dict[str, Any]]]:
    initialize_tenant_store(database_path)
    with _connection(database_path) as connection:
        row = connection.execute(
            "SELECT projects_json, volunteers_json FROM private_workspaces WHERE organization_id = ?",
            (organization_id,),
        ).fetchone()
    if row is None:
        raise PermissionError("This nonprofit workspace is not available to this account.")
    students = json.loads(row["volunteers_json"])
    projects = json.loads(row["projects_json"])
    changed = _migrate_onboarding(students)
    changed = _seed_scenarios_once(organization_id, students, projects, database_path) or changed
    if changed:
        save_workspace(organization_id, projects, students, database_path)
    attach_volunteer_profiles(students, database_path)
    annotate_onboarding(students, projects)
    _seed_application_once(organization_id, database_path)
    return {
        "projects": projects,
        "students": students,
    }


def _migrate_onboarding(students: list[dict[str, Any]]) -> bool:
    """Roster entries from before NGO-led onboarding: demo volunteers get their seeded status; others were already approved."""
    changed = False
    for student in students:
        if "onboarding" not in student:
            student["onboarding"] = seed_onboarding(student.get("name", "")) if student.get("demo_student") else new_onboarding(
                SUPERVISED, confidentiality_accepted_at=None, legacy=True,
            )
            changed = True
    return changed


def _seed_scenarios_once(organization_id: str, students: list[dict[str, Any]], projects: list[dict[str, Any]], database_path: Path) -> bool:
    """Add the labeled demo scenarios to a workspace once (and again after Reset demo data)."""
    key = f"demo_scenarios:{organization_id}"
    with _connection(database_path) as connection:
        if connection.execute("SELECT 1 FROM app_meta WHERE key = ?", (key,)).fetchone():
            return False
        connection.execute("INSERT INTO app_meta(key, value) VALUES (?, '1')", (key,))
        row = connection.execute("SELECT name FROM organizations WHERE id = ?", (organization_id,)).fetchone()
    return bool(apply_scenarios(row["name"] if row else "", students, projects, APP_BASE_URL))


def _seed_application_once(organization_id: str, database_path: Path) -> None:
    key = f"seed_application:{organization_id}"
    with _connection(database_path) as connection:
        if connection.execute("SELECT 1 FROM app_meta WHERE key = ?", (key,)).fetchone():
            return
        connection.execute("INSERT INTO app_meta(key, value) VALUES (?, '1')", (key,))
        connection.execute(
            "INSERT INTO applications(id, organization_id, application_json, status, created_at, demo) VALUES (?, ?, ?, 'New', ?, 1)",
            (uuid4().hex, organization_id, json.dumps(SEED_APPLICATION, ensure_ascii=True), now_iso()),
        )


def save_workspace(
    organization_id: str,
    projects: list[dict[str, Any]],
    volunteers: list[dict[str, Any]],
    database_path: Path = DATABASE_PATH,
) -> None:
    with _connection(database_path) as connection:
        cursor = connection.execute(
            "UPDATE private_workspaces SET projects_json = ?, volunteers_json = ? WHERE organization_id = ?",
            (
                json.dumps(projects, ensure_ascii=True),
                json.dumps(volunteers, ensure_ascii=True),
                organization_id,
            ),
        )
        if cursor.rowcount != 1:
            raise PermissionError("This nonprofit workspace is not available to this account.")


def find_invitation(
    token: str,
    database_path: Path = DATABASE_PATH,
) -> tuple[str, str] | None:
    """Resolve a volunteer's private invitation link to (organization_id, project_id)."""
    if not token or len(token) < 20:
        return None
    initialize_tenant_store(database_path)
    with _connection(database_path) as connection:
        rows = connection.execute("SELECT organization_id, projects_json FROM private_workspaces").fetchall()
    for row in rows:
        for project in json.loads(row["projects_json"]):
            if find_invitation_by_token(project, token):
                return row["organization_id"], project["id"]
    return None


def organization_email(organization_id: str, database_path: Path = DATABASE_PATH) -> str:
    with _connection(database_path) as connection:
        row = connection.execute("SELECT email FROM accounts WHERE organization_id = ?", (organization_id,)).fetchone()
    return row["email"] if row else ""


def reset_workspace(organization_id: str, database_path: Path = DATABASE_PATH) -> None:
    with _connection(database_path) as connection:
        connection.execute("BEGIN")
        organization = connection.execute(
            "SELECT name FROM organizations WHERE id = ?", (organization_id,)
        ).fetchone()
    if organization is None:
        raise PermissionError("This nonprofit workspace is not available to this account.")
    workspace = _seeded_workspace(organization["name"])
    save_workspace(organization_id, workspace["projects"], workspace["students"], database_path)
    with _connection(database_path) as connection:
        connection.execute("DELETE FROM applications WHERE organization_id = ?", (organization_id,))
        connection.execute("DELETE FROM app_meta WHERE key IN (?, ?)", (f"seed_application:{organization_id}", f"demo_scenarios:{organization_id}"))


def load_shared_library(database_path: Path = DATABASE_PATH) -> list[dict[str, Any]]:
    initialize_tenant_store(database_path)
    with _connection(database_path) as connection:
        connection.execute("BEGIN")
        row = connection.execute(
            "SELECT solutions_json FROM shared_library WHERE singleton_id = 1"
        ).fetchone()
    if row is None:
        raise RuntimeError("The shared solution library has not been initialized.")
    return json.loads(row["solutions_json"])


def save_shared_library(
    solutions: list[dict[str, Any]],
    database_path: Path = DATABASE_PATH,
) -> None:
    with _connection(database_path) as connection:
        connection.execute(
            "UPDATE shared_library SET solutions_json = ? WHERE singleton_id = 1",
            (json.dumps(solutions, ensure_ascii=True),),
        )


def complete_workspace_project(
    organization_id: str,
    project_id: str,
    handoff_guide: str,
    database_path: Path = DATABASE_PATH,
) -> None:
    with _connection(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        workspace = connection.execute(
            "SELECT projects_json, volunteers_json FROM private_workspaces WHERE organization_id = ?",
            (organization_id,),
        ).fetchone()
        if workspace is None:
            raise PermissionError("This nonprofit workspace is not available to this account.")
        projects = json.loads(workspace["projects_json"])
        project = next((item for item in projects if item.get("id") == project_id), None)
        if project is None:
            raise PermissionError("This project is not part of this nonprofit workspace.")
        first_completion = project.get("status") != "Done"
        roster = json.loads(workspace["volunteers_json"])
        annotate_onboarding(roster, projects)
        require_mentor_approval(project, next((item for item in roster if item.get("id") == project.get("assigned_student_id")), None))
        reused_solution = None
        if first_completion and project.get("reuse_template_id"):
            library_row = connection.execute(
                "SELECT solutions_json FROM shared_library WHERE singleton_id = 1"
            ).fetchone()
            solutions = json.loads(library_row["solutions_json"])
            solution = next((item for item in solutions if item.get("id") == project["reuse_template_id"]), None)
            if solution is None:
                raise ValueError("The reused solution is no longer available in the library.")
            solution["reuse_count"] = int(solution.get("reuse_count", 0)) + 1
            solution["reuse_staff_hours_per_week"] = int(solution.get("reuse_staff_hours_per_week", 0) or 0) + int(project.get("hours_wasted_per_week", 0) or 0)
            reused_solution = solution
            connection.execute(
                "UPDATE shared_library SET solutions_json = ? WHERE singleton_id = 1",
                (json.dumps(solutions, ensure_ascii=True),),
            )
        project["status"] = "Done"
        project["handoff_guide"] = handoff_guide
        connection.execute(
            "UPDATE private_workspaces SET projects_json = ? WHERE organization_id = ?",
            (json.dumps(projects, ensure_ascii=True), organization_id),
        )
        if not first_completion:
            return
        if reused_solution and reused_solution.get("builder_volunteer_id"):
            builder = _load_profile(connection, reused_solution["builder_volunteer_id"])
            if builder:
                _notify(connection, builder, "reuse", reuse_message(reused_solution, project.get("mission_area")),
                        action={"organization_id": organization_id})
        volunteer = next(
            (item for item in json.loads(workspace["volunteers_json"]) if item.get("id") == project.get("assigned_student_id")),
            None,
        )
        if volunteer:
            profile = _get_or_create_profile(connection, volunteer)
            profile.setdefault("completed_projects", []).append({
                "title": reused_solution["title"] if reused_solution else project.get("problem_type", "Volunteer project"),
                "mission_area": project.get("mission_area", "Other"),
                "kind": "reuse" if reused_solution else "new build",
                "hours_saved_per_week": int(project.get("hours_wasted_per_week", 0) or 0),
                "skills": list(project.get("skills", [])),
                "completed_at": now_iso(),
                "project_id": project_id,
            })
            _save_profile(connection, profile)


def publish_workspace_solution(
    organization_id: str,
    project_id: str,
    solution: dict[str, Any],
    database_path: Path = DATABASE_PATH,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not solution.get("data_free"):
        raise ValueError("Only data-free solutions can be added to the shared library.")
    with _connection(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        workspace = connection.execute(
            "SELECT projects_json FROM private_workspaces WHERE organization_id = ?",
            (organization_id,),
        ).fetchone()
        if workspace is None:
            raise PermissionError("This nonprofit workspace is not available to this account.")
        projects = json.loads(workspace["projects_json"])
        project = next((item for item in projects if item.get("id") == project_id), None)
        if project is None:
            raise PermissionError("This project is not part of this nonprofit workspace.")
        if project.get("status") != "Done" or project.get("reuse_template_id"):
            raise ValueError("Only completed new builds can be published.")
        # The nonprofit publishing its own reviewed, data-free pattern is its consent.
        project["library_consent"] = True
        if project.get("library_template_id"):
            raise ValueError("This project already has a library solution.")
        library_row = connection.execute(
            "SELECT solutions_json FROM shared_library WHERE singleton_id = 1"
        ).fetchone()
        solutions = json.loads(library_row["solutions_json"])
        if any(item.get("id") == solution.get("id") for item in solutions):
            raise ValueError("This solution is already in the shared library.")
        solutions.append(solution)
        project["library_template_id"] = solution["id"]
        connection.execute(
            "UPDATE shared_library SET solutions_json = ? WHERE singleton_id = 1",
            (json.dumps(solutions, ensure_ascii=True),),
        )
        connection.execute(
            "UPDATE private_workspaces SET projects_json = ? WHERE organization_id = ?",
            (json.dumps(projects, ensure_ascii=True), organization_id),
        )
    return solutions, projects

# ---------------------------------------------------------------- volunteer retention

RETENTION_SEED_VERSION = 2


def _identity_key(student: dict[str, Any]) -> str:
    email = (student.get("email") or "").strip().casefold()
    return f"email:{email}" if email else f"id:{student.get('id', '')}"


def _load_profile(connection: sqlite3.Connection, profile_id: str) -> dict[str, Any] | None:
    row = connection.execute("SELECT profile_json FROM volunteer_profiles WHERE id = ?", (profile_id,)).fetchone()
    return json.loads(row["profile_json"]) if row else None


def _save_profile(connection: sqlite3.Connection, profile: dict[str, Any]) -> None:
    connection.execute(
        "UPDATE volunteer_profiles SET profile_json = ? WHERE id = ?",
        (json.dumps(profile, ensure_ascii=True), profile["id"]),
    )


def _get_or_create_profile(
    connection: sqlite3.Connection,
    student: dict[str, Any],
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One global profile per volunteer (keyed by email), shared across every nonprofit roster they appear on."""
    key = _identity_key(student)
    row = connection.execute("SELECT profile_json FROM volunteer_profiles WHERE identity_key = ?", (key,)).fetchone()
    if row:
        profile = json.loads(row["profile_json"])
        if overrides:
            profile.update(overrides)
            _save_profile(connection, profile)
        return profile
    demo = bool(student.get("demo_student"))
    fields = seed_profile_fields(student.get("name", "")) if demo else json.loads(json.dumps(DEFAULT_SEED_PROFILE))
    seeded_proofs = fields.pop("proofs", [])
    profile = {
        **fields,
        "id": uuid4().hex,
        "impact_token": secrets.token_urlsafe(24),
        "name": student.get("name", ""),
        "email": student.get("email", ""),
        "skills": list(student.get("skills", [])),
        "causes": list(student.get("causes", [])),
        "hours_per_week": int(student.get("hours_per_week", 4) or 4),
        "confidentiality_signed": bool(student.get("confidentiality_signed", False)),
        "demo": demo,
        "created_at": now_iso(),
    }
    profile.update(overrides or {})
    connection.execute(
        "INSERT INTO volunteer_profiles(id, identity_key, impact_token, profile_json) VALUES (?, ?, ?, ?)",
        (profile["id"], key, profile["impact_token"], json.dumps(profile, ensure_ascii=True)),
    )
    _seed_profile_proofs(connection, profile, seeded_proofs)
    return profile


def _insert_proof(
    connection: sqlite3.Connection,
    volunteer_id: str,
    skill: str,
    level: int,
    source: str,
    confirmed_by: str,
    private: dict[str, Any] | None = None,
    demo: bool = False,
    created_at: str | None = None,
) -> None:
    connection.execute(
        """INSERT INTO skill_proofs(id, volunteer_id, skill, level, source, confirmed_by, created_at, private_details_json, demo)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (uuid4().hex, volunteer_id, skill, level, source, confirmed_by, created_at or now_iso(),
         json.dumps(private or {}, ensure_ascii=True), int(demo)),
    )


def _seed_profile_proofs(connection: sqlite3.Connection, profile: dict[str, Any], seeded: list[dict[str, Any]]) -> None:
    """Level 1 rows for listed skills, plus labeled demo Level 2-3 proofs and Level 4 rows for demo stars."""
    demo = bool(profile.get("demo"))
    for skill in profile.get("skills", []):
        _insert_proof(connection, profile["id"], skill, 1, "Self-listed", "Volunteer", demo=demo)
    for proof in seeded:
        _insert_proof(connection, profile["id"], proof["skill"], proof["level"], proof["source"], proof["confirmed_by"],
                      proof.get("private"), demo=True)
    for skill, count in profile.get("badges", {}).items():
        for _ in range(int(count or 0)):
            _insert_proof(connection, profile["id"], skill, 4, "Star from a nonprofit (demo)", "A nonprofit", demo=True)


def _skill_levels(connection: sqlite3.Connection, volunteer_id: str) -> dict[str, int]:
    rows = connection.execute(
        "SELECT skill, MAX(level) AS level FROM skill_proofs WHERE volunteer_id = ? AND level >= 2 GROUP BY skill",
        (volunteer_id,),
    ).fetchall()
    return {row["skill"]: int(row["level"]) for row in rows}


def _notify(
    connection: sqlite3.Connection,
    profile: dict[str, Any],
    notification_type: str,
    message: str,
    *,
    extra: str = "",
    action: dict[str, Any] | None = None,
    created_at: str | None = None,
    read: bool = False,
    demo: bool = False,
) -> dict[str, Any]:
    subject, body = notification_email(profile, notification_type, message, APP_BASE_URL, extra)
    notification = {
        "id": uuid4().hex, "volunteer_id": profile["id"], "type": notification_type, "message": message,
        "created_at": created_at or now_iso(), "read": read, "email_subject": subject, "email_body": body,
        "action": action or {}, "demo": demo,
    }
    connection.execute(
        """INSERT INTO notifications(id, volunteer_id, type, message, created_at, read, email_subject, email_body, action_json, demo)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            notification["id"], profile["id"], notification_type, message, notification["created_at"], int(read),
            subject, body, json.dumps(notification["action"], ensure_ascii=True), int(demo),
        ),
    )
    return notification


def _seed_retention(connection: sqlite3.Connection) -> None:
    """Create labeled demo volunteer profiles and notifications, and credit demo library entries to them."""
    profiles_by_name = {}
    for student in SEED_STUDENTS:
        existed = connection.execute(
            "SELECT 1 FROM volunteer_profiles WHERE identity_key = ?", (_identity_key(student),)
        ).fetchone()
        profile = _get_or_create_profile(connection, student)
        profiles_by_name[student["name"]] = profile
        if existed and profile.get("demo"):
            has_proofs = connection.execute("SELECT 1 FROM skill_proofs WHERE volunteer_id = ?", (profile["id"],)).fetchone()
            if not has_proofs:
                seed = seed_profile_fields(student["name"])
                if not profile.get("completed_projects") and seed["completed_projects"]:
                    profile["completed_projects"] = seed["completed_projects"]
                for stale in ("skill_check_passed", "endorsed"):
                    profile.pop(stale, None)
                profile.setdefault("background_check_cleared", False)
                _save_profile(connection, profile)
                _seed_profile_proofs(connection, profile, seed["proofs"])
        if existed:
            continue
        for seed in SEED_NOTIFICATIONS.get(student["name"], []):
            _notify(
                connection, profile, seed["type"], seed["message"], extra=seed.get("extra", ""),
                action=seed.get("action"), created_at=seed["created_at"], read=seed["read"], demo=True,
            )
    library_row = connection.execute("SELECT solutions_json FROM shared_library WHERE singleton_id = 1").fetchone()
    if library_row is None:
        return
    solutions = json.loads(library_row["solutions_json"])
    seeds = {template["id"]: template for template in SEED_TEMPLATES}
    for solution in solutions:
        seed = seeds.get(solution.get("id"))
        if seed and solution.get("demo_template"):
            for key in ("title", "source_project_title", "origin_staff_hours_per_week", "reuse_staff_hours_per_week"):
                solution[key] = seed[key]
            solution["reuse_count"] = max(int(solution.get("reuse_count", 0) or 0), seed["reuse_count"])
        if not solution.get("builder_volunteer_id") and solution.get("built_by") in profiles_by_name:
            solution["builder_volunteer_id"] = profiles_by_name[solution["built_by"]]["id"]
        solution.setdefault("origin_staff_hours_per_week", 0)
        solution.setdefault("reuse_staff_hours_per_week", 0)
    connection.execute(
        "UPDATE shared_library SET solutions_json = ? WHERE singleton_id = 1",
        (json.dumps(solutions, ensure_ascii=True),),
    )


def attach_volunteer_profiles(students: list[dict[str, Any]], database_path: Path = DATABASE_PATH) -> None:
    """Copy each volunteer's global settings (pause, causes, hours, trust inputs) onto the roster entry used for matching."""
    if not students:
        return
    with _connection(database_path) as connection:
        for student in students:
            profile = _get_or_create_profile(connection, student)
            profile["skill_levels"] = _skill_levels(connection, profile["id"])
            profile["completed_count"] = len(profile.get("completed_projects", []))
            for key in MATCHING_PROFILE_KEYS:
                if key in profile:
                    student[key] = profile[key]
            student["volunteer_profile_id"] = profile["id"]


def ensure_volunteer_profile(
    student: dict[str, Any],
    overrides: dict[str, Any] | None = None,
    database_path: Path = DATABASE_PATH,
) -> dict[str, Any]:
    initialize_tenant_store(database_path)
    with _connection(database_path) as connection:
        return _get_or_create_profile(connection, student, overrides)


def load_volunteer_profile(profile_id: str, database_path: Path = DATABASE_PATH) -> dict[str, Any] | None:
    initialize_tenant_store(database_path)
    with _connection(database_path) as connection:
        return _load_profile(connection, profile_id)


def load_volunteer_profiles(database_path: Path = DATABASE_PATH) -> dict[str, dict[str, Any]]:
    initialize_tenant_store(database_path)
    with _connection(database_path) as connection:
        rows = connection.execute("SELECT profile_json FROM volunteer_profiles").fetchall()
    profiles = [json.loads(row["profile_json"]) for row in rows]
    return {profile["id"]: profile for profile in profiles}


def find_profile_by_impact_token(token: str, database_path: Path = DATABASE_PATH) -> dict[str, Any] | None:
    """Resolve a private impact link. Invalid, short, or unknown tokens resolve to nothing."""
    if not isinstance(token, str) or len(token) < 20:
        return None
    initialize_tenant_store(database_path)
    with _connection(database_path) as connection:
        row = connection.execute(
            "SELECT impact_token, profile_json FROM volunteer_profiles WHERE impact_token = ?", (token,)
        ).fetchone()
    if row is None or not secrets.compare_digest(row["impact_token"], token):
        return None
    return json.loads(row["profile_json"])


def list_notifications(volunteer_id: str, database_path: Path = DATABASE_PATH) -> list[dict[str, Any]]:
    with _connection(database_path) as connection:
        rows = connection.execute(
            "SELECT * FROM notifications WHERE volunteer_id = ? ORDER BY created_at DESC", (volunteer_id,)
        ).fetchall()
    return [
        {
            **{key: row[key] for key in row.keys() if key != "action_json"},
            "read": bool(row["read"]), "demo": bool(row["demo"]), "action": json.loads(row["action_json"]),
        }
        for row in rows
    ]


def mark_notifications_read(volunteer_id: str, database_path: Path = DATABASE_PATH) -> None:
    with _connection(database_path) as connection:
        connection.execute("UPDATE notifications SET read = 1 WHERE volunteer_id = ?", (volunteer_id,))


def update_volunteer_settings(
    token: str,
    settings: dict[str, Any],
    database_path: Path = DATABASE_PATH,
) -> dict[str, Any] | None:
    """The volunteer edits their own settings from the private impact link."""
    profile = find_profile_by_impact_token(token, database_path)
    if profile is None:
        return None
    if "causes" in settings:
        profile["causes"] = [cause for cause in settings["causes"] if cause in MISSION_AREAS]
    if "hours_per_week" in settings:
        profile["hours_per_week"] = max(1, min(int(settings["hours_per_week"]), 40))
    if "paused" in settings:
        profile["paused"] = bool(settings["paused"])
    if "show_name_consent" in settings:
        profile["show_name_consent"] = bool(settings["show_name_consent"])
    if settings.get("display_name_choice") in DISPLAY_NAME_CHOICES:
        profile["display_name_choice"] = settings["display_name_choice"]
    if "nickname" in settings:
        profile["nickname"] = str(settings["nickname"]).strip()[:40]
    added_skills = []
    if "skills" in settings:
        listed = [skill for skill in settings["skills"] if skill in PRACTICE_TASKS]
        added_skills = [skill for skill in listed if skill not in profile.get("skills", [])]
        profile["skills"] = listed
    with _connection(database_path) as connection:
        _save_profile(connection, profile)
        for skill in added_skills:
            _insert_proof(connection, profile["id"], skill, 1, "Self-listed", "Volunteer")
    return profile


def set_background_check(profile_id: str, cleared: bool, database_path: Path = DATABASE_PATH) -> dict[str, Any]:
    """Coordinator-only: record a cleared background check (needed for projects with vulnerable people)."""
    with _connection(database_path) as connection:
        profile = _load_profile(connection, profile_id)
        if profile is None:
            raise PermissionError("Unknown volunteer.")
        profile["background_check_cleared"] = bool(cleared)
        profile["background_check_date"] = now_iso() if cleared else None
        _save_profile(connection, profile)
    return profile


def give_star(
    organization_id: str,
    project_id: str,
    note: str = "",
    database_path: Path = DATABASE_PATH,
) -> dict[str, Any]:
    """The nonprofit thanks the volunteer: +1 star, one badge per project skill, and a name-free notification."""
    with _connection(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        workspace = connection.execute(
            """SELECT private_workspaces.projects_json, private_workspaces.volunteers_json, organizations.name
               FROM private_workspaces JOIN organizations ON organizations.id = private_workspaces.organization_id
               WHERE private_workspaces.organization_id = ?""",
            (organization_id,),
        ).fetchone()
        if workspace is None:
            raise PermissionError("This nonprofit workspace is not available to this account.")
        projects = json.loads(workspace["projects_json"])
        project = next((item for item in projects if item.get("id") == project_id), None)
        if project is None:
            raise PermissionError("This project is not part of this nonprofit workspace.")
        if project.get("status") != "Done":
            raise ValueError("Stars can only be given after the project is marked done.")
        if project.get("thanks", {}).get("star"):
            raise ValueError("This project already has a star.")
        volunteer = next(
            (item for item in json.loads(workspace["volunteers_json"]) if item.get("id") == project.get("assigned_student_id")),
            None,
        )
        if volunteer is None:
            raise ValueError("This project has no assigned volunteer to thank.")
        clean_note = note.strip()[:500]
        for organization_name in {workspace["name"], project.get("organization", "")}:
            clean_note = scrub_organization(clean_note, organization_name)
        skills = list(dict.fromkeys(project.get("skills", [])))
        profile = _get_or_create_profile(connection, volunteer)
        roster = json.loads(workspace["volunteers_json"])
        annotate_onboarding(roster, projects)
        entry = next(item for item in roster if item.get("id") == volunteer.get("id"))
        was_trusted = entry["onboarding_status"] == TRUSTED
        profile["stars"] = int(profile.get("stars", 0) or 0) + 1
        badges = profile.setdefault("badges", {})
        for skill in skills:
            badges[skill] = int(badges.get(skill, 0)) + 1
            _insert_proof(connection, profile["id"], skill, 4, "Star from a nonprofit", "A nonprofit")
        if clean_note:
            profile.setdefault("thank_you_notes", []).append({
                "note": clean_note, "mission_area": project.get("mission_area", "Other"), "created_at": now_iso(),
            })
        _save_profile(connection, profile)
        project["thanks"] = {"star": True, "note": clean_note, "given_at": now_iso()}
        if not was_trusted and volunteer_status(entry, projects) == TRUSTED and entry.get("onboarding"):
            entry["onboarding"]["trusted_at"] = now_iso()
        for item in roster:
            item.pop("onboarding_status", None)
            item.pop("reviewed_tasks", None)
        connection.execute(
            "UPDATE private_workspaces SET projects_json = ?, volunteers_json = ? WHERE organization_id = ?",
            (json.dumps(projects, ensure_ascii=True), json.dumps(roster, ensure_ascii=True), organization_id),
        )
        extra = f'Their thank-you note:\n"{clean_note}"' if clean_note else ""
        return _notify(connection, profile, "star", star_message(skills), extra=extra, action={"organization_id": organization_id})


def report_concern(
    organization_id: str,
    project_id: str,
    note: str,
    database_path: Path = DATABASE_PATH,
) -> None:
    """A private note to the coordinator. Never shown to the volunteer or in any shared view."""
    if not note.strip():
        raise ValueError("Describe the concern.")
    workspace = load_workspace(organization_id, database_path)
    project = next((item for item in workspace["projects"] if item.get("id") == project_id), None)
    if project is None:
        raise PermissionError("This project is not part of this nonprofit workspace.")
    volunteer = next((item for item in workspace["students"] if item.get("id") == project.get("assigned_student_id")), None)
    with _connection(database_path) as connection:
        connection.execute(
            "INSERT INTO concerns(id, organization_id, project_id, volunteer_id, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (uuid4().hex, organization_id, project_id, (volunteer or {}).get("volunteer_profile_id"), note.strip()[:1000], now_iso()),
        )


def list_concerns(organization_id: str, database_path: Path = DATABASE_PATH) -> list[dict[str, Any]]:
    with _connection(database_path) as connection:
        rows = connection.execute(
            "SELECT * FROM concerns WHERE organization_id = ? ORDER BY created_at DESC", (organization_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def _recent_nudge(connection: sqlite3.Connection, volunteer_id: str) -> bool:
    row = connection.execute(
        "SELECT MAX(created_at) AS latest FROM notifications WHERE volunteer_id = ? AND type = 'nudge'", (volunteer_id,)
    ).fetchone()
    if row is None or not row["latest"]:
        return False
    return datetime.now(timezone.utc) - datetime.fromisoformat(row["latest"]) < timedelta(days=NUDGE_INTERVAL_DAYS)


def send_project_nudges(
    organization_id: str,
    project: dict[str, Any],
    students: list[dict[str, Any]],
    projects: list[dict[str, Any]] | None = None,
    database_path: Path = DATABASE_PATH,
) -> int:
    """Nudge unpaused volunteers whose skills and causes fit a new project. At most one nudge per volunteer per week."""
    already_invited = {item.get("student_id") for item in project.get("invitations", [])} | {project.get("assigned_student_id")}
    sent = 0
    with _connection(database_path) as connection:
        for match in score_students(project, students, projects, limit=None):
            student = match["student"]
            cause_fit = project.get("mission_area", "").casefold() in {cause.casefold() for cause in student.get("causes", [])}
            if student.get("id") in already_invited or not cause_fit or student.get("paused"):
                continue
            profile = _get_or_create_profile(connection, student)
            if profile.get("paused") or _recent_nudge(connection, profile["id"]):
                continue
            _notify(
                connection, profile, "nudge", NUDGE_MESSAGE, extra=nudge_details(project),
                action={"organization_id": organization_id, "project_id": project["id"], "response": None},
            )
            sent += 1
    return sent


def respond_to_nudge(
    token: str,
    notification_id: str,
    accepted: bool,
    database_path: Path = DATABASE_PATH,
) -> str | None:
    """Accept / Not now on a nudge from the private impact link. Returns a message for the volunteer."""
    profile = find_profile_by_impact_token(token, database_path)
    if profile is None:
        return None
    with _connection(database_path) as connection:
        row = connection.execute(
            "SELECT action_json FROM notifications WHERE id = ? AND volunteer_id = ? AND type = 'nudge'",
            (notification_id, profile["id"]),
        ).fetchone()
        if row is None:
            return None
        action = json.loads(row["action_json"])
        action["response"] = "Accepted" if accepted else "Not now"
        connection.execute(
            "UPDATE notifications SET action_json = ?, read = 1 WHERE id = ?",
            (json.dumps(action, ensure_ascii=True), notification_id),
        )
    if not accepted:
        return "No problem. We won't hold this one for you."
    if action.get("demo") or not action.get("organization_id"):
        return "Thanks! (Demo) The coordinator will send you the project card."
    workspace = load_workspace(action["organization_id"], database_path)
    project = next((item for item in workspace["projects"] if item.get("id") == action.get("project_id")), None)
    student = next((item for item in workspace["students"] if item.get("volunteer_profile_id") == profile["id"]), None)
    if project is None or student is None or project.get("assigned_student_id"):
        return "Thanks! This project has already been taken, but we'll keep you in mind."
    message = "Thanks! The coordinator can see you're interested and will reach out."
    if project.get("status") == "Open" and not pending_invitation(project):
        invitation = offer_next_volunteer(project, workspace["students"], workspace["projects"], student_id=student["id"])
        if invitation:
            message = f"Thanks! The project is yours to accept or decline here: {invitation['portal_link']}"
    if not project.get("assigned_student_id") and student["id"] not in project.setdefault("interested_student_ids", []):
        project["interested_student_ids"].append(student["id"])
    save_workspace(action["organization_id"], workspace["projects"], workspace["students"], database_path)
    return message


def community_nonprofits_helped(database_path: Path = DATABASE_PATH) -> int:
    return sum(len(profile.get("completed_projects", [])) for profile in load_volunteer_profiles(database_path).values())


# ---------------------------------------------------------------- proof ladder, practice tasks, safety nets


def list_skill_proofs(volunteer_id: str, *, coordinator: bool = False, database_path: Path = DATABASE_PATH) -> list[dict[str, Any]]:
    """Proof records for one volunteer. Private details (reference names, contacts, links) only for the coordinator."""
    with _connection(database_path) as connection:
        rows = connection.execute(
            "SELECT * FROM skill_proofs WHERE volunteer_id = ? ORDER BY level DESC, created_at DESC", (volunteer_id,)
        ).fetchall()
    proofs = []
    for row in rows:
        proof = {key: row[key] for key in ("id", "skill", "level", "source", "confirmed_by", "created_at")}
        proof["level_label"] = PROOF_LEVELS[row["level"]]
        proof["demo"] = bool(row["demo"])
        if coordinator:
            proof["private"] = json.loads(row["private_details_json"])
        proofs.append(proof)
    return proofs


def add_skill_evidence(
    profile_id: str,
    skill: str,
    evidence_type: str,
    details: dict[str, str],
    confirmed_by: str = "Tech Bridge coordinator",
    database_path: Path = DATABASE_PATH,
) -> None:
    """Coordinator confirms Level 2 evidence: portfolio link, reference, or certificate with a verification link."""
    if skill not in PRACTICE_TASKS:
        raise ValueError("Unknown skill.")
    if evidence_type not in EVIDENCE_TYPES:
        raise ValueError("Choose portfolio link, reference, or certificate.")
    clean = {key: str(value).strip()[:300] for key, value in details.items() if str(value or "").strip()}
    if evidence_type == "Reference" and not (clean.get("reference_name") and clean.get("contact")):
        raise ValueError("A reference needs a name and contact details.")
    if evidence_type != "Reference" and not clean.get("link"):
        raise ValueError("Add the link the coordinator checked.")
    source = {"Portfolio link": "Evidence: portfolio link", "Reference": f"Evidence: reference ({clean.get('relationship', 'reference').lower()})",
              "Certificate with verification link": "Evidence: certificate with verification link"}[evidence_type]
    with _connection(database_path) as connection:
        if _load_profile(connection, profile_id) is None:
            raise PermissionError("Unknown volunteer.")
        _insert_proof(connection, profile_id, skill, 2, source, confirmed_by, clean)


def _update_project(connection: sqlite3.Connection, organization_id: str, project_id: str):
    workspace = connection.execute(
        "SELECT projects_json, volunteers_json FROM private_workspaces WHERE organization_id = ?", (organization_id,)
    ).fetchone()
    if workspace is None:
        raise PermissionError("This nonprofit workspace is not available to this account.")
    projects = json.loads(workspace["projects_json"])
    project = next((item for item in projects if item.get("id") == project_id), None)
    if project is None:
        raise PermissionError("This project is not part of this nonprofit workspace.")
    return projects, project, json.loads(workspace["volunteers_json"])


def approve_as_mentor(
    organization_id: str,
    project_id: str,
    mentor_student_id: str | None,
    database_path: Path = DATABASE_PATH,
) -> dict[str, Any]:
    """Record 'Mentor approved'. mentor_student_id=None means NGO staff reviewed it; otherwise a Mentor on this roster."""
    with _connection(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        projects, project, volunteers = _update_project(connection, organization_id, project_id)
        if project.get("status") not in {"In progress", "Ready for review"}:
            raise ValueError("Only work in progress or ready for review can be approved.")
        annotate_onboarding(volunteers, projects)
        if mentor_student_id is None:
            approval = {"approved_by": NGO_STAFF, "role": "NGO staff"}
        else:
            mentor = next((item for item in volunteers if item.get("id") == mentor_student_id), None)
            if mentor is None or not is_mentor(mentor):
                raise ValueError("Only NGO staff or a Mentor on this nonprofit's roster can approve.")
            if mentor_student_id == project.get("assigned_student_id"):
                raise ValueError("A Mentor can't approve their own project.")
            profile = _get_or_create_profile(connection, mentor)
            approval = {"approved_by": display_name({**profile, "show_name_consent": True}), "role": "Mentor", "mentor_student_id": mentor_student_id}
        approval["approved_at"] = now_iso()
        project["mentor_approval"] = approval
        connection.execute(
            "UPDATE private_workspaces SET projects_json = ? WHERE organization_id = ?",
            (json.dumps(projects, ensure_ascii=True), organization_id),
        )
    return approval


def switch_to_real_data(organization_id: str, project_id: str, database_path: Path = DATABASE_PATH) -> None:
    """Sample data first: Real data only after Mentor approval and if the volunteer meets the personal-data rule."""
    workspace = load_workspace(organization_id, database_path)
    project = next((item for item in workspace["projects"] if item.get("id") == project_id), None)
    if project is None:
        raise PermissionError("This project is not part of this nonprofit workspace.")
    volunteer = next((item for item in workspace["students"] if item.get("id") == project.get("assigned_student_id")), None)
    allowed, reason = real_data_check(project, volunteer)
    if not allowed:
        raise ValueError(reason)
    project["data_mode"] = "Real data"
    save_workspace(organization_id, workspace["projects"], workspace["students"], database_path)


def enrich_profile(profile: dict[str, Any], database_path: Path = DATABASE_PATH) -> dict[str, Any]:
    """A profile with its per-skill proof levels and completed-project count, for display and rule checks."""
    with _connection(database_path) as connection:
        levels = _skill_levels(connection, profile["id"])
    return {**profile, "skill_levels": levels, "completed_count": len(profile.get("completed_projects", []))}


# ---------------------------------------------------------------- NGO-led onboarding


def organization_by_key(key: str, database_path: Path = DATABASE_PATH) -> dict[str, str] | None:
    """Look up a nonprofit for its public 'Volunteer with us' form link (?apply=<key>)."""
    initialize_tenant_store(database_path)
    with _connection(database_path) as connection:
        row = connection.execute("SELECT id, name, organization_key FROM organizations WHERE organization_key = ?", (key or "",)).fetchone()
    return dict(row) if row else None


def organization_form_key(organization_id: str, database_path: Path = DATABASE_PATH) -> str:
    with _connection(database_path) as connection:
        row = connection.execute("SELECT organization_key FROM organizations WHERE id = ?", (organization_id,)).fetchone()
    return row["organization_key"] if row else ""


def _roster_entry_for_email(students: list[dict[str, Any]], email: str) -> dict[str, Any] | None:
    email = email.strip().casefold()
    return next((item for item in students if email and (item.get("email") or "").strip().casefold() == email), None)


def submit_application(organization_id: str, data: dict[str, Any], database_path: Path = DATABASE_PATH) -> dict[str, Any]:
    """Public 'Volunteer with us' form. The application goes to that nonprofit's New applications list only."""
    name = str(data.get("name", "")).strip()[:80]
    email = str(data.get("email", "")).strip()[:120]
    if not name or "@" not in email or email.startswith("@") or email.endswith("@"):
        raise ValueError("Add your name and a valid email.")
    application = {
        "name": name, "email": email, "phone": str(data.get("phone", "")).strip()[:40],
        "skills": [skill for skill in data.get("skills", []) if skill in PRACTICE_TASKS],
        "hours_per_week": max(1, min(int(data.get("hours_per_week", 4) or 4), 40)),
        "causes": [cause for cause in data.get("causes", []) if cause in MISSION_AREAS],
        "note": str(data.get("note", "")).strip()[:500],
        "show_name_consent": bool(data.get("show_name_consent", True)),
        "display_name_choice": data.get("display_name_choice") if data.get("display_name_choice") in DISPLAY_NAME_CHOICES else "initial",
        "nickname": str(data.get("nickname", "")).strip()[:40],
    }
    if not application["skills"]:
        raise ValueError("Pick at least one skill.")
    workspace = load_workspace(organization_id, database_path)
    existing = _roster_entry_for_email(workspace["students"], email)
    if existing is not None:
        wait = reapply_after(existing.get("onboarding") or {})
        if wait is not None:
            raise ValueError(f"Thanks for your interest! You can apply again after {wait.strftime('%B %d, %Y')}.")
        if (existing.get("onboarding") or {}).get("status") != REJECTED:
            raise ValueError("You're already on this nonprofit's volunteer roster. Check your private link for next steps.")
    with _connection(database_path) as connection:
        for row in connection.execute("SELECT application_json FROM applications WHERE organization_id = ? AND status = 'New'", (organization_id,)).fetchall():
            if json.loads(row["application_json"]).get("email", "").casefold() == email.casefold():
                raise ValueError("We already have your application. The nonprofit will be in touch.")
        application_id = uuid4().hex
        connection.execute(
            "INSERT INTO applications(id, organization_id, application_json, status, created_at) VALUES (?, ?, ?, 'New', ?)",
            (application_id, organization_id, json.dumps(application, ensure_ascii=True), now_iso()),
        )
    return {"id": application_id, **application}


def list_applications(organization_id: str, database_path: Path = DATABASE_PATH) -> list[dict[str, Any]]:
    with _connection(database_path) as connection:
        rows = connection.execute(
            "SELECT id, application_json, created_at, demo FROM applications WHERE organization_id = ? AND status = 'New' ORDER BY created_at",
            (organization_id,),
        ).fetchall()
    return [{"id": row["id"], "created_at": row["created_at"], "demo": bool(row["demo"]), **json.loads(row["application_json"])} for row in rows]


def add_application_to_roster(
    organization_id: str,
    application_id: str,
    skills: list[str],
    database_path: Path = DATABASE_PATH,
) -> dict[str, Any]:
    """NGO adds a reviewed application to its private roster with confirmed skill tags. Status: Applicant."""
    with _connection(database_path) as connection:
        row = connection.execute(
            "SELECT application_json, demo FROM applications WHERE id = ? AND organization_id = ? AND status = 'New'",
            (application_id, organization_id),
        ).fetchone()
    if row is None:
        raise PermissionError("This application isn't in your New applications list.")
    application = json.loads(row["application_json"])
    workspace = load_workspace(organization_id, database_path)
    student = _roster_entry_for_email(workspace["students"], application["email"])
    fields = {
        "name": application["name"], "email": application["email"], "phone": application.get("phone", ""),
        "skills": [skill for skill in skills if skill in PRACTICE_TASKS], "hours_per_week": application["hours_per_week"],
        "causes": application["causes"], "bio": application.get("note", "")[:300], "onboarding": new_onboarding(APPLICANT, applied_at=now_iso()),
        "confidentiality_signed": False,
    }
    if student is None:
        student = {"id": uuid4().hex, "major": "", "year": None, "mode": "Remote", "demo_student": bool(row["demo"]), **fields}
        workspace["students"].append(student)
    else:
        student.update(fields)  # A rejected volunteer reapplying after 30 days starts again as an Applicant.
    save_workspace(organization_id, workspace["projects"], workspace["students"], database_path)
    ensure_volunteer_profile(student, {
        "show_name_consent": application["show_name_consent"], "display_name_choice": application["display_name_choice"],
        "nickname": application["nickname"],
    }, database_path)
    with _connection(database_path) as connection:
        connection.execute("UPDATE applications SET status = 'Added' WHERE id = ?", (application_id,))
    return student


def _roster_student(workspace: dict[str, Any], student_id: str) -> dict[str, Any]:
    student = next((item for item in workspace["students"] if item.get("id") == student_id), None)
    if student is None:
        raise PermissionError("This volunteer isn't on this nonprofit's roster.")
    return student


def send_demo_project(
    organization_id: str,
    student_id: str,
    skill: str,
    deadline_days: int = DEMO_DEADLINE_DAYS,
    database_path: Path = DATABASE_PATH,
) -> dict[str, Any]:
    """Send an Applicant a short demo project (fake sample data only) with a deadline. Status: Demo sent."""
    if skill not in PRACTICE_TASKS:
        raise ValueError("There's no demo project for that skill.")
    workspace = load_workspace(organization_id, database_path)
    student = _roster_student(workspace, student_id)
    onboarding = student["onboarding"]
    resend = onboarding["status"] == DEMO_SENT and demo_overdue(onboarding.get("demo"))
    if onboarding["status"] != APPLICANT and not resend:
        raise ValueError("Demo projects go to applicants, or to volunteers whose demo deadline passed.")
    demo = new_demo(skill, max(1, min(int(deadline_days), 30)))
    onboarding.update({"status": DEMO_SENT, "demo": demo})
    save_workspace(organization_id, workspace["projects"], workspace["students"], database_path)
    return demo


def _volunteer_entry(token: str, organization_id: str, student_id: str, database_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """The roster entry behind a private link, only if the link's volunteer owns it."""
    profile = find_profile_by_impact_token(token, database_path)
    if profile is None:
        raise PermissionError("This link is invalid or no longer active.")
    workspace = load_workspace(organization_id, database_path)
    student = _roster_student(workspace, student_id)
    if student.get("volunteer_profile_id") != profile["id"]:
        raise PermissionError("This link is invalid or no longer active.")
    return workspace, student


def submit_demo(token: str, organization_id: str, student_id: str, answers: list[str], database_path: Path = DATABASE_PATH) -> dict[str, Any]:
    """The volunteer submits their demo from their private link. Status: Demo submitted."""
    workspace, student = _volunteer_entry(token, organization_id, student_id, database_path)
    onboarding = student["onboarding"]
    if onboarding["status"] != DEMO_SENT:
        raise ValueError("There's no open demo project to submit.")
    if demo_overdue(onboarding["demo"]):
        raise ValueError("The deadline has passed. Ask the nonprofit to send a new demo project.")
    answers = [str(answer).strip()[:1000] for answer in answers]
    onboarding["demo"].update({"answers": answers, "submitted_at": now_iso(),
                               "auto_check": grade_practice_task(onboarding["demo"]["skill"], answers)})
    onboarding["status"] = DEMO_SUBMITTED
    save_workspace(organization_id, workspace["projects"], workspace["students"], database_path)
    return onboarding["demo"]


def review_demo(
    organization_id: str,
    student_id: str,
    approve: bool,
    feedback: str = "",
    reviewer_student_id: str | None = None,
    database_path: Path = DATABASE_PATH,
) -> dict[str, Any]:
    """A Mentor (NGO staff or a promoted Trusted volunteer) approves or rejects a submitted demo."""
    workspace = load_workspace(organization_id, database_path)
    student = _roster_student(workspace, student_id)
    onboarding = student["onboarding"]
    if onboarding["status"] != DEMO_SUBMITTED:
        raise ValueError("There's no submitted demo to review.")
    if reviewer_student_id is None:
        reviewed_by = NGO_STAFF
    else:
        mentor = _roster_student(workspace, reviewer_student_id)
        if not is_mentor(mentor) or reviewer_student_id == student_id:
            raise ValueError("Only NGO staff or a Mentor on this roster can review demos.")
        reviewed_by = display_name({**load_volunteer_profile(mentor["volunteer_profile_id"], database_path), "show_name_consent": True})
    feedback = feedback.strip()[:300]
    if not approve and not feedback:
        raise ValueError("Add short, kind feedback for the volunteer.")
    onboarding["review"] = {"decision": "Approved" if approve else "Rejected", "feedback": feedback,
                            "reviewed_by": reviewed_by, "reviewed_at": now_iso()}
    onboarding["status"] = APPROVED if approve else REJECTED
    save_workspace(organization_id, workspace["projects"], workspace["students"], database_path)
    if approve:
        with _connection(database_path) as connection:
            _insert_proof(connection, student["volunteer_profile_id"], onboarding["demo"]["skill"], 3,
                          f"Demo project approved: {onboarding['demo']['title']}", "Mentor review")
    return onboarding["review"]


def accept_confidentiality(token: str, organization_id: str, student_id: str, database_path: Path = DATABASE_PATH) -> None:
    """Approved volunteers accept the confidentiality agreement before any real task. Status: Supervised."""
    workspace, student = _volunteer_entry(token, organization_id, student_id, database_path)
    if student["onboarding"]["status"] != APPROVED:
        raise ValueError("The confidentiality agreement comes after your demo project is approved.")
    student["onboarding"].update({"status": SUPERVISED, "confidentiality_accepted_at": now_iso()})
    student["confidentiality_signed"] = True
    save_workspace(organization_id, workspace["projects"], workspace["students"], database_path)
    with _connection(database_path) as connection:
        profile = _load_profile(connection, student["volunteer_profile_id"])
        profile["confidentiality_signed"] = True
        _save_profile(connection, profile)


def promote_to_mentor(organization_id: str, student_id: str, database_path: Path = DATABASE_PATH) -> None:
    """The NGO promotes one of its Trusted volunteers to Mentor."""
    workspace = load_workspace(organization_id, database_path)
    student = _roster_student(workspace, student_id)
    if volunteer_status(student) != TRUSTED:
        raise ValueError("Only Trusted volunteers can become Mentors.")
    student["onboarding"].update({"mentor": True, "mentor_at": now_iso()})
    save_workspace(organization_id, workspace["projects"], workspace["students"], database_path)


def memberships_for_profile(profile_id: str, database_path: Path = DATABASE_PATH) -> list[dict[str, Any]]:
    """Every nonprofit roster this volunteer is on, with their status there. For their own private page only."""
    profile = load_volunteer_profile(profile_id, database_path)
    if profile is None:
        return []
    key = _identity_key(profile)
    with _connection(database_path) as connection:
        rows = connection.execute(
            "SELECT organizations.id, organizations.name, private_workspaces.volunteers_json FROM private_workspaces "
            "JOIN organizations ON organizations.id = private_workspaces.organization_id"
        ).fetchall()
    memberships = []
    for row in rows:
        if not any(_identity_key(item) == key for item in json.loads(row["volunteers_json"])):
            continue
        workspace = load_workspace(row["id"], database_path)
        student = next(item for item in workspace["students"] if _identity_key(item) == key)
        memberships.append({"organization_id": row["id"], "organization_name": row["name"], "student": student,
                            "status": student["onboarding_status"]})
    return memberships


# ---------------------------------------------------------------- volunteer mailbox


def volunteer_mailbox(profile_id: str, organization_id: str | None = None, database_path: Path = DATABASE_PATH) -> list[dict[str, Any]]:
    """Every email this volunteer would get, newest first. With organization_id: only what that nonprofit sent (plus labeled demo mail)."""
    profile = load_volunteer_profile(profile_id, database_path)
    if profile is None:
        return []
    key = _identity_key(profile)
    query = "SELECT organization_id, projects_json, volunteers_json FROM private_workspaces"
    with _connection(database_path) as connection:
        rows = connection.execute(query + (" WHERE organization_id = ?" if organization_id else ""),
                                  (organization_id,) if organization_id else ()).fetchall()
    mails = []
    for row in rows:
        own = [item for item in json.loads(row["volunteers_json"]) if _identity_key(item) == key]
        ids = {item.get("id") for item in own}
        if not own:
            continue
        for student in own:
            mails += onboarding_mails(student, row["organization_id"], profile, APP_BASE_URL)
        for project in json.loads(row["projects_json"]):
            for invitation in project.get("invitations", []):
                if invitation.get("student_id") in ids:
                    mails.append(mail_from_invitation(invitation, project, row["organization_id"]))
            if project.get("assigned_student_id") in ids:
                accepted = next((item for item in project.get("invitations", []) if item.get("status") == "Accepted"), {})
                for change in project.get("change_requests", []):
                    subject, body = changes_requested_notice(project, change.get("comment", ""), accepted.get("portal_link", ""))
                    mails.append(mail_from_change_request(change, subject, body, project, row["organization_id"], accepted.get("portal_link", "")))
    for notification in list_notifications(profile_id, database_path):
        if notification["type"] in DERIVED_TYPES:
            continue
        mail = mail_from_notification(notification)
        if organization_id and mail.get("organization_id") != organization_id and not mail["demo"]:
            continue
        mails.append(mail)
    return sort_mail(mails)


def respond_to_invitation(token: str, organization_id: str, project_id: str, accepted: bool, database_path: Path = DATABASE_PATH) -> str:
    """Accept or decline a project offer from the volunteer's own mailbox."""
    profile = find_profile_by_impact_token(token, database_path)
    if profile is None:
        raise PermissionError("This link is invalid or no longer active.")
    workspace = load_workspace(organization_id, database_path)
    project = next((item for item in workspace["projects"] if item.get("id") == project_id), None)
    invitation = pending_invitation(project) if project else None
    student = next((item for item in workspace["students"] if invitation and item.get("id") == invitation.get("student_id")), None)
    if invitation is None or student is None or student.get("volunteer_profile_id") != profile["id"]:
        raise PermissionError("This offer isn't waiting for your reply.")
    next_offer = respond_to_offer(project, accepted, workspace["students"], workspace["projects"])
    save_workspace(organization_id, workspace["projects"], workspace["students"], database_path)
    if accepted:
        return f"You accepted. Your project page: {invitation.get('portal_link', '')}"
    return "Thanks for letting them know. The project was offered to another volunteer." if next_offer else "Thanks for letting them know."
