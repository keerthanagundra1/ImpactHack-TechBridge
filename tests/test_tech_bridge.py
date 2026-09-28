import json
import ast
import tempfile
import unittest
from pathlib import Path

from tech_bridge import (
    SEED_PROJECTS,
    SEED_STUDENTS,
    HANDOFF_CHECKLIST,
    SEED_TEMPLATES,
    SKILLS,
    build_template_from_project,
    choose_starting_point,
    complete_project,
    extract_bio_skills,
    generate_handoff,
    completion_notice,
    find_duplicate_project,
    find_invitation_by_token,
    fallback_scope,
    impact_summary,
    load_state,
    offer_next_volunteer,
    pending_invitation,
    projects_for_organization,
    new_demo_state,
    record_template_reuse,
    request_changes,
    respond_to_offer,
    sanitize_library_draft,
    save_state,
    score_students,
    search_library,
    send_invitation_email,
    submit_completion,
    validate_scope,
)
from tenant_store import (
    authenticate,
    complete_workspace_project,
    create_account,
    find_invitation,
    initialize_tenant_store,
    load_shared_library,
    load_workspace,
    publish_workspace_solution,
    reset_workspace,
    save_shared_library,
    save_workspace,
)



def own_projects(workspace):
    """A workspace's projects without the labeled demo scenarios added to every seeded workspace."""
    return [project for project in workspace["projects"] if not project.get("demo_scenario")]

class TechBridgeTests(unittest.TestCase):
    def test_seed_data_is_fictional_and_uses_fixed_skills(self):
        self.assertEqual(len(SEED_PROJECTS), 8)
        self.assertEqual(len(SEED_STUDENTS), 41)  # 40 roster volunteers + Alex (proof-ladder demo)
        self.assertEqual(len({student['email'] for student in SEED_STUDENTS}), 41)
        self.assertTrue(set(SKILLS) <= {skill for student in SEED_STUDENTS for skill in student['skills']})
        allowed = {skill for student in SEED_STUDENTS for skill in student["skills"]}
        self.assertTrue(allowed)
        self.assertTrue(all(template["data_free"] for template in SEED_TEMPLATES))
        self.assertTrue(all(template["built_by"] != "Tech Bridge demo team" for template in SEED_TEMPLATES))
        self.assertTrue(all(template["reuse_count"] > 0 for template in SEED_TEMPLATES))
        self.assertTrue(all(template["source_project_status"] == "Done" for template in SEED_TEMPLATES))
        self.assertFalse(any(template["id"] == "tpl-adoptable-pets" for template in SEED_TEMPLATES))
        self.assertTrue(all(project["demo_project"] for project in SEED_PROJECTS))
        self.assertTrue(all(student["demo_student"] for student in SEED_STUDENTS))
        self.assertTrue(all(template["demo_template"] for template in SEED_TEMPLATES))

        oak_cliff = next(project for project in SEED_PROJECTS if project["organization"] == "Oak Cliff Community Pantry")
        reuse_projects = [project for project in SEED_PROJECTS if project["organization"] in {"North Dallas Food Share", "Garland Meals", "Irving Youth League"}]
        paws = next(project for project in SEED_PROJECTS if project["organization"] == "Paws of Plano Rescue")
        self.assertTrue(oak_cliff["library_consent"])
        self.assertEqual(oak_cliff["library_template_id"], "tpl-volunteer-intake")
        self.assertEqual(oak_cliff["assigned_student_id"], next(student["id"] for student in SEED_STUDENTS if student["name"] == "Priya Shah"))
        self.assertEqual(len(reuse_projects), 3)
        self.assertTrue(all(project["status"] == "Done" and project["reuse_template_id"] == "tpl-volunteer-intake" for project in reuse_projects))
        self.assertTrue(all(project["status"] == "Done" for project in reuse_projects))
        self.assertEqual(paws["status"], "Open")
        self.assertIsNone(paws["reuse_template_id"])
        paws_scope = fallback_scope(
            paws["organization"], paws["mission_area"], paws["tech_comfort"], paws["problem_summary"], new_demo_state()["templates"],
        )
        self.assertIsNone(paws_scope["matching_template_id"])
        self.assertEqual(paws_scope["effort_hours"], 18)

    def test_scoring_weights_skills_and_returns_top_three(self):
        project = {"skills": ["Google Sheets/Excel", "Apps Script"], "effort_hours": 8, "mission_area": "Food",
                   "difficulty": "Beginner", "reuse_template_id": "tpl-volunteer-intake"}
        matches = score_students(project, SEED_STUDENTS)
        self.assertEqual(len(matches), 3)
        self.assertEqual(matches[0]["student"]["name"], "Priya Shah")  # Nonprofit-verified in both skills
        self.assertAlmostEqual(matches[0]["score"], 1.0)
        self.assertLess(matches[2]["score"], matches[0]["score"])

    def test_matching_filters_low_skill_coverage_and_tie_breaks_by_hours(self):
        project = {"skills": ["Google Sheets/Excel", "Apps Script"], "effort_hours": 8, "mission_area": "Food", "difficulty": "Beginner"}
        students = [
            {"id": "junior", "name": "Junior", "skills": project["skills"], "hours_per_week": 10, "causes": ["Food"], "year": 2},
            {"id": "senior-busy", "name": "Senior busy", "skills": project["skills"], "hours_per_week": 2, "causes": ["Food"], "year": 4},
            {"id": "senior-free", "name": "Senior free", "skills": project["skills"], "hours_per_week": 8, "causes": ["Food"], "year": 4},
            {"name": "Half coverage", "skills": ["Google Sheets/Excel"], "hours_per_week": 10, "causes": ["Food"], "year": 2},
            {"name": "Below threshold", "skills": [], "hours_per_week": 10, "causes": ["Food"], "year": 2},
        ]
        for student in students:
            # Only approved volunteers (Supervised, confidentiality accepted) get real projects.
            student["onboarding"] = {"status": "Supervised"}
            student["confidentiality_signed"] = True
        active_projects = [{"assigned_student_id": "senior-busy", "status": "In progress"}]
        matches = score_students(project, students, active_projects)
        self.assertEqual([match["student"]["name"] for match in matches], ["Senior free", "Senior busy", "Junior"])

    def test_duplicate_detection_requires_same_org_and_similar_summary(self):
        projects = [{
            "id": "existing-1", "organization": "North Dallas Food Bank",
            "problem_summary": "Every Friday, we copy volunteer names from three Excel files into one list.",
        }]
        duplicate = find_duplicate_project(
            projects, "north dallas food bank", "Every Friday we copy volunteer names from three Excel files into one list!",
        )
        self.assertEqual(duplicate["id"], "existing-1")
        near_duplicate = find_duplicate_project(
            projects, "North Dallas Food Bank", "Every Friday we copy volunteer names from three Excel files into one list for our team.",
        )
        self.assertEqual(near_duplicate["id"], "existing-1")
        self.assertIsNone(find_duplicate_project(projects, "Different Pantry", projects[0]["problem_summary"]))
        self.assertIsNone(find_duplicate_project(projects, "North Dallas Food Bank", "We need an animal shelter website."))

    def test_demo_walkthrough_examples_route_to_reuse_and_new_build(self):
        state = new_demo_state()
        pantry_card = fallback_scope(
            "Demo Pantry Two", "Food", "Basic",
            "We copy volunteer names from several spreadsheets every week and it takes forever.",
            state["templates"],
        )
        animal_card = fallback_scope(
            "Demo Animal Shelter", "Animals", "Basic",
            "Our shelter website needs a multilingual, accessible intake workflow that our current platform cannot support.",
            state["templates"],
        )
        self.assertEqual(pantry_card["matching_template_id"], "tpl-volunteer-intake")
        self.assertEqual(pantry_card["effort_hours"], 1)
        self.assertIsNone(animal_card["matching_template_id"])
        self.assertEqual(animal_card["effort_hours"], 18)

    def test_every_streamlit_form_has_submit_button(self):
        app_path = Path(__file__).parents[1] / "app.py"
        syntax_tree = ast.parse(app_path.read_text(encoding="utf-8"))
        form_blocks = [
            node for node in ast.walk(syntax_tree)
            if isinstance(node, (ast.With, ast.AsyncWith))
            and any(
                isinstance(context.context_expr, ast.Call)
                and isinstance(context.context_expr.func, ast.Attribute)
                and context.context_expr.func.attr == "form"
                for context in node.items
            )
        ]
        self.assertTrue(form_blocks)
        for form_block in form_blocks:
            self.assertTrue(any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "form_submit_button"
                for node in ast.walk(form_block)
            ))

    def test_keyword_fallback_finds_volunteer_spreadsheet_pattern(self):
        card = fallback_scope("Demo Pantry", "Food", "Basic", "We combine volunteer Excel spreadsheets every week", SEED_TEMPLATES)
        self.assertEqual(card["matching_template_id"], "tpl-volunteer-intake")
        self.assertEqual(card["library_match_similarity"], 88)
        self.assertEqual(card["effort_hours"], 1)

    def test_volunteer_problem_is_a_new_build_without_library_entry(self):
        library = [template for template in new_demo_state()["templates"] if template["id"] != "tpl-volunteer-intake"]
        card = fallback_scope("Oak Cliff", "Food", "Basic", "We copy volunteer names from three Excel spreadsheets", library)
        self.assertIsNone(card["matching_template_id"])
        self.assertEqual(card["library_match_similarity"], 0)
        self.assertEqual(card["effort_hours"], 8)

    def test_unmatched_problem_does_not_inherit_unrelated_mission_template(self):
        library = new_demo_state()["templates"]
        book_card = fallback_scope("North Dallas", "Education", "None", "need help in organising books", library)
        self.assertEqual(book_card["problem_summary"], "need help in organising books")
        self.assertEqual(book_card["problem_type"], "Book inventory organization")
        self.assertIn("book inventory", book_card["suggested_solution"].casefold())
        self.assertNotIn("attendance", book_card["suggested_solution"].casefold())
        self.assertIsNone(book_card["matching_template_id"])

        general_card = fallback_scope("North Dallas", "Education", "None", "Need help organizing our weekly staff process", library)
        self.assertEqual(general_card["problem_type"], "Workflow improvement")
        self.assertNotIn("attendance", general_card["suggested_solution"].casefold())

    def test_education_video_request_gets_mission_aware_media_solution(self):
        card = fallback_scope("North Dallas", "Education", "Basic", "we need help on building education videos", new_demo_state()["templates"])
        self.assertEqual(card["problem_type"], "Educational video production")
        self.assertIn("learners", card["suggested_solution"])
        self.assertIn("Canva/Graphics", card["skills"])
        self.assertNotIn("Google Sheets/Excel", card["tools"])
        self.assertIsNone(card["matching_template_id"])

    def test_clear_task_outranks_incidental_keyword_matches(self):
        library = new_demo_state()["templates"]
        video = fallback_scope("X", "Education", "Basic", "We want to record short lesson videos learners can watch at home, but no one knows how to film or edit them.", library)
        feedback = fallback_scope("X", "Health", "Basic", "After each health fair we hand out paper feedback forms, then someone types the answers into a spreadsheet.", library)
        website = fallback_scope("X", "Other", "Basic", "Our website is outdated and only one former volunteer knew how to update it.", library)
        donors = fallback_scope("X", "Women and families", "Basic", "Our director spends hours writing thank-you emails to donors one by one.", library)
        self.assertEqual(video["problem_type"], "Educational video production")
        self.assertEqual(feedback["problem_type"], "Feedback collection and summary")
        self.assertEqual(website["problem_type"], "Website update workflow")
        self.assertTrue(all(card["matching_template_id"] is None for card in (video, feedback, website)))
        self.assertEqual(donors["matching_template_id"], "tpl-donor-thanks")

    def test_food_distribution_problem_does_not_match_volunteer_merger_or_pet_site(self):
        card = fallback_scope(
            "North Dallas Food Bank", "Food", "Basic",
            "every friday need volunteers to distribute food", new_demo_state()["templates"],
        )
        self.assertEqual(card["problem_type"], "Food distribution volunteer coordination")
        self.assertIn("distribution shifts", card["suggested_solution"])
        self.assertNotIn("spreadsheet", card["suggested_solution"].casefold())
        self.assertNotIn("shelter", card["suggested_solution"].casefold())
        self.assertIsNone(card["matching_template_id"])
        self.assertEqual(card["effort_hours"], 8)

    def test_new_build_can_be_sanitized_published_and_reused(self):
        state = new_demo_state()
        state["templates"] = [template for template in state["templates"] if template["id"] != "tpl-volunteer-intake"]
        first_card = fallback_scope("Oak Cliff Community Pantry", "Food", "Basic", "We copy volunteer names from three Excel files into one list every Friday.", state["templates"])
        self.assertIsNone(first_card["matching_template_id"])
        self.assertEqual(first_card["effort_hours"], 8)
        project = {
            "id": "first-build", "organization": "Oak Cliff Community Pantry",
            "problem_summary": first_card["problem_summary"], "problem_type": first_card["problem_type"],
            "suggested_solution": "A shared sheet for Oak Cliff Community Pantry contact 555-123-4567 and jane@example.org",
            "tools": first_card["tools"], "skills": first_card["skills"],
            "deliverables": first_card["deliverables"], "mission_area": "Food",
            "build_effort_hours": 8, "effort_hours": 8,
        }
        draft, warning = sanitize_library_draft(project, "Priya Shah")
        self.assertIsNone(warning)
        public_text = " ".join([draft["title"], draft["summary"], draft["handoff_guide"], *draft["steps"]])
        self.assertNotIn("Oak Cliff Community Pantry", public_text)
        self.assertNotIn("555-123-4567", public_text)
        self.assertNotIn("jane@example.org", public_text)
        template = build_template_from_project(project, draft, "Priya Shah")
        self.assertEqual(template["title"], "Volunteer Sign-up Sheet")
        self.assertEqual(template["built_by"], "Priya Shah")
        second_card = fallback_scope("Garland Meals", "Food", "Basic", "We copy volunteer names from several spreadsheets every week and it takes forever.", state["templates"] + [template])
        self.assertEqual(second_card["matching_template_id"], template["id"])
        self.assertEqual(second_card["library_match_similarity"], 88)
        self.assertEqual(second_card["effort_hours"], 1)
        self.assertTrue(record_template_reuse(state["templates"] + [template], template["id"]))
        self.assertEqual(template["reuse_count"], 1)
        impact = impact_summary([
            {"organization": "Oak Cliff Community Pantry", "status": "Done", "hours_wasted_per_week": 3, "effort_hours": 8, "build_effort_hours": 8, "library_template_id": template["id"]},
            {"organization": "Garland Meals", "status": "Done", "hours_wasted_per_week": 3, "effort_hours": 1, "build_effort_hours": 8, "reuse_template_id": template["id"]},
        ], [template])
        self.assertEqual(impact["new_builds"], 1)
        self.assertEqual(impact["nonprofits_helped"], 2)
        self.assertEqual(impact["staff_hours_saved_per_week"], 6)
        self.assertEqual(impact["volunteer_hours_saved_by_reuse"], 7)
        self.assertEqual(impact["headline_volunteer_projects"], 1)
        self.assertEqual(impact["headline_nonprofits_helped"], 2)
        self.assertEqual(impact["headline"], "Volunteer Sign-up Sheet: 1 volunteer project -> 2 nonprofits helped")
        self.assertEqual(impact["average_reuse_reach"], 2.0)

    def test_impact_headline_uses_most_reused_solution_and_pluralizes(self):
        templates = [
            {"id": "one", "title": "One solution", "reuse_count": 0, "data_free": True, "source_project_status": "Done"},
            {"id": "most", "title": "Most reused", "reuse_count": 3, "data_free": True, "source_project_status": "Done"},
        ]
        impact = impact_summary([], templates)
        self.assertEqual(impact["headline"], "Most reused: 1 volunteer project -> 4 nonprofits helped")
        templates[1]["reuse_count"] = 0
        self.assertEqual(impact_summary([], templates)["headline"], "One solution: 1 volunteer project -> 1 nonprofit helped")

    def test_reuse_count_increments_only_on_first_completion(self):
        templates = [{"id": "shared", "reuse_count": 3}]
        project = {"status": "In progress", "reuse_template_id": "shared"}
        with self.assertRaises(ValueError):
            complete_project(project, templates, "Guide")  # Mentor approval first.
        self.assertEqual(templates[0]["reuse_count"], 3)
        project["mentor_approval"] = {"approved_by": "Tech Bridge coordinator", "role": "Coordinator"}
        complete_project(project, templates, "Guide")
        self.assertEqual(templates[0]["reuse_count"], 4)
        self.assertEqual(project["status"], "Done")
        complete_project(project, templates, "Guide refreshed")
        self.assertEqual(templates[0]["reuse_count"], 4)

    def test_reset_state_contains_expected_seed_and_no_pet_library_entry(self):
        state = new_demo_state()
        self.assertEqual(len(state["projects"]), 8)
        self.assertEqual(len(state["templates"]), 4)
        self.assertFalse(any(template["id"] == "tpl-adoptable-pets" for template in state["templates"]))

    def test_student_bio_skill_fallback_uses_only_fixed_skills(self):
        skills, error = extract_bio_skills("I build Python dashboards and automate spreadsheets with Apps Script.")
        self.assertIsNone(error)
        self.assertEqual(skills, ["Google Sheets/Excel", "Apps Script", "Python"])

    def test_validation_drops_unapproved_skills_and_template_ids(self):
        card = validate_scope({
            "skills": ["Python", "invented skill"], "matching_template_id": "not-a-template",
            "deliverables": ["One", "Two", "Three"], "effort_hours": 99,
        }, SEED_TEMPLATES)
        self.assertEqual(card["skills"], ["Python"])
        self.assertIsNone(card["matching_template_id"])
        self.assertEqual(card["effort_hours"], 24)

    def test_validation_handles_malformed_ai_fields(self):
        card = validate_scope({
            "skills": "Python", "tools": None, "deliverables": "not a list",
            "hours_wasted_per_week": "unknown",
        }, SEED_TEMPLATES)
        self.assertEqual(card["skills"], [])
        self.assertEqual(card["tools"], [])
        self.assertEqual(len(card["deliverables"]), 3)
        self.assertEqual(card["hours_wasted_per_week"], 0)

    def test_json_state_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            expected = {"projects": [], "students": [], "templates": [], "demo_seed_version": 6}
            save_state(expected, path)
            self.assertEqual(load_state(path), expected)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), expected)

    def test_demo_migration_preserves_non_demo_records_and_remaps_students(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            custom_project = {"id": "custom-project", "demo_project": False, "assigned_student_id": "legacy-priya", "status": "Open"}
            custom_student = {"id": "custom-student", "demo_student": False, "name": "Community Student"}
            custom_template = {"id": "custom-template", "demo_template": False, "title": "Community Template"}
            save_state({
                "projects": [{"id": "legacy-demo-project", "demo_project": True}, custom_project],
                "students": [{"id": "legacy-priya", "demo_student": True, "name": "Priya Shah"}, custom_student],
                "templates": [{"id": "legacy-demo-template", "demo_template": True}, custom_template],
                "demo_seed_version": 5,
            }, path)
            migrated = load_state(path)
            self.assertEqual(migrated["demo_seed_version"], 6)
            self.assertEqual(len([project for project in migrated["projects"] if project.get("demo_project")]), 8)
            self.assertEqual(next(project for project in migrated["projects"] if project["id"] == "custom-project")["assigned_student_id"], next(student["id"] for student in migrated["students"] if student["name"] == "Priya Shah"))
            self.assertTrue(any(student["id"] == "custom-student" for student in migrated["students"]))
            self.assertTrue(any(template["id"] == "custom-template" for template in migrated["templates"]))

    def test_nonprofit_accounts_isolate_workspaces_and_share_only_library(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tenants.sqlite3"
            initialize_tenant_store(path, [{"id": "shared-solution", "title": "Shared"}])
            alpha = create_account("Alpha Pantry", "alpha@example.org", "alpha-password-123", path)
            beta = create_account("Beta Pantry", "beta@example.org", "beta-password-456", path)
            self.assertIsNotNone(authenticate("ALPHA@example.org", "alpha-password-123", path))
            self.assertIsNone(authenticate("alpha@example.org", "wrong-password", path))

            save_workspace(alpha["organization_id"], [{"id": "alpha-project"}], [{"id": "alpha-volunteer"}], path)
            save_workspace(beta["organization_id"], [{"id": "beta-project"}], [{"id": "beta-volunteer"}], path)
            self.assertEqual(own_projects(load_workspace(alpha["organization_id"], path)), [{"id": "alpha-project"}])
            self.assertEqual(own_projects(load_workspace(beta["organization_id"], path)), [{"id": "beta-project"}])

            save_shared_library([{"id": "shared-solution", "title": "Updated shared"}], path)
            self.assertEqual(load_shared_library(path)[0]["title"], "Updated shared")
            reset_workspace(alpha["organization_id"], path)
            self.assertEqual(own_projects(load_workspace(alpha["organization_id"], path)), [])
            self.assertEqual(len(load_workspace(alpha["organization_id"], path)["students"]), len(SEED_STUDENTS))
            self.assertEqual(own_projects(load_workspace(beta["organization_id"], path)), [{"id": "beta-project"}])
            self.assertEqual(load_shared_library(path)[0]["title"], "Updated shared")

    def test_seed_nonprofit_account_gets_only_its_own_demo_project(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tenants.sqlite3"
            initialize_tenant_store(path, [])
            pantry = create_account("Oak Cliff Community Pantry", "pantry@example.org", "pantry-password-123", path)
            workspace = load_workspace(pantry["organization_id"], path)
            self.assertEqual([project["organization"] for project in own_projects(workspace)], ["Oak Cliff Community Pantry"])
            self.assertEqual(len(workspace["students"]), len(SEED_STUDENTS))

    def test_complete_reuse_and_publish_solution_are_atomic_and_tenant_scoped(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tenants.sqlite3"
            initial_library = [{"id": "shared", "title": "Shared solution", "reuse_count": 2, "data_free": True}]
            initialize_tenant_store(path, initial_library)
            alpha = create_account("Alpha Pantry", "alpha@example.org", "alpha-password-123", path)
            beta = create_account("Beta Pantry", "beta@example.org", "beta-password-456", path)
            reuse_project = {"id": "reuse-project", "status": "In progress", "reuse_template_id": "shared",
                             "mentor_approval": {"approved_by": "Tech Bridge coordinator", "role": "Coordinator"}}
            new_project = {"id": "new-build", "status": "Done", "library_consent": True}
            save_workspace(alpha["organization_id"], [reuse_project, new_project], [], path)

            complete_workspace_project(alpha["organization_id"], "reuse-project", "Private guide", path)
            self.assertEqual(load_shared_library(path)[0]["reuse_count"], 3)
            complete_workspace_project(alpha["organization_id"], "reuse-project", "Updated guide", path)
            self.assertEqual(load_shared_library(path)[0]["reuse_count"], 3)

            solution = {"id": "published", "title": "Reviewed solution", "data_free": True}
            solutions, projects = publish_workspace_solution(alpha["organization_id"], "new-build", solution, path)
            self.assertEqual(solutions[-1]["id"], "published")
            self.assertEqual(next(project for project in projects if project["id"] == "new-build")["library_template_id"], "published")
            self.assertEqual(own_projects(load_workspace(beta["organization_id"], path)), [])

            with self.assertRaises(ValueError):
                publish_workspace_solution(alpha["organization_id"], "reuse-project", {"id": "bad", "data_free": True}, path)


class VolunteerOfferFlowTests(unittest.TestCase):
    def setUp(self):
        self.students = json.loads(json.dumps(SEED_STUDENTS))
        self.project = {
            "id": "p1", "organization": "Oak Cliff", "mission_area": "Food", "problem_type": "Volunteer data consolidation",
            "problem_summary": "We copy volunteer names from spreadsheets", "suggested_solution": "Shared sheet",
            "skills": ["Google Sheets/Excel"], "difficulty": "Beginner", "effort_hours": 8, "status": "Open",
            "assigned_student_id": None, "deliverables": ["Build the sheet"], "privacy_notes": "Use sample data.",
        }

    def test_posting_emails_top_match_with_card_and_library_link(self):
        top = score_students(self.project, self.students, limit=None)[0]["student"]
        invitation = offer_next_volunteer(self.project, self.students)
        self.assertEqual(invitation["student_id"], top["id"])
        self.assertEqual(self.project["status"], "Offered")
        self.assertIn("library_search=", invitation["library_link"])
        self.assertIn(invitation["library_link"], invitation["body"])
        self.assertIn("Shared sheet", invitation["body"])
        self.assertIsNone(offer_next_volunteer(self.project, self.students))

    def test_decline_passes_to_next_volunteer_and_accept_assigns(self):
        ranked = [match["student"]["id"] for match in score_students(self.project, self.students, limit=None)]
        offer_next_volunteer(self.project, self.students)
        next_invitation = respond_to_offer(self.project, False, self.students)
        self.assertEqual(next_invitation["student_id"], ranked[1])
        self.assertEqual(self.project["declined_student_ids"], [ranked[0]])
        self.assertEqual(self.project["status"], "Offered")
        respond_to_offer(self.project, True, self.students)
        self.assertEqual(self.project["assigned_student_id"], ranked[1])
        self.assertEqual(self.project["status"], "In progress")
        self.assertIsNone(pending_invitation(self.project))

    def test_project_returns_to_open_when_every_match_declines(self):
        offer_next_volunteer(self.project, self.students)
        while pending_invitation(self.project):
            respond_to_offer(self.project, False, self.students)
        self.assertEqual(self.project["status"], "Open")
        self.assertIsNone(self.project["assigned_student_id"])

    def test_library_search_and_starting_point(self):
        results = search_library("volunteer spreadsheet", SEED_TEMPLATES)
        self.assertEqual(results[0][1]["id"], "tpl-volunteer-intake")
        self.assertEqual(len(search_library("", SEED_TEMPLATES)), len(SEED_TEMPLATES))
        choose_starting_point(self.project, results[0][1])
        self.assertEqual(self.project["reuse_template_id"], "tpl-volunteer-intake")
        self.assertEqual(self.project["effort_hours"], 1)
        choose_starting_point(self.project, None)
        self.assertIsNone(self.project["reuse_template_id"])
        self.assertEqual(self.project["effort_hours"], 8)

    def test_invitation_has_private_portal_link_and_demo_delivery(self):
        invitation = offer_next_volunteer(self.project, self.students)
        self.assertGreaterEqual(len(invitation["token"]), 20)
        self.assertIn(f"invite={invitation['token']}", invitation["portal_link"])
        self.assertIn(invitation["portal_link"], invitation["body"])
        self.assertTrue(invitation["delivery"].startswith("Demo inbox only"))
        self.assertIs(find_invitation_by_token(self.project, invitation["token"]), invitation)
        self.assertIsNone(find_invitation_by_token(self.project, "not-a-real-token-value-123"))
        self.assertEqual(send_invitation_email({"to": ""}), "Demo inbox only (no email on file)")

    def test_invitation_token_resolves_only_to_its_workspace_project(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tenants.sqlite3"
            initialize_tenant_store(path, [])
            alpha = create_account("Alpha Pantry", "alpha@example.org", "alpha-password-123", path)
            offer_next_volunteer(self.project, self.students)
            token = pending_invitation(self.project)["token"]
            save_workspace(alpha["organization_id"], [self.project], self.students, path)
            self.assertEqual(find_invitation(token, path), (alpha["organization_id"], "p1"))
            self.assertIsNone(find_invitation("x" * 32, path))
            self.assertIsNone(find_invitation("", path))

    def test_volunteer_handoff_needs_review_and_changes_go_back_to_volunteer(self):
        self.project["status"] = "In progress"
        submit_completion(self.project, ["https://example.org/sheet", " "], "A shared sheet", "Open it every Friday", "", HANDOFF_CHECKLIST + ["bogus"], "Priya Shah")
        self.assertEqual(self.project["status"], "Ready for review")
        self.assertEqual(self.project["completion"]["links"], ["https://example.org/sheet"])
        self.assertEqual(self.project["completion"]["checklist"], HANDOFF_CHECKLIST)
        subject, body = completion_notice(self.project, "http://localhost:8501")
        self.assertIn("Ready for review", subject)
        self.assertIn("https://example.org/sheet", body)
        request_changes(self.project, "Please add a Totals tab")
        self.assertEqual(self.project["status"], "In progress")
        self.assertEqual(self.project["change_requests"][-1]["comment"], "Please add a Totals tab")
        guide, _ = generate_handoff(self.project, {"name": "Priya Shah"})
        self.assertIn("https://example.org/sheet", guide)
        self.assertIn("Open it every Friday", guide)

    def test_nonprofit_can_publish_confirmed_new_build_without_upfront_consent(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tenants.sqlite3"
            initialize_tenant_store(path, [])
            alpha = create_account("Alpha Pantry", "alpha@example.org", "alpha-password-123", path)
            save_workspace(alpha["organization_id"], [{"id": "built", "status": "Done", "library_consent": False}], [], path)
            _, projects = publish_workspace_solution(alpha["organization_id"], "built", {"id": "tpl-new", "data_free": True}, path)
            self.assertEqual(projects[0]["library_template_id"], "tpl-new")
            self.assertTrue(projects[0]["library_consent"])

    def test_impact_projects_are_limited_to_signed_in_nonprofit(self):
        projects = [{"organization": "Red Cross"}, {"organization": "redcross"}, {"organization": "Demo Animal Shelter"}]
        self.assertEqual(len(projects_for_organization(projects, "redcross")), 2)


if __name__ == "__main__":
    unittest.main()