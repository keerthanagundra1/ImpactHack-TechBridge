from __future__ import annotations

import json
import os
import secrets
from datetime import datetime
from uuid import uuid4

import streamlit as st

from tech_bridge import (
    MISSION_AREAS,
    SKILLS,
    VOLUNTEER_HOURLY_VALUE,
    HANDOFF_CHECKLIST,
    REVIEW_STATUS,
    APP_BASE_URL,
    MENTOR_APPROVAL_REQUIRED,
    AssignmentBlocked,
    assign_volunteer,
    build_template_from_project,
    changes_requested_notice,
    completion_notice,
    choose_starting_point,
    extract_bio_skills,
    find_invitation_by_token,
    find_duplicate_project,
    generate_handoff,
    impact_summary,
    offer_next_volunteer,
    pending_invitation,
    projects_for_organization,
    request_changes,
    respond_to_offer,
    sanitize_library_draft,
    score_students,
    scope_problem,
    search_library,
    send_email,
    submit_completion,
    suggest_thank_you_note,
)
from tenant_store import (
    authenticate,
    community_nonprofits_helped,
    complete_workspace_project,
    create_account,
    ensure_demo_account,
    ensure_volunteer_profile,
    find_invitation,
    find_profile_by_impact_token,
    give_star,
    list_concerns,
    list_notifications,
    load_volunteer_profile,
    load_volunteer_profiles,
    mark_notifications_read,
    organization_email,
    initialize_tenant_store,
    load_shared_library,
    load_workspace,
    publish_workspace_solution,
    report_concern,
    reset_workspace,
    respond_to_nudge,
    save_workspace,
    send_project_nudges,
    accept_confidentiality,
    add_application_to_roster,
    add_skill_evidence,
    approve_as_mentor,
    enrich_profile,
    list_applications,
    list_skill_proofs,
    memberships_for_profile,
    organization_by_key,
    organization_form_key,
    promote_to_mentor,
    respond_to_invitation,
    review_demo,
    volunteer_mailbox,
    send_demo_project,
    set_background_check,
    submit_application,
    submit_demo,
    switch_to_real_data,
    update_volunteer_settings,
)
from onboarding import (
    APPLICANT,
    APPROVED,
    DEMO_DEADLINE_DAYS,
    DEMO_SENT,
    DEMO_SUBMITTED,
    REAPPLY_DAYS,
    REJECTED,
    STATUS_PATH,
    STATUS_STEP,
    SUPERVISED,
    TRUSTED,
    TRUSTED_TASKS,
    assignment_check,
    demo_overdue,
    is_mentor,
    mentor_review_required,
    progress_text,
    real_data_check,
    reapply_after,
    suggested_demo_skill,
)
from demo_scenarios import SCENARIOS
from skill_checks import PRACTICE_TASKS
from volunteer_mailbox import MAIL_ICONS, REPLY_GUIDE
from volunteer_retention import (
    DATA_SENSITIVITY,
    DISPLAY_NAME_CHOICES,
    EVIDENCE_TYPES,
    PROOF_ICONS,
    REFERENCE_RELATIONSHIPS,
    badge_label,
    builder_credit,
    format_skill_proofs,
    WORK_NEW_BUILD,
    WORK_SETUP,
    project_work_type,
    skill_proof_lines,
    certificate_html,
    effort_warning,
    impact_link,
    linkedin_snippet,
    milestone_message,
    mission_phrase,
    plural,
    project_data_sensitivity,
    public_credit_name,
    public_profile,
    volunteer_impact,
)

st.set_page_config(page_title="Tech Bridge", page_icon="TB", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Fraunces:opsz,wght@9..144,600;9..144,700&display=swap');
    :root { --ink:#192b28; --muted:#64716d; --paper:#f6f8f5; --line:#dce5df; --green:#166b52; --mint:#e5f2eb; --coral:#e36f51; --gold:#e9b94e; }
    html, body, [class*="css"] { font-family:'DM Sans', sans-serif; color:var(--ink); }
    .stApp { background:var(--paper); }
    [data-testid="stHeader"] { background:transparent; }
    .block-container { max-width:1280px; padding-top:1.5rem; padding-bottom:3rem; }
    h1, h2, h3 { color:var(--ink); }
    h1 { font-family:'Fraunces', Georgia, serif; font-size:2.6rem; margin-bottom:.1rem; }
    .brandline { color:var(--muted); font-size:.9rem; margin-bottom:1.2rem; }
    .problem-stat { margin:.35rem 0 1.1rem; color:var(--green); font-size:.95rem; font-weight:600; }
    .eyebrow { color:var(--green); font-weight:700; text-transform:uppercase; font-size:.72rem; letter-spacing:.08em; }
    .panel { background:white; border:1px solid var(--line); border-radius:8px; padding:1.15rem 1.25rem; margin:.3rem 0 1rem; }
    .library-card { background:white; border:1px solid var(--line); border-left:4px solid var(--green); border-radius:6px; padding:1rem 1.1rem; margin:.6rem 0; }
    .callout { background:var(--mint); border-radius:6px; padding:.75rem 1rem; color:var(--ink); margin:.5rem 0 1rem; }
    .privacy { background:#fff1e9; border-left:4px solid var(--coral); border-radius:4px; padding:.75rem 1rem; margin:.5rem 0 1rem; }
    .small-muted { color:var(--muted); font-size:.85rem; }
    .status-pill { display:inline-block; background:var(--mint); color:var(--green); border-radius:12px; padding:.2rem .55rem; font-size:.75rem; font-weight:700; }
    div[data-testid="stMetric"] { background:white; border:1px solid var(--line); border-radius:7px; padding:.8rem 1rem; }
    div[data-testid="stMetricLabel"] { color:var(--muted); }
    .stButton > button[kind="primary"] { background:var(--green); border-color:var(--green); }
    .milestone { background:linear-gradient(90deg,#fff6df,#e5f2eb); border:1px solid #efd9a0; border-radius:8px; padding:.7rem 1rem; margin:.2rem 0 1rem; font-weight:600; }
    .milestone span { color:var(--muted); font-weight:400; font-size:.85rem; margin-left:.4rem; }
    .trust-pill { display:inline-block; background:#fff6df; color:#7a5a10; border-radius:12px; padding:.15rem .5rem; font-size:.72rem; font-weight:700; }
    .unread-pill { display:inline-block; background:var(--coral); color:white; border-radius:12px; padding:.1rem .5rem; font-size:.72rem; font-weight:700; }
    .path { display:flex; flex-wrap:wrap; gap:.25rem; align-items:center; margin:.2rem 0; font-size:.72rem; }
    .path span { border-radius:10px; padding:.1rem .45rem; background:#eef2ef; color:var(--muted); }
    .path span.done { background:var(--mint); color:var(--green); }
    .path span.now { background:var(--green); color:white; font-weight:700; }
    .path span.no { background:#fde8e2; color:#9b3b22; font-weight:700; }
    .thank-note { background:var(--mint); border-left:4px solid var(--green); border-radius:4px; padding:.7rem 1rem; margin:.4rem 0; font-style:italic; }
    .stTabs [data-baseweb="tab-list"] { display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:.35rem; width:100%; border-bottom:1px solid var(--line); }
    .stTabs [data-baseweb="tab"] { height:3rem; min-width:0; justify-content:center; white-space:nowrap; }
    .stTabs .stTabs [data-baseweb="tab-list"] { display:flex; flex-wrap:wrap; gap:.2rem; }
    .stTabs .stTabs [data-baseweb="tab"] { height:2.4rem; padding:0 .8rem; }
    .sp { display:inline-block; border-radius:12px; padding:.12rem .55rem; font-size:.72rem; font-weight:700; margin-right:.25rem; }
    .sp-applicant { background:#eef2ef; color:#46524e; }
    .sp-demo { background:#e6eefb; color:#2a4f8f; }
    .sp-approved { background:#e5f2eb; color:#166b52; }
    .sp-rejected { background:#fde8e2; color:#9b3b22; }
    .sp-supervised { background:#e5f2eb; color:#166b52; }
    .sp-trusted { background:#fff3d6; color:#7a5a10; }
    .sp-mentor { background:#f1e8fb; color:#5b3a86; }
    .sp-paused { background:#f2f2f2; color:#6b6b6b; }
    .sp-demo-data { background:transparent; color:var(--muted); border:1px dashed var(--line); }
    .filters { background:white; border:1px solid var(--line); border-radius:8px; padding:.4rem .8rem .1rem; margin:.3rem 0 .8rem; }
    .flow li { margin:.15rem 0; }
    @media (max-width:760px) {
        .stTabs [data-baseweb="tab-list"] { display:flex; justify-content:flex-start; gap:.35rem; overflow-x:auto; }
        .stTabs [data-baseweb="tab"] { flex:0 0 auto; padding-left:.8rem; padding-right:.8rem; }
    }
    div[data-testid="stExpander"] { background:white; border:1px solid var(--line); border-radius:7px; }
    </style>
    """,
    unsafe_allow_html=True,
)


def render_library(templates: list[dict], show_steps: bool = False) -> None:
    """Search, filter and list the shared, data-free library. Safe to show without signing in."""
    st.markdown("### Data-free solution library")
    st.markdown('<div class="callout">Only reusable patterns belong here, never nonprofit records. Patterns are shared under <strong>CC BY 4.0</strong>; attribution is required and adaptations may be shared.</div>', unsafe_allow_html=True)
    filters = st.columns([2.2, 1.3, 1.3, 1])
    library_query = filters[0].text_input(
        "Search for a similar past project", value=st.query_params.get("library_search", ""),
        placeholder="e.g. volunteer spreadsheet, attendance, video", key="lib_search",
    )
    missions = filters[1].multiselect("Mission", sorted({template.get("mission_area", "Other") for template in templates}), key="lib_mission")
    skills = filters[2].multiselect("Skills", sorted({skill for template in templates for skill in template.get("skills", [])}),
                                    format_func=badge_label, key="lib_skills")
    sort = filters[3].selectbox("Sort by", ["Best match", "Most reused", "Most hours saved"], key="lib_sort")
    results = search_library(library_query, templates)
    results = [
        (score, template) for score, template in results
        if (not missions or template.get("mission_area") in missions) and (not skills or set(skills) & set(template.get("skills", [])))
    ]
    if sort == "Most reused":
        results.sort(key=lambda item: -int(item[1].get("reuse_count", 0)))
    elif sort == "Most hours saved":
        results.sort(key=lambda item: -int(item[1].get("estimated_build_hours", 0)))
    builder_profiles = load_volunteer_profiles()
    if not results:
        st.info("No matching solutions. A new build can be published here once it's done." if library_query.strip() else "No solutions match these filters.")
    for score, template in paginate(results, "library", page_size=8):
        with st.container(border=True):
            head = st.columns([4, 1])
            demo_label = " <span class='sp sp-demo-data'>Demo data</span>" if template.get("demo_template") else ""
            match = f" · {score}% match" if library_query.strip() else ""
            head[0].markdown(f"**{template['title']}** <span class='status-pill'>{template['mission_area']}</span>{demo_label}{match}", unsafe_allow_html=True)
            reuse_count = int(template.get("reuse_count", 0))
            head[1].markdown(f"<div style='text-align:right'>🔁 reused by <b>{reuse_count}</b></div>", unsafe_allow_html=True)
            st.write(template["solution"])
            st.caption(f"Tools: {', '.join(template['tools'])} · Skills: {', '.join(badge_label(skill) for skill in template['skills'])}")
            if show_steps and template.get("steps"):
                st.markdown("\n".join(f"{number}. {step}" for number, step in enumerate(template["steps"], start=1)))
            builder = builder_profiles.get(template.get("builder_volunteer_id") or "")
            credit = builder_credit(template, builder_profiles)
            if builder and builder.get("show_name_consent", True):
                credit = f"[{credit}](?volunteer={builder['id']})"
                badges = " · ".join(f"{badge_label(skill)} x{count}" for skill, count in sorted(builder.get("badges", {}).items(), key=lambda item: -int(item[1])))
                if badges:
                    credit += f" · badges: {badges}"
            st.markdown(f"<span class='small-muted'>{credit}</span>", unsafe_allow_html=True)
            student_hours_saved = max(0, int(template.get("estimated_build_hours", 1)) - 1)
            st.caption(f"Completed project: {template.get('source_project_title', 'Community project')} · {template['license']} · "
                       f"saves ~{student_hours_saved} volunteer hours vs building new")
            if template.get("handoff_guide"):
                st.download_button("Download reusable handoff guide", template["handoff_guide"], file_name=f"template-guide-{template['id']}.md", mime="text/markdown", key=f"template-guide-{template['id']}")


def render_milestone_banner() -> None:
    """Community milestone computed from data. Totals only; no leaderboards."""
    helped = community_nonprofits_helped()
    message = milestone_message(helped)
    if message:
        st.markdown(f'<div class="milestone">🎉 {message}<span>{helped} and counting · includes demo data</span></div>', unsafe_allow_html=True)


def copy_link_button(link: str) -> None:
    safe_link = json.dumps(link)
    st.iframe(
        f"""<button id="copy" style="font:600 13px 'DM Sans',sans-serif;padding:6px 12px;border:1px solid #dce5df;border-radius:6px;background:white;color:#166b52;cursor:pointer">Copy link</button>
        <script>
        const button = document.getElementById('copy');
        button.onclick = async () => {{
            try {{ await navigator.clipboard.writeText({safe_link}); }}
            catch (error) {{
                const field = document.createElement('textarea'); field.value = {safe_link};
                document.body.appendChild(field); field.select(); document.execCommand('copy'); field.remove();
            }}
            button.innerText = 'Copied!';
            setTimeout(() => button.innerText = 'Copy link', 1500);
        }};
        </script>""",
        height=40,
    )


def render_mail_reply(mail: dict, profile: dict, *, mode: str, token: str) -> None:
    """Reply controls. mode: 'volunteer' (their private page) or 'readonly' (coordinator preview)."""
    if mode == "readonly":
        st.caption("Waiting for the volunteer's reply.")
        return
    key = f"{mode}-{mail['id']}"

    def run(action, message: str | None = None) -> None:
        try:
            result = action()
        except (PermissionError, ValueError) as error:
            st.error(str(error))
            return
        st.session_state.impact_notice = message or result
        st.rerun()

    if mail["type"] in {"invite", "nudge"}:
        cols = st.columns(2)
        yes, no = ("Accept", "Decline") if mail["type"] == "invite" else ("Accept", "Not now")
        if mail["type"] == "invite":
            reply = lambda accepted: respond_to_invitation(token, mail["organization_id"], mail["project_id"], accepted)
        else:
            reply = lambda accepted: respond_to_nudge(token, mail["notification_id"], accepted)
        if cols[0].button(yes, type="primary", key=f"{key}-yes", width="stretch"):
            run(lambda: reply(True))
        if cols[1].button(no, key=f"{key}-no", width="stretch"):
            run(lambda: reply(False))
    elif mail["type"] == "demo":
        st.caption("Open the **My nonprofits** tab to see the demo and submit your answers.")
    elif mail["type"] == "demo_approved":
        st.caption("Open the **My nonprofits** tab to read and accept the agreement.")
    elif mail["type"] == "changes" and mail.get("portal_link"):
        st.markdown(f"[Open the project page to update the work and resubmit]({mail['portal_link']})")


def render_mail(mail: dict, profile: dict, *, mode: str, token: str = "") -> None:
    """One email as the volunteer receives it, with how replying works."""
    how, outcome = REPLY_GUIDE.get(mail["type"], ("No reply needed", ""))
    with st.container(border=True):
        if mail["needs_reply"]:
            badge = "<span class='unread-pill'>Needs a reply</span>"
        elif mail.get("status"):
            badge = f"<span class='status-pill'>{mail['status']}</span>"
        else:
            badge = "<span class='unread-pill'>NEW</span>" if mail.get("read") is False else ""
        st.markdown(f"{MAIL_ICONS.get(mail['type'], '✉️')} **{mail['subject']}** {badge}", unsafe_allow_html=True)
        st.caption(f"{mail['created_at'][:10]}{' · DEMO DATA' if mail.get('demo') else ''} · {mail['summary']}")
        with st.expander("Open email"):
            st.markdown(f"**To:** {profile.get('name', '')} <{profile.get('email') or 'no email on file'}>  \n**Subject:** {mail['subject']}")
            st.text(mail["body"])
            st.caption("Demo: no real email is sent.")
        st.caption(f"**How to reply:** {how}. {outcome}")
        if mail["needs_reply"]:
            render_mail_reply(mail, profile, mode=mode, token=token)


def render_reply_guide() -> None:
    labels = {
        "invite": "Project offer", "nudge": "New matching project (nudge)", "added": "Added to a roster", "demo": "Demo project",
        "demo_approved": "Demo approved", "demo_rejected": "Demo not approved", "welcome": "Welcome (Supervised)",
        "changes": "Changes requested", "star": "Star from a nonprofit", "reuse": "Solution reused", "trusted": "Now Trusted", "mentor": "Now a Mentor",
    }
    rows = "\n".join(f"| {MAIL_ICONS[kind]} {label} | {REPLY_GUIDE[kind][0]} | {REPLY_GUIDE[kind][1]} |" for kind, label in labels.items())
    st.markdown("| Email | How the volunteer replies | What happens |\n|---|---|---|\n" + rows)


def render_skill_proofs(profile: dict) -> None:
    lines = skill_proof_lines(profile)
    if not lines:
        st.caption("No skills listed yet.")
        return
    st.markdown("\n".join(f"- {line['icon']} **{badge_label(line['skill'])}** - {line['label']}" for line in lines))
    st.caption("🏅 Nonprofit-verified (a star on a real project) > ✅ Skill check passed > 📎 Evidence > 📝 Self-listed")


ROSTER_STATUSES = [APPLICANT, DEMO_SENT, DEMO_SUBMITTED, APPROVED, REJECTED, SUPERVISED, TRUSTED]
STATUS_CLASS = {APPLICANT: "applicant", DEMO_SENT: "demo", DEMO_SUBMITTED: "demo", APPROVED: "approved",
                REJECTED: "rejected", SUPERVISED: "supervised", TRUSTED: "trusted"}


def status_pill(status: str) -> str:
    return f"<span class='sp sp-{STATUS_CLASS.get(status, 'applicant')}'>{status}</span>"


def volunteer_pills(student: dict, profile: dict | None = None) -> str:
    profile = profile or {}
    pills = [status_pill(student.get("onboarding_status", APPLICANT))]
    if is_mentor(student):
        pills.append("<span class='sp sp-mentor'>Mentor</span>")
    if profile.get("paused") or student.get("paused"):
        pills.append("<span class='sp sp-paused'>Paused</span>")
    if student.get("demo_student"):
        pills.append("<span class='sp sp-demo-data'>Demo data</span>")
    return "".join(pills)


def paginate(items: list, key: str, page_size: int = 10) -> list:
    """Show one page at a time; the page picker resets whenever the filtered list changes."""
    pages = max(1, (len(items) + page_size - 1) // page_size)
    page = 1
    if pages > 1:
        page = st.radio("Page", list(range(1, pages + 1)), horizontal=True, key=f"{key}-page-{len(items)}")
    start = (page - 1) * page_size
    if items:
        st.caption(f"Showing {start + 1}-{min(start + page_size, len(items))} of {len(items)}")
    return items[start:start + page_size]


AGREEMENT = """TECH BRIDGE CONFIDENTIALITY COMMITMENT (DRAFT)

I will use nonprofit information only for the approved project. I will not copy, publish, disclose, or retain personal, donor, client, or volunteer data beyond what the organization authorizes. I will use sample data for development where possible, follow the organization's access rules, report suspected exposure promptly, and return or delete project data at handoff. Only a separately approved, data-free template may be contributed to the shared library.

This draft is not legal advice or an executed agreement. Have counsel review and execute an agreement appropriate to your program.
"""


def status_path_html(status: str) -> str:
    """Applicant -> Demo sent -> Approved / Rejected -> Supervised -> Trusted, with the current step highlighted."""
    current = STATUS_STEP.get(status, 0)
    parts = []
    for index, step in enumerate(STATUS_PATH):
        label = status if index == current else step
        css = "no" if index == current and status == REJECTED else "now" if index == current else "done" if index < current else ""
        parts.append(f"<span class='{css}'>{label}</span>")
    return "<div class='path'>" + " → ".join(parts) + "</div>"


def render_demo_task(skill: str, *, answers: list[str] | None = None) -> None:
    task = PRACTICE_TASKS[skill]
    st.markdown(f"**{task['title']}** · about {task['minutes']} minutes · fake sample data only")
    st.write(task["instructions"])
    st.code(task["sample"], language=None)
    if answers is not None:
        for number, (question, answer) in enumerate(zip(task["questions"], answers), start=1):
            st.markdown(f"{number}. {question['prompt']}  \n**Answer:** {answer or '(blank)'}")


def render_membership(membership: dict, *, editable: bool, token: str) -> None:
    """One nonprofit this volunteer applied to: status, demo project, feedback, agreement, progress. Private link only."""
    student, status = membership["student"], membership["status"]
    onboarding = student.get("onboarding") or {}
    demo = onboarding.get("demo") or {}
    key = f"{membership['organization_id']}-{student['id']}"
    with st.container(border=True):
        st.markdown(f"**{membership['organization_name']}**{' · Mentor' if is_mentor(student) else ''}")
        st.markdown(status_path_html(status), unsafe_allow_html=True)
        if status == APPLICANT:
            st.caption("Application received. The nonprofit will send you a short demo project.")
        elif status == DEMO_SENT:
            if demo_overdue(demo):
                st.warning("The deadline for this demo project has passed. Ask the nonprofit to send a new one.")
                return
            st.caption(f"Demo project due {demo['deadline'][:10]}. It uses fake sample data only.")
            render_demo_task(demo["skill"])
            if editable:
                with st.form(f"demo-{key}"):
                    answers = [
                        (st.text_area if question["kind"] == "free" else st.text_input)(f"{number}. {question['prompt']}", key=f"demo-{key}-{number}")
                        for number, question in enumerate(PRACTICE_TASKS[demo["skill"]]["questions"], start=1)
                    ]
                    if st.form_submit_button("Submit demo project", type="primary"):
                        submit_demo(token, membership["organization_id"], student["id"], answers)
                        st.session_state.impact_notice = "Demo submitted. A mentor will review it."
                        st.rerun()
        elif status == DEMO_SUBMITTED:
            st.caption(f"Demo submitted {demo.get('submitted_at', '')[:10]}. A mentor is reviewing it.")
        elif status == APPROVED:
            review = onboarding.get("review") or {}
            st.success("Your demo project was approved!" + (f" Feedback: {review['feedback']}" if review.get("feedback") else ""))
            st.markdown("**Before any real task, please read and accept the confidentiality agreement.**")
            st.text(AGREEMENT)
            if editable:
                agreed = st.checkbox("I have read and agree to the confidentiality agreement.", key=f"agree-{key}")
                if st.button("Accept and start", type="primary", disabled=not agreed, key=f"accept-{key}"):
                    accept_confidentiality(token, membership["organization_id"], student["id"])
                    st.session_state.impact_notice = "Welcome aboard! Your first few tasks will be reviewed by a mentor."
                    st.rerun()
        elif status == REJECTED:
            review = onboarding.get("review") or {}
            st.info(f"Thanks for your demo project. Feedback from the mentor: {review.get('feedback', '')}")
            wait = reapply_after(onboarding)
            st.caption(f"You can apply again after {wait.strftime('%B %d, %Y')}." if wait else "You can apply again now through the nonprofit's volunteer form.")
        elif status == SUPERVISED:
            st.progress(min(student.get("reviewed_tasks", 0), TRUSTED_TASKS) / TRUSTED_TASKS, text=progress_text(student))
            st.caption("A mentor reviews your first few real tasks. After 3 reviewed tasks with a star from the nonprofit, you become Trusted.")
        else:
            st.caption("Trusted: mentor review is optional and you can take on bigger or sensitive work here.")


MAIL_GROUPS = {
    "Needs a reply": None,
    "Onboarding": {"added", "demo", "demo_approved", "demo_rejected", "welcome", "trusted", "mentor"},
    "Projects": {"invite", "changes", "nudge"},
    "Recognition": {"star", "reuse"},
}


def render_mailbox(profile: dict, mails: list[dict], unread: int, *, editable: bool, token: str, key: str) -> None:
    waiting = sum(mail["needs_reply"] for mail in mails)
    head = st.columns([3, 1])
    view = head[0].radio("Show", ["All", *MAIL_GROUPS], horizontal=True, key=f"mail-filter-{key}", label_visibility="collapsed",
                         format_func=lambda label: f"{label} ({waiting})" if label == "Needs a reply" else label)
    if editable and unread and head[1].button("Mark all as read", key=f"mark-read-{key}", width="stretch"):
        mark_notifications_read(profile["id"])
        st.rerun()
    if view == "Needs a reply":
        shown = [mail for mail in mails if mail["needs_reply"]]
    elif view in MAIL_GROUPS:
        shown = [mail for mail in mails if mail["type"] in MAIL_GROUPS[view]]
    else:
        shown = mails
    if not shown:
        st.caption("Nothing here." if mails else "No emails yet.")
    for mail in shown:
        render_mail(mail, profile, mode="volunteer" if editable else "readonly", token=token)


def render_memberships(memberships: list[dict], *, editable: bool, token: str) -> None:
    st.caption("Your onboarding with each nonprofit you applied to. Only you can see this.")
    if not memberships:
        st.caption("You haven't joined a nonprofit's roster yet.")
    for membership in memberships:
        render_membership(membership, editable=editable, token=token)


def render_profile_and_impact(profile: dict, impact: dict, *, key: str) -> None:
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("##### Solutions you built")
        if not impact["solutions"]:
            st.caption("None in the shared library yet. When a nonprofit publishes your work, it shows up here.")
        for solution in impact["solutions"]:
            st.markdown(
                f"**{solution['title']}** · reused by {plural(solution['reuse_count'], 'nonprofit')}  \n"
                f"<span class='small-muted'>Has helped {solution['nonprofits_helped']} nonprofits · saves about {solution['staff_hours_saved_per_week']} staff hours every week</span>",
                unsafe_allow_html=True,
            )
        notes = profile.get("thank_you_notes", [])
        if notes:
            st.markdown("##### Thank-you notes")
            for note in reversed(notes):
                st.markdown(f'<div class="thank-note">"{note["note"]}"</div>', unsafe_allow_html=True)
                st.caption(f"From {mission_phrase(note.get('mission_area'))} · {note.get('created_at', '')[:10]}")
    with right:
        st.markdown("##### Skills and proof")
        render_skill_proofs(profile)
        st.markdown("##### Certificate")
        st.download_button(
            "Download certificate", certificate_html(profile, impact),
            file_name=f"tech-bridge-certificate-{profile['id'][:8]}.html", mime="text/html",
            key=f"certificate-{key}", help="Opens in any browser; use Print → Save as PDF for a PDF copy.",
        )
        st.caption("Share on LinkedIn")
        st.code(linkedin_snippet(profile, impact), language=None, wrap_lines=True)


def render_volunteer_settings(profile: dict, *, editable: bool, token: str, key: str) -> None:
    if not editable:
        st.caption(
            f"Causes: {', '.join(profile.get('causes', [])) or 'none chosen'} · {profile.get('hours_per_week', 0)} hrs/week · "
            f"{'Paused' if profile.get('paused') else 'Available'} · credit on solutions: {public_credit_name(profile)}."
        )
        return
    with st.form(f"volunteer-settings-{key}"):
        my_skills = st.multiselect("My skills (self-listed)", SKILLS, default=[skill for skill in profile.get("skills", []) if skill in SKILLS],
                                   help="Self-listed is the first proof level. An approved demo project and stars from nonprofits raise it.")
        causes = st.multiselect("Causes I care about (used in matching)", MISSION_AREAS, default=[cause for cause in profile.get("causes", []) if cause in MISSION_AREAS])
        hours = st.slider("Hours I can give per week", 1, 20, min(20, max(1, int(profile.get("hours_per_week", 4)))))
        paused = st.toggle("Pause - I'm taking a break", value=bool(profile.get("paused")), help="Paused volunteers are never matched, invited, or nudged.")
        consent = st.checkbox("Show my name and badges on solutions I build", value=bool(profile.get("show_name_consent", True)))
        choices = list(DISPLAY_NAME_CHOICES)
        choice = st.radio("Name to show", choices, index=choices.index(profile.get("display_name_choice", "initial")), format_func=DISPLAY_NAME_CHOICES.get, horizontal=True)
        nickname = st.text_input("Nickname (if you chose Nickname)", value=profile.get("nickname", ""), max_chars=40)
        if st.form_submit_button("Save settings", type="primary"):
            update_volunteer_settings(token, {
                "skills": my_skills, "causes": causes, "hours_per_week": hours, "paused": paused, "show_name_consent": consent,
                "display_name_choice": choice, "nickname": nickname,
            })
            st.session_state.impact_notice = "Settings saved."
            st.rerun()


def render_my_impact(profile: dict, *, editable: bool, token: str = "", scope_organization_id: str | None = None,
                     extra_tabs: dict | None = None) -> None:
    """A volunteer's own page: mailbox, onboarding, impact and settings. Never names the nonprofits in shared parts."""
    profile = enrich_profile(profile)
    impact = volunteer_impact(profile, load_shared_library())
    unread = sum(not item["read"] for item in list_notifications(profile["id"]))
    mails = volunteer_mailbox(profile["id"], scope_organization_id)
    waiting = sum(mail["needs_reply"] for mail in mails)
    memberships = [item for item in memberships_for_profile(profile["id"])
                   if not scope_organization_id or item["organization_id"] == scope_organization_id]
    key = f"{profile['id']}-{'scoped' if scope_organization_id else 'own'}"
    demo = " · DEMO DATA" if profile.get("demo") else ""
    where = "Demo view of their private page" if scope_organization_id else "Private link, just for you"
    st.markdown(f'<div class="eyebrow">Tech Bridge · {where}{demo}</div>', unsafe_allow_html=True)
    st.subheader(f"Hi {profile.get('name', 'there').split()[0]}, your work has helped {plural(impact['nonprofits_helped'], 'nonprofit')}")
    if st.session_state.get("impact_notice") and editable:
        st.success(st.session_state.pop("impact_notice"))
    if profile.get("paused"):
        st.info("You're taking a break. You won't be matched, invited, or nudged until you unpause in Settings.")
    metrics = st.columns(4)
    metrics[0].metric("Need a reply", waiting)
    metrics[1].metric("Staff hours saved / week", impact["staff_hours_saved_per_week"])
    metrics[2].metric("Stars", f"⭐ {impact['stars']}")
    metrics[3].metric("Trusted by", plural(sum(item["status"] == TRUSTED for item in memberships), "nonprofit"))
    extra_tabs = extra_tabs or {}
    labels = [f"📬 Mailbox ({waiting})" if waiting else "📬 Mailbox", "🤝 My nonprofits", "🌱 My impact", "⚙️ Settings", *extra_tabs]
    sections = st.tabs(labels)
    with sections[0]:
        render_mailbox(profile, mails, unread, editable=editable, token=token, key=key)
    with sections[1]:
        render_memberships(memberships, editable=editable, token=token)
    with sections[2]:
        render_profile_and_impact(profile, impact, key=key)
    with sections[3]:
        render_volunteer_settings(profile, editable=editable, token=token, key=key)
    for section, render in zip(sections[4:], extra_tabs.values()):
        with section:
            render()


def render_impact_page(token: str) -> None:
    """Password-free private page. An invalid token shows nothing but an error."""
    profile = find_profile_by_impact_token(token)
    if profile is None:
        st.error("This link is invalid or no longer active.")
        return
    render_my_impact(profile, editable=True, token=token)


def render_public_profile(profile_id: str) -> None:
    """Shared volunteer profile: credit and totals only, and only with the volunteer's consent."""
    profile = load_volunteer_profile(profile_id) if profile_id else None
    shared = public_profile(profile, load_shared_library()) if profile else None
    st.markdown('<div class="eyebrow">Tech Bridge · Volunteer profile</div>', unsafe_allow_html=True)
    if shared is None:
        st.info("This volunteer profile isn't public.")
        return
    st.title(shared["display_name"])
    if shared["demo"]:
        st.caption("DEMO DATA")
    cols = st.columns(3)
    cols[0].metric("Nonprofits helped", shared["nonprofits_helped"])
    cols[1].metric("Staff hours saved / week", shared["staff_hours_saved_per_week"])
    cols[2].metric("Stars from nonprofits", shared["stars"])
    if shared["solutions"]:
        st.markdown("#### Solutions built")
        for solution in shared["solutions"]:
            st.markdown(f"- **{solution['title']}** · reused by {plural(solution['reuse_count'], 'nonprofit')}")
    st.markdown("#### Skills")
    render_skill_proofs(enrich_profile(profile))


def render_volunteer_portal(token: str) -> None:
    """Private, password-free page for the volunteer who received this invitation link."""
    st.markdown('<div class="eyebrow">Tech Bridge · Volunteer project</div>', unsafe_allow_html=True)
    located = find_invitation(token)
    if located is None:
        st.error("This invitation link is invalid or no longer active. Check the latest email from Tech Bridge.")
        return
    organization_id, project_id = located
    workspace = load_workspace(organization_id)
    project = next(item for item in workspace["projects"] if item["id"] == project_id)
    invitation = find_invitation_by_token(project, token)
    volunteer = next((item for item in workspace["students"] if item["id"] == invitation["student_id"]), None)
    volunteer_name = volunteer["name"] if volunteer else invitation["student_name"]
    templates = load_shared_library()

    def save() -> None:
        save_workspace(organization_id, workspace["projects"], workspace["students"])

    st.title(f"Hi {volunteer_name.split()[0]}, {project['organization']} needs your help")
    with st.container(border=True):
        st.markdown(f"**Problem:** {project['problem_summary']}")
        st.markdown(f"**Suggested solution:** {project['suggested_solution']}")
        st.caption(f"Skills: {', '.join(project.get('skills', [])) or 'Open to all skills'} · About {project.get('effort_hours', 0)} volunteer hours · {project.get('difficulty', 'Beginner')}")
        if project.get("deliverables"):
            st.markdown("**Deliverables**\n" + "\n".join(f"- {item}" for item in project["deliverables"]))
        st.caption(f"Privacy: {project.get('privacy_notes', '')}")

    if invitation["status"] == "Pending":
        st.markdown("#### Step 1 · Accept or decline")
        reply_cols = st.columns(2)
        if reply_cols[0].button("Accept this project", type="primary", width="stretch", key=f"portal-accept-{project_id}"):
            respond_to_offer(project, True, workspace["students"], workspace["projects"])
            save()
            st.rerun()
        if reply_cols[1].button("Decline", width="stretch", key=f"portal-decline-{project_id}"):
            respond_to_offer(project, False, workspace["students"], workspace["projects"])
            save()
            st.rerun()
        return
    if invitation["status"] != "Accepted" or project.get("assigned_student_id") != invitation["student_id"]:
        st.info("Thanks for letting us know. This project has been passed to another volunteer." if invitation["status"] == "Declined" else "This project is no longer available.")
        return

    if project["status"] in {"Matched", "In progress"}:
        st.success("You accepted this project. It's now in progress.")
        st.markdown("#### Step 2 · Check the library for a similar past project")
        similar = [
            (score, template) for score, template in search_library(f"{project['problem_type']} {project['problem_summary']}", templates, limit=3)
            if score >= 30
        ]
        starting_points = {"Build from scratch": None}
        starting_points.update({f"Customize: {template['title']} ({score}% similar)": template for score, template in similar})
        for score, template in similar:
            with st.expander(f"{template['title']} · {score}% similar"):
                st.write(template["solution"])
                st.markdown("\n".join(f"{number}. {step}" for number, step in enumerate(template.get("steps", []), start=1)))
                if template.get("handoff_guide"):
                    st.download_button("Download handoff guide", template["handoff_guide"], file_name=f"template-guide-{template['id']}.md", mime="text/markdown", key=f"portal-guide-{template['id']}")
        if not similar:
            st.caption("No similar solutions in the library yet, so this will be a new build.")
        st.markdown(f"[Search the full library]({invitation.get('library_link', '')})")
        current = next((label for label, template in starting_points.items() if template and template["id"] == project.get("reuse_template_id")), "Build from scratch")
        chosen_label = st.radio("Starting point", list(starting_points), index=list(starting_points).index(current), key=f"portal-start-{project_id}")
        if chosen_label != current and st.button("Save starting point", key=f"portal-save-start-{project_id}"):
            choose_starting_point(project, starting_points[chosen_label])
            project["status"] = "In progress"
            save()
            st.rerun()
        st.markdown("#### Step 3 · Build or customize, then tell the nonprofit it's done")
        reused = next((template for template in templates if template["id"] == project.get("reuse_template_id")), None)
        st.write(f"Customizing **{reused['title']}**." if reused else "Building a new solution from scratch.")
        st.caption("Use sample data while building and follow the privacy notes above.")
        for change in project.get("change_requests", [])[-1:]:
            st.warning(f"**The nonprofit asked for changes:** {change['comment']}")
        previous = project.get("completion", {})
        with st.form(f"handoff_form-{project_id}"):
            st.markdown("**Hand over your work**")
            links = st.text_area("Links to the work · one per line", value="\n".join(previous.get("links", [])), key=f"portal-links-{project_id}", placeholder="https://docs.google.com/spreadsheets/...\nhttps://drive.google.com/...", height=90)
            summary = st.text_area("What you built", value=previous.get("summary", ""), height=80, key=f"portal-summary-{project_id}")
            how_to_use = st.text_area("How staff use it day to day", value=previous.get("how_to_use", ""), height=100, key=f"portal-how-{project_id}")
            notes = st.text_area("Anything else staff should know (optional)", value=previous.get("notes", ""), height=70, key=f"portal-notes-{project_id}")
            checked = [item for item in HANDOFF_CHECKLIST if st.checkbox(item, value=item in previous.get("checklist", []), key=f"portal-check-{project_id}-{HANDOFF_CHECKLIST.index(item)}")]
            if st.form_submit_button("Email the nonprofit that it's done", type="primary"):
                if not links.strip() or not summary.strip() or not how_to_use.strip():
                    st.error("Add at least one link, what you built, and how staff use it.")
                elif len(checked) < len(HANDOFF_CHECKLIST):
                    st.error("Confirm every item in the handoff checklist before submitting.")
                else:
                    submit_completion(project, links.splitlines(), summary, how_to_use, notes, checked, volunteer_name)
                    subject, body = completion_notice(project, APP_BASE_URL)
                    project["completion"]["notice_delivery"] = send_email(organization_email(organization_id), subject, body)
                    save()
                    st.rerun()
    elif project["status"] == REVIEW_STATUS:
        st.markdown("#### Step 4 · Waiting for the nonprofit to mark it done")
        st.info("The nonprofit was emailed your handoff. They'll mark the project done on the website or ask for changes; you'll get an email if they need changes.")
        for link in project.get("completion", {}).get("links", []):
            st.markdown(f"- {link}")
    elif project["status"] == "Done":
        st.success("The nonprofit confirmed your work is complete. Thank you!")
        own_profile = load_volunteer_profile(volunteer.get("volunteer_profile_id", "")) if volunteer else None
        if own_profile:
            st.markdown(f"[See your impact, badges and stars]({impact_link(own_profile['impact_token'], APP_BASE_URL)})")
        if project.get("handoff_guide"):
            st.download_button("Download the handoff guide", project["handoff_guide"], file_name=f"handoff-{project['id'][:8]}.md", mime="text/markdown", key=f"portal-handoff-{project_id}")
        if project.get("library_template_id"):
            st.caption("The nonprofit added a data-free version of your solution to the shared library, credited to you.")


def app_setting(name: str) -> str:
    """A setting from the environment, or from Streamlit Secrets (.streamlit/secrets.toml locally, the Secrets box when hosted)."""
    value = os.environ.get(name, "")
    if value:
        return value
    try:
        return str(st.secrets.get(name, "") or "")
    except Exception:  # No secrets file configured.
        return ""


@st.cache_resource(show_spinner=False)
def prepare_demo_account(organization_name: str, email: str, password: str) -> str:
    """Once per server start: the demo sign-in from secrets always works, even after a hosted app's storage resets."""
    try:
        ensure_demo_account(organization_name, email, password)
    except ValueError as error:
        return str(error)
    return ""


initialize_tenant_store()
demo_settings = [app_setting(name) for name in ("TECH_BRIDGE_DEMO_ORG", "TECH_BRIDGE_DEMO_EMAIL", "TECH_BRIDGE_DEMO_PASSWORD")]
demo_account_problem = prepare_demo_account(*demo_settings) if all(demo_settings) else ""

if "impact" in st.query_params:
    render_impact_page(st.query_params["impact"])
    st.stop()

def render_application_form(key: str) -> None:
    """A nonprofit's public 'Volunteer with us' form. Submissions go only to that nonprofit's New applications."""
    organization = organization_by_key(key)
    st.markdown('<div class="eyebrow">Tech Bridge · Volunteer application</div>', unsafe_allow_html=True)
    if organization is None:
        st.error("This volunteer form link isn't active.")
        return
    st.title(f"Volunteer with {organization['name']}")
    st.caption("Tell us about you. If it's a fit, we'll send a short demo project (fake sample data only) and a private link. There are no passwords.")
    if st.session_state.get("application_notice"):
        st.success(st.session_state.pop("application_notice"))
        return
    with st.form("application_form"):
        name = st.text_input("Name")
        email = st.text_input("Email")
        phone = st.text_input("Phone (optional)")
        skills = st.multiselect("Skills", SKILLS)
        hours = st.slider("Hours per week", 1, 20, 4)
        causes = st.multiselect("Causes you care about", MISSION_AREAS)
        note = st.text_area("A short note (optional)", max_chars=500)
        show_name = st.checkbox("Show my name and badges on solutions I build", value=True)
        choices = list(DISPLAY_NAME_CHOICES)
        choice = st.radio("Name to show", choices, index=choices.index("initial"), format_func=DISPLAY_NAME_CHOICES.get, horizontal=True)
        nickname = st.text_input("Nickname (if you chose Nickname)", max_chars=40)
        if st.form_submit_button("Send application", type="primary"):
            try:
                submit_application(organization["id"], {
                    "name": name, "email": email, "phone": phone, "skills": skills, "hours_per_week": hours, "causes": causes,
                    "note": note, "show_name_consent": show_name, "display_name_choice": choice, "nickname": nickname,
                })
            except ValueError as error:
                st.error(str(error))
            else:
                st.session_state.application_notice = f"Thanks, {name.split()[0]}! {organization['name']} will review your application."
                st.rerun()


if "apply" in st.query_params:
    render_application_form(st.query_params["apply"])
    st.stop()

if "volunteer" in st.query_params:
    render_public_profile(st.query_params["volunteer"])
    st.stop()

if "invite" in st.query_params:
    render_volunteer_portal(st.query_params["invite"])
    st.stop()

if "tenant_account" not in st.session_state and "library_search" in st.query_params:
    # Public, read-only view for volunteers following an invitation link: shared library only, no workspace data.
    st.markdown('<div class="eyebrow">Tech Bridge · Public solution library</div>', unsafe_allow_html=True)
    st.caption("You're viewing the shared library without signing in. It contains only reviewed, data-free patterns. No nonprofit projects, volunteers, or records are shown here.")
    render_library(load_shared_library(), show_steps=True)
    st.divider()
    if st.button("Nonprofit staff? Sign in to your workspace"):
        del st.query_params["library_search"]
        st.rerun()
    st.stop()

if "tenant_account" not in st.session_state:
    st.markdown('<div class="eyebrow">Tech Bridge · Private nonprofit workspaces</div>', unsafe_allow_html=True)
    st.title("Your nonprofit workspace")
    st.caption("Each nonprofit account has its own projects and volunteer roster. Only approved, data-free solutions are shared in the library.")
    if demo_account_problem:
        st.warning(f"The demo account from the app's secrets couldn't be set up: {demo_account_problem}")
    render_milestone_banner()
    if st.button("Volunteer? Browse the public solution library"):
        st.query_params["library_search"] = ""
        st.rerun()
    account_mode = st.radio("Workspace access", ["Sign in", "Create nonprofit account"], horizontal=True, label_visibility="collapsed")
    if account_mode == "Sign in":
        with st.form("sign_in_form"):
            sign_in_email = st.text_input("Work email", key="sign_in_email")
            sign_in_password = st.text_input("Password", type="password", key="sign_in_password")
            sign_in_submit = st.form_submit_button("Sign in", type="primary", width="stretch")
        if sign_in_submit:
            account = authenticate(sign_in_email, sign_in_password)
            if account is None:
                st.error("We couldn't sign in with those details.")
            else:
                st.session_state.tenant_account = account
                st.rerun()
    else:
        with st.form("create_account_form"):
            organization_name = st.text_input("Nonprofit name", key="register_organization")
            registration_email = st.text_input("Work email", key="register_email")
            registration_password = st.text_input("Password · at least 12 characters", type="password", key="register_password")
            confirm_password = st.text_input("Confirm password", type="password", key="confirm_password")
            create_submit = st.form_submit_button("Create private workspace", type="primary", width="stretch")
        if create_submit:
            if registration_password != confirm_password:
                st.error("The passwords don't match.")
            else:
                try:
                    account = create_account(organization_name, registration_email, registration_password)
                except ValueError as error:
                    st.error(str(error))
                else:
                    st.session_state.tenant_account = account
                    st.rerun()
    st.stop()

tenant_account = st.session_state.tenant_account
tenant_id = tenant_account["organization_id"]
private_data = load_workspace(tenant_id)
state = {
    "projects": private_data["projects"],
    "students": private_data["students"],
    "templates": load_shared_library(),
}
volunteer_profiles = load_volunteer_profiles()


def persist() -> None:
    save_workspace(tenant_id, state["projects"], state["students"])


def student_by_id(student_id: str | None):
    return next((student for student in state["students"] if student["id"] == student_id), None)


def mark_project_done(project: dict, volunteer: dict | None) -> None:
    if not project.get("mentor_approval") and mentor_review_required(volunteer):
        st.error(MENTOR_APPROVAL_REQUIRED)
        return
    guide, _ = generate_handoff(project, volunteer)
    complete_workspace_project(tenant_id, project["id"], guide)
    st.session_state.just_completed_id = project["id"]
    st.session_state.offer_notice = (
        "Marked as done. Next: add a data-free version in the Library tab."
        if not project.get("reuse_template_id") else "Marked as done. The reused library solution's reuse count was updated, and its builder was notified."
    ) + (" Want to say thanks? You can give the volunteer a star on the Matchboard." if volunteer else "")
    st.rerun()


def render_invitation(invitation: dict) -> None:
    recipient = invitation.get("to") or "no email on file · demo inbox only"
    st.markdown(f"**To:** {invitation['student_name']} <{recipient}>  \n**Subject:** {invitation['subject']}")
    st.text(invitation["body"])
    st.caption(f"Delivery: {invitation.get('delivery', 'Demo inbox only')}")
    if invitation.get("portal_link"):
        st.markdown(f"[Open this volunteer's private project page]({invitation['portal_link']})")


def render_offer_reply(project: dict, key_prefix: str) -> None:
    reply_cols = st.columns(2)
    if reply_cols[0].button("Accept", type="primary", key=f"{key_prefix}-accept-{project['id']}", width="stretch"):
        respond_to_offer(project, True, state["students"], state["projects"])
        persist()
        st.rerun()
    if reply_cols[1].button("Decline", key=f"{key_prefix}-decline-{project['id']}", width="stretch"):
        next_invitation = respond_to_offer(project, False, state["students"], state["projects"])
        persist()
        st.session_state.offer_notice = (
            f"Declined. The project card was emailed to {next_invitation['student_name']}, the next best match."
            if next_invitation else "Declined. No other matching volunteers are left; add volunteers or adjust the skills needed."
        )
        st.rerun()


def _suggest_thank_you(project: dict, volunteer: dict | None, key: str) -> None:
    draft, _ = suggest_thank_you_note(project, volunteer)
    st.session_state[key] = draft


def render_thanks(project: dict, volunteer: dict | None) -> None:
    """Positive-only thanks after Done: one optional star, an optional note, and a private concern link."""
    if volunteer is None:
        return
    if project.get("thanks", {}).get("star"):
        st.success(f"⭐ You gave {volunteer['name'].split()[0]} a star. Thank you for recognizing great work!")
    else:
        with st.container(border=True):
            st.markdown("**Say thank you (optional)**")
            note_key = f"thanks-note-{project['id']}"
            st.button("Suggest a note with AI", key=f"suggest-{project['id']}", on_click=_suggest_thank_you, args=(project, volunteer, note_key))
            note = st.text_area("Short thank-you note (optional, edit it however you like)", key=note_key, max_chars=500, height=80)
            st.caption("The volunteer sees your note without your organization's name. Skipping this records nothing.")
            if st.button("⭐ Give a star - great work", type="primary", key=f"star-{project['id']}"):
                give_star(tenant_id, project["id"], note)
                st.session_state.offer_notice = f"Star sent! {volunteer['name'].split()[0]} earned a verified badge for each skill on this project."
                st.rerun()
    with st.popover("Report a concern to the coordinator"):
        st.caption("Private: only the Tech Bridge coordinator sees this. It is never shown to the volunteer or in any public view.")
        concern = st.text_area("What happened?", key=f"concern-{project['id']}")
        if st.button("Send privately", key=f"send-concern-{project['id']}", disabled=not concern.strip()):
            report_concern(tenant_id, project["id"], concern)
            st.session_state.offer_notice = "Your concern was sent privately to the coordinator."
            st.rerun()


def coordinator_mode() -> bool:
    return bool(st.session_state.get("coordinator_mode"))


def render_mentor_review(project: dict, volunteer: dict | None) -> None:
    """Supervised volunteers' tasks need 'Mentor approved' before Done; for Trusted volunteers it's optional."""
    approval = project.get("mentor_approval")
    if approval:
        demo = " · demo" if approval.get("demo") else ""
        st.markdown(f"✅ **Mentor approved** by {approval['approved_by']} ({approval.get('role', 'Mentor')}) · {approval.get('approved_at', '')[:10]}{demo}")
        return
    required = mentor_review_required(volunteer)
    options = {"NGO staff (you)": None}
    for student in state["students"]:
        if is_mentor(student) and (not volunteer or student["id"] != volunteer["id"]):
            options[f"{student['name']} (Mentor)"] = student["id"]
    with st.container(border=True):
        st.markdown("**Mentor review** · " + ("required: this volunteer is Supervised" if required else "optional: this volunteer is Trusted"))
        cols = st.columns([2, 1])
        approver = cols[0].selectbox("Reviewed by", list(options), key=f"approver-{project['id']}", label_visibility="collapsed")
        if cols[1].button("Mentor approved", key=f"mentor-ok-{project['id']}", width="stretch"):
            try:
                approve_as_mentor(tenant_id, project["id"], options[approver])
            except ValueError as error:
                st.error(str(error))
            else:
                st.rerun()


def render_data_mode(project: dict, volunteer: dict | None) -> None:
    """Sample data first; Real data only with a Trusted volunteer who meets the project's rule."""
    mode = project.get("data_mode", "Sample data")
    cols = st.columns([2, 1])
    cols[0].markdown(f"<span class='status-pill'>{mode} mode</span>", unsafe_allow_html=True)
    if mode == "Real data" or project["status"] not in {"In progress", REVIEW_STATUS, "Done"}:
        return
    allowed, reason = real_data_check(project, volunteer)
    if cols[1].button("Switch to real data", key=f"real-data-{project['id']}", disabled=not allowed, help=reason or "The volunteer is Trusted here."):
        switch_to_real_data(tenant_id, project["id"])
        st.rerun()
    if not allowed:
        cols[0].caption(f"Real data locked: {reason}")


def render_assign_anyone(project: dict) -> None:
    """Assign a specific volunteer. Blocked, with the reason, if they don't meet the project's rule."""
    with st.expander("Assign a specific volunteer"):
        candidates: dict[str, str] = {}
        for student in state["students"]:
            label = student["name"]
            while label in candidates:
                label += " (another)"
            candidates[label] = student["id"]
        chosen_label = st.selectbox("Volunteer", list(candidates), key=f"assign-pick-{project['id']}")
        if st.button("Assign", key=f"assign-{project['id']}"):
            volunteer = student_by_id(candidates[chosen_label])
            try:
                invitation = assign_volunteer(project, volunteer, state["students"], state["projects"])
            except AssignmentBlocked as blocked:
                st.error(f"Can't assign {volunteer['name']}: {blocked}")
            else:
                persist()
                st.session_state.offer_notice = f"Project card emailed to {invitation['student_name']}."
                st.rerun()


with st.sidebar:
    st.markdown("### Tech Bridge")
    st.caption(tenant_account["organization_name"])
    st.caption("Private projects and volunteers · shared data-free library")
    st.caption("Solve once. Reuse everywhere.")
    st.divider()
    if os.environ.get("ANTHROPIC_API_KEY"):
        st.success("AI scoping enabled", icon="✨")
        st.caption(f"Model: `{os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-5')}`")
    else:
        st.info("Demo mode · keyword scoping is ready", icon="⚡")
    st.caption("Descriptions may be sent to Anthropic when AI is enabled. Never enter identifying client, donor, volunteer, or health details.")
    st.divider()
    coordinator_passcode = os.environ.get("TECH_BRIDGE_COORDINATOR_PASSCODE", "")
    if coordinator_mode():
        st.success("Coordinator mode on", icon="🛡️")
        if st.button("Leave coordinator mode", width="stretch"):
            st.session_state.pop("coordinator_mode", None)
            st.rerun()
    else:
        with st.expander("Coordinator mode"):
            st.caption("Tech Bridge coordinator tools: skill evidence and reference details, background checks, practice-task entry, and the Alex demo. Nonprofit staff never see reference details.")
            if coordinator_passcode:
                entered = st.text_input("Coordinator passcode", type="password", key="coordinator_passcode")
                if st.button("Unlock", width="stretch"):
                    if secrets.compare_digest(entered.encode(), coordinator_passcode.encode()):
                        st.session_state.coordinator_mode = True
                        st.rerun()
                    st.error("That passcode didn't work.")
            else:
                st.caption("Demo: no passcode set. Set TECH_BRIDGE_COORDINATOR_PASSCODE to require one.")
                if st.button("Switch to coordinator mode (demo)", width="stretch"):
                    st.session_state.coordinator_mode = True
                    st.rerun()
    with st.expander("🎬 Demo scenarios"):
        st.caption("Ready-made examples of each case in your workspace (demo data). Reset demo data restores them.")
        for number, (_, what, who, where) in enumerate(SCENARIOS, start=1):
            st.markdown(f"**{number}. {what}**  \n<span class='small-muted'>{who} · {where}</span>", unsafe_allow_html=True)
    if st.button("Sign out", width="stretch"):
        st.session_state.pop("tenant_account", None)
        st.session_state.pop("coordinator_mode", None)
        st.session_state.pop("pending_scope", None)
        st.session_state.pop("existing_project_id", None)
        st.session_state.pop("library_draft", None)
        st.rerun()
    if st.button("Reset demo data", width="stretch"):
        st.session_state.confirm_reset = True
    if st.session_state.get("confirm_reset"):
        st.warning("This restores this nonprofit's demo projects and volunteer roster. The shared solution library is unchanged.")
        left, right = st.columns(2)
        if left.button("Confirm reset", type="primary", width="stretch"):
            reset_workspace(tenant_id)
            st.session_state.pop("confirm_reset", None)
            st.session_state.pop("pending_scope", None)
            st.session_state.pop("existing_project_id", None)
            st.session_state.pop("library_draft", None)
            st.rerun()
        if right.button("Cancel", width="stretch"):
            st.session_state.pop("confirm_reset", None)


st.title("Solve once. Reuse everywhere.")
st.markdown('<div class="problem-stat">41% of nonprofit leaders cite lack of automation as their top operational challenge. <span class="small-muted">Sage, 2025</span></div>', unsafe_allow_html=True)
st.markdown('<div class="brandline">Turn a nonprofit workflow pain point into a practical project, then carry proven solutions forward.</div>', unsafe_allow_html=True)
render_milestone_banner()

posted_count = len(state["projects"])
open_count = sum(project["status"] == "Open" for project in state["projects"])
reuse_count = len(state["templates"])
top_metrics = st.columns(3)
top_metrics[0].metric("Projects", posted_count)
top_metrics[1].metric("Open needs", open_count)
top_metrics[2].metric("Proven solutions", reuse_count)

if st.session_state.get("offer_notice"):
    st.info(st.session_state.pop("offer_notice"))

tabs = st.tabs(["🧭 Scope a need", "👥 Volunteers", "📋 Matchboard", "📚 Library", "📈 Impact", "🙋 Demo view"], key="main_tab", on_change="rerun")

with tabs[0]:
    st.markdown("### Start with what's broken")
    left, right = st.columns([0.9, 1.1], gap="large")
    with left:
        st.markdown("#### Demo examples")
        example_columns = st.columns(2)
        if example_columns[0].button("A second food pantry", width="stretch"):
            st.session_state["scope_mission"] = "Food"
            st.session_state["scope_comfort"] = "Basic"
            st.session_state["scope_problem"] = "We copy volunteer names from several spreadsheets every week and it takes forever."
            st.rerun()
        if example_columns[1].button("An animal shelter website", width="stretch"):
            st.session_state["scope_mission"] = "Animals"
            st.session_state["scope_comfort"] = "Basic"
            st.session_state["scope_problem"] = "Our shelter website needs a multilingual, accessible intake workflow that our current platform cannot support."
            st.rerun()
        with st.form("scope_form"):
            organization = tenant_account["organization_name"]
            st.text_input("Organization", value=organization, disabled=True, help="Projects are always posted under your signed-in nonprofit.")
            mission = st.selectbox("Mission area", MISSION_AREAS, key="scope_mission")
            comfort = st.selectbox("Staff tech comfort", ["None", "Basic", "Some"], key="scope_comfort")
            problem = st.text_area(
                "What task is getting stuck or repeated?",
                height=150,
                placeholder="Every Friday, we copy volunteer names from three spreadsheets into one list. It takes about 3 hours.",
                key="scope_problem",
            )
            st.caption("Describe what staff do today, how often it happens, and roughly how much time it takes. Leave out names and private records.")
            if st.form_submit_button("Find a simple solution", type="primary", width="stretch"):
                if not organization.strip() or not problem.strip():
                    st.error("Add the organization name and describe the workflow problem.")
                else:
                    duplicate = find_duplicate_project(state["projects"], organization, problem)
                    if duplicate:
                        st.session_state.pending_scope = None
                        st.session_state.existing_project_id = duplicate["id"]
                        st.rerun()
                    else:
                        st.session_state.pop("existing_project_id", None)
                        card, ai_error = scope_problem(organization.strip(), mission, comfort, problem.strip(), state["templates"])
                        st.session_state.pending_scope = {
                            "organization": organization.strip(), "mission": mission,
                            "comfort": comfort, "problem": problem.strip(), "card": card,
                        }
                        st.session_state.scope_ai_error = ai_error
                        st.rerun()
    with right:
        linked_project_id = st.query_params.get("project_id") or st.session_state.get("existing_project_id")
        existing_project = next(
            (project for project in state["projects"] if project["id"] == linked_project_id),
            None,
        )
        if existing_project:
            st.warning("This project already exists.")
            st.markdown(f"[View existing project: {existing_project['organization']} · {existing_project['problem_type']}](?project_id={existing_project['id']})")
            assigned_volunteer = student_by_id(existing_project.get("assigned_student_id"))
            st.markdown(f"**Status:** {existing_project['status']}" + (f" · **Volunteer:** {assigned_volunteer['name']}" if assigned_volunteer else ""))
            st.markdown(f"**Problem:** {existing_project['problem_summary']}")
        pending = st.session_state.get("pending_scope")
        if existing_project:
            pass
        elif not pending:
            st.markdown('<div class="panel"><div class="eyebrow">The workflow</div><h3>Describe → scope → reuse or build</h3><p>AI proposes the smallest maintainable fix and checks the data-free library. A volunteer and the nonprofit review every recommendation before work begins.</p><p class="small-muted">Only sanitized templates can enter the library. Each nonprofit keeps its own data private.</p></div>', unsafe_allow_html=True)
        else:
            card = pending["card"]
            if st.session_state.get("scope_ai_error") is None and os.environ.get("ANTHROPIC_API_KEY"):
                st.caption("Scoped with Claude · review before posting")
            elif os.environ.get("ANTHROPIC_API_KEY"):
                st.warning("AI was unavailable; showing a keyword-based fallback.")
            else:
                st.caption("Keyword-based demo suggestion · review before posting")
            match_id = card.get("matching_template_id")
            match_template = next((item for item in state["templates"] if item["id"] == match_id), None)
            if match_template:
                st.markdown(f'<div class="callout"><strong>Proven solution found, {card.get("library_match_similarity", 0)}% similar:</strong> {match_template["title"]}<br><span class="small-muted">{card.get("reuse_reason", "Adapt a proven, data-free pattern in about an hour.")}</span></div>', unsafe_allow_html=True)
            else:
                st.info("No similar published solution yet. This will be scoped as a new build.")
            with st.form("edit_project_card"):
                st.markdown("#### Review the project card")
                problem_summary = st.text_input("Problem summary", value=card["problem_summary"])
                problem_type = st.text_input("Problem type", value=card["problem_type"])
                hours_wasted = st.number_input("Staff hours lost each week", 0, 168, int(card["hours_wasted_per_week"]))
                solution = st.text_area("Suggested solution · review and edit", value=card["suggested_solution"], height=100)
                st.markdown(f"**Why this fits:** {card['why_this_solution']}")
                advanced = st.text_input("More advanced alternative", value=card.get("advanced_alternative", ""))
                tools = st.text_input("Tools", value=", ".join(card.get("tools", [])))
                skills = st.multiselect("Volunteer skills needed", SKILLS, default=[item for item in card.get("skills", []) if item in SKILLS])
                difficulty = st.selectbox("Difficulty", ["Beginner", "Intermediate", "Advanced"], index=["Beginner", "Intermediate", "Advanced"].index(card.get("difficulty", "Beginner")))
                effort = st.number_input("Volunteer hours to build", 1, 80, int(card["effort_hours"]), help="Reuse projects take about 1 hour. Keep new builds under 25 hours; split anything larger.")
                deliverables = st.text_area("Deliverables · one per line", value="\n".join(card["deliverables"]), height=100)
                privacy_notes = st.text_area("Privacy notes", value=card["privacy_notes"], height=80)
                inferred_sensitivity = project_data_sensitivity({"privacy_notes": card["privacy_notes"], "reuse_template_id": match_id})
                sensitivity = st.selectbox(
                    "Data the volunteer will handle", DATA_SENSITIVITY, index=DATA_SENSITIVITY.index(inferred_sensitivity),
                    help="Sets who can be matched: New volunteers take sample-data reuse projects only; personal data needs a Trusted volunteer with a confidentiality agreement.",
                )
                choices = {"Build a new solution": None}
                choices.update({f"Reuse: {item['title']} · about 1 hour to customize": item["id"] for item in state["templates"]})
                default_choice = next((label for label, value in choices.items() if value == match_id), "Build a new solution")
                reuse_label = st.selectbox("How should this be solved?", list(choices), index=list(choices).index(default_choice))
                if st.form_submit_button("Post project", type="primary", width="stretch"):
                    chosen_template_id = choices[reuse_label]
                    chosen_template = next((item for item in state["templates"] if item["id"] == chosen_template_id), None)
                    if chosen_template:
                        solution = chosen_template["solution"]
                        effort = 1
                        build_effort = int(chosen_template.get("estimated_build_hours", card["effort_hours"]))
                    else:
                        build_effort = int(card["effort_hours"])
                    project_record = {
                        "id": uuid4().hex,
                        "organization": pending["organization"], "mission_area": pending["mission"],
                        "tech_comfort": pending["comfort"], "problem_summary": problem_summary,
                        "problem_type": problem_type, "hours_wasted_per_week": int(hours_wasted),
                        "suggested_solution": solution, "why_this_solution": card["why_this_solution"],
                        "advanced_alternative": advanced, "tools": [part.strip() for part in tools.split(",") if part.strip()],
                        "skills": skills, "difficulty": difficulty, "effort_hours": int(effort),
                        "build_effort_hours": build_effort,
                        "deliverables": [line.strip() for line in deliverables.splitlines() if line.strip()][:5],
                        "privacy_notes": privacy_notes, "reuse_template_id": chosen_template_id,
                        "data_sensitivity": sensitivity,
                        "library_match_similarity": card.get("library_match_similarity", 0),
                        "reuse_reason": card.get("reuse_reason", ""), "library_consent": False,
                        "status": "Open", "assigned_student_id": None, "handoff_guide": "",
                        "created_at": datetime.now().isoformat(),
                        "demo_project": False,
                    }
                    state["projects"].insert(0, project_record)
                    invitation = offer_next_volunteer(project_record, state["students"], state["projects"])
                    persist()
                    nudged = send_project_nudges(tenant_id, project_record, state["students"], state["projects"])
                    st.session_state.pending_scope = None
                    if invitation:
                        st.success(f"Project posted and emailed to {invitation['student_name']}, the top match. Track the reply on the Matchboard.")
                    else:
                        st.success("Project posted. No matching volunteer yet; add volunteers, then send the offer from the Matchboard.")
                    if nudged:
                        st.caption(f"Also nudged {plural(nudged, 'other volunteer')} whose skills and causes fit (max one nudge per volunteer per week; paused volunteers are skipped).")
                    if effort_warning(project_record):
                        st.warning(effort_warning(project_record))

def render_roster_actions(student: dict, column, prefix: str = "roster") -> None:
    """Per-status next step on a volunteer card."""
    status = student.get("onboarding_status", APPLICANT)
    onboarding = student.get("onboarding") or {}
    demo = onboarding.get("demo") or {}
    with column:
        if status == APPLICANT or (status == DEMO_SENT and demo_overdue(demo)):
            if status == DEMO_SENT:
                st.caption(f"Demo expired {demo.get('deadline', '')[:10]}")
            with st.popover("Send demo project" if status == APPLICANT else "Resend demo project", width="stretch"):
                options = [skill for skill in student.get("skills", []) if skill in PRACTICE_TASKS] or list(PRACTICE_TASKS)
                suggested = suggested_demo_skill(student)
                skill = st.selectbox("Demo task (suggested from their skills)", options, index=options.index(suggested) if suggested in options else 0,
                                     key=f"{prefix}-demo-skill-{student['id']}")
                render_demo_task(skill)
                days = st.number_input("Deadline (days)", 1, 30, DEMO_DEADLINE_DAYS, key=f"{prefix}-demo-days-{student['id']}")
                if st.button("Send demo project", type="primary", key=f"{prefix}-send-demo-{student['id']}"):
                    send_demo_project(tenant_id, student["id"], skill, int(days))
                    st.session_state.offer_notice = f"Demo project sent to {student['name']}. It shows up on their private link."
                    st.rerun()
        elif status == DEMO_SENT:
            st.caption(f"Demo due {demo.get('deadline', '')[:10]}")
        elif status == DEMO_SUBMITTED:
            st.caption("Demo submitted: see Volunteers → Demo reviews")
        elif status == APPROVED:
            st.caption("Approved: waiting for them to accept the confidentiality agreement")
        elif status == REJECTED:
            wait = reapply_after(onboarding)
            st.caption(f"Feedback sent. Can reapply after {wait.strftime('%b %d')}" if wait else "Can reapply now")
        elif status == SUPERVISED:
            st.progress(min(student.get("reviewed_tasks", 0), TRUSTED_TASKS) / TRUSTED_TASKS, text=progress_text(student))
        elif is_mentor(student):
            st.markdown("<span class='trust-pill'>Mentor</span>", unsafe_allow_html=True)
        elif st.button("Promote to Mentor", key=f"{prefix}-promote-{student['id']}", width="stretch"):
            promote_to_mentor(tenant_id, student["id"])
            st.rerun()


def render_demo_reviews() -> None:
    """Step 4: a Mentor (NGO staff or a promoted Trusted volunteer) approves or rejects submitted demos."""
    waiting = [student for student in state["students"] if student.get("onboarding_status") == DEMO_SUBMITTED]
    st.caption("A Mentor (NGO staff or a Trusted volunteer you promoted) approves or rejects each demo. The automatic check is only a hint.")
    if not waiting:
        st.caption("No demo projects waiting.")
    reviewers = {"NGO staff (you)": None}
    for student in state["students"]:
        if is_mentor(student):
            reviewers[f"{student['name']} (Mentor)"] = student["id"]
    for student in waiting:
        demo = student["onboarding"]["demo"]
        with st.container(border=True):
            st.markdown(f"**{student['name']}** · {badge_label(demo['skill'])} demo · submitted {demo['submitted_at'][:10]}{' · DEMO DATA' if student.get('demo_student') else ''}")
            with st.expander("Task and answers", expanded=True):
                render_demo_task(demo["skill"], answers=demo.get("answers") or [])
            check = demo.get("auto_check") or {}
            st.caption(f"Automatic check (a hint for the mentor): {'all answers match' if check.get('passed') else check.get('feedback', 'not available')}")
            reviewer_label = st.selectbox("Reviewed by", [label for label, reviewer_id in reviewers.items() if reviewer_id != student["id"]], key=f"reviewer-{student['id']}")
            feedback = st.text_area("Short, kind feedback (required to reject)", key=f"feedback-{student['id']}", max_chars=300)
            cols = st.columns(2)
            if cols[0].button("Approve", type="primary", key=f"approve-demo-{student['id']}", width="stretch"):
                review_demo(tenant_id, student["id"], True, feedback, reviewers[reviewer_label])
                st.session_state.offer_notice = f"{student['name']} is approved. Next, they accept the confidentiality agreement on their private link."
                st.rerun()
            if cols[1].button("Reject", key=f"reject-demo-{student['id']}", width="stretch"):
                try:
                    review_demo(tenant_id, student["id"], False, feedback, reviewers[reviewer_label])
                except ValueError as error:
                    st.error(str(error))
                else:
                    st.session_state.offer_notice = f"Feedback sent to {student['name']}. They can reapply after {REAPPLY_DAYS} days."
                    st.rerun()


def render_roster() -> None:
    filters = st.columns([2, 1.5, 1.5, 1, 1])
    query = filters[0].text_input("Search", placeholder="Name, email or skill", key="roster_search").strip().casefold()
    statuses = filters[1].multiselect("Status", ROSTER_STATUSES, key="roster_status")
    skills = filters[2].multiselect("Skills", SKILLS, format_func=badge_label, key="roster_skills")
    availability = filters[3].selectbox("Availability", ["All", "Available", "Paused"], key="roster_availability")
    sort = filters[4].selectbox("Sort by", ["Status", "Name", "Stars", "Hours"], key="roster_sort")
    people = []
    for student in state["students"]:
        profile = volunteer_profiles.get(student.get("volunteer_profile_id"), {})
        haystack = " ".join([student["name"], student.get("email", ""), *[badge_label(skill) for skill in student.get("skills", [])]]).casefold()
        if query and query not in haystack:
            continue
        if statuses and student.get("onboarding_status") not in statuses:
            continue
        if skills and not set(skills) & set(student.get("skills", [])):
            continue
        if availability != "All" and bool(profile.get("paused")) != (availability == "Paused"):
            continue
        people.append((student, profile))
    order = {status: index for index, status in enumerate(ROSTER_STATUSES)}
    sorters = {
        "Status": lambda item: (order.get(item[0].get("onboarding_status"), 0), item[0]["name"]),
        "Name": lambda item: item[0]["name"],
        "Stars": lambda item: -int(item[1].get("stars", 0)),
        "Hours": lambda item: -int(item[1].get("hours_per_week", item[0].get("hours_per_week", 0)) or 0),
    }
    people.sort(key=sorters[sort])
    if not people:
        st.info("No volunteers match these filters.")
    for student, profile in paginate(people, "roster"):
        with st.container(border=True):
            col1, col2, col3 = st.columns([2.8, 1.5, 1.1])
            col1.markdown(f"**{student['name']}** &nbsp;{volunteer_pills(student, profile)}", unsafe_allow_html=True)
            col1.markdown(status_path_html(student.get("onboarding_status", APPLICANT)), unsafe_allow_html=True)
            col1.caption(format_skill_proofs(student) or "No skills listed")
            col2.caption(f"⭐ {int(profile.get('stars', 0))} · {profile.get('hours_per_week', student.get('hours_per_week', 0))} hrs/wk · "
                         f"{', '.join(profile.get('causes', student.get('causes', []))) or 'no causes chosen'}")
            render_roster_actions(student, col2)
            if profile.get("impact_token"):
                link = impact_link(profile["impact_token"], APP_BASE_URL)
                with col3:
                    copy_link_button(link)
                    st.markdown(f"<span class='small-muted'>[Private link]({link})</span>", unsafe_allow_html=True)


def render_applications(applications: list[dict]) -> None:
    form_link = f"{APP_BASE_URL.rstrip('/')}/?apply={organization_form_key(tenant_id)}"
    with st.container(border=True):
        link_cols = st.columns([3, 1])
        link_cols[0].markdown(f"**Your \"Volunteer with us\" form** · [{form_link}]({form_link})")
        link_cols[0].caption("Share this public link. New applications land here. Try it yourself in the Volunteer view tab.")
        with link_cols[1]:
            copy_link_button(form_link)
    if not applications:
        st.caption("No new applications.")
    for application in applications:
        with st.container(border=True):
            demo = " <span class='sp sp-demo-data'>Demo data</span>" if application.get("demo") else ""
            st.markdown(f"**{application['name']}** {status_pill(APPLICANT)}{demo}", unsafe_allow_html=True)
            st.caption(f"{application['email']}" + (f" · {application['phone']}" if application.get("phone") else "")
                       + f" · {application['hours_per_week']} hrs/week · causes: {', '.join(application['causes']) or 'none chosen'}"
                       + f" · applied {application['created_at'][:10]}")
            if application.get("note"):
                st.markdown(f"> {application['note']}")
            cols = st.columns([3, 1])
            tags = cols[0].multiselect("Skill tags (confirm or edit)", SKILLS, default=application["skills"], key=f"tags-{application['id']}")
            cols[1].markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
            if cols[1].button("Add to roster", type="primary", key=f"add-{application['id']}", disabled=not tags, width="stretch"):
                add_application_to_roster(tenant_id, application["id"], tags)
                st.session_state.offer_notice = f"{application['name']} is on your roster as an Applicant. Next: send a demo project (Volunteers → Roster)."
                st.rerun()


def render_pending_offers(open_offers: list) -> None:
    st.caption("Project cards emailed to volunteers and still waiting for a reply. Record their reply here, or see it from their side in the Volunteer view tab.")
    if not open_offers:
        st.caption("No pending offers.")
    for project, invitation in open_offers:
        with st.container(border=True):
            st.markdown(f"**{project['problem_type']}** → {invitation['student_name']} · sent {invitation.get('sent_at', '')[:10]}")
            with st.expander("View the email"):
                render_invitation(invitation)
            render_offer_reply(project, "inbox")


def render_add_volunteer() -> None:
    with st.form("student_form"):
        st.caption("They start as an Applicant and go through the same demo project and mentor review.")
        cols = st.columns(2)
        name = cols[0].text_input("Name")
        volunteer_email = cols[1].text_input("Email (demo projects and invitations are sent here)")
        student_skills = st.multiselect("Skills", SKILLS)
        cols = st.columns(2)
        student_hours = cols[0].slider("Hours available per week", 1, 10, 4)
        causes = cols[1].multiselect("Causes they care about", MISSION_AREAS)
        bio = st.text_area("Short bio (optional; sent to Anthropic for skill extraction when AI is enabled)", height=80)
        show_name = st.checkbox("Show their name and badges on solutions they build", value=True, help="If off, their solutions say \"Built by a Tech Bridge volunteer\".")
        name_choices = list(DISPLAY_NAME_CHOICES)
        name_choice = st.radio("Name to show", name_choices, index=name_choices.index("initial"), format_func=DISPLAY_NAME_CHOICES.get, horizontal=True)
        nickname = st.text_input("Nickname (if they chose Nickname)", max_chars=40)
        if st.form_submit_button("Add as applicant", type="primary"):
            if not name.strip():
                st.error("Add their name.")
            else:
                inferred, bio_error = extract_bio_skills(bio)
                combined = list(dict.fromkeys(student_skills + inferred))
                new_volunteer = {
                    "id": uuid4().hex, "name": name.strip(), "email": volunteer_email.strip(), "major": "", "year": None,
                    "skills": combined, "hours_per_week": student_hours, "causes": causes, "mode": "Remote", "bio": bio[:300],
                    "confidentiality_signed": False, "demo_student": False,
                    "onboarding": {"status": APPLICANT, "applied_at": datetime.now().astimezone().isoformat(timespec="seconds")},
                }
                profile = ensure_volunteer_profile(new_volunteer, {
                    "show_name_consent": show_name, "display_name_choice": name_choice, "nickname": nickname.strip(),
                })
                new_volunteer["volunteer_profile_id"] = profile["id"]
                state["students"].append(new_volunteer)
                persist()
                if bio_error:
                    st.warning("Could not map the bio with AI; keyword-based skill suggestions were used instead.")
                st.success(f"Added {name} as an Applicant. Send them a demo project from the Roster.")
    st.download_button("Download confidentiality agreement draft", AGREEMENT, file_name="tech-bridge-confidentiality-draft.txt", mime="text/plain")


with tabs[1]:
    st.markdown("### Volunteers")
    st.caption("Your roster is private to your nonprofit. Every volunteer proves themselves before real work: "
               "a demo project with sample data, a mentor's approval, then mentor-reviewed first tasks.")
    applications = list_applications(tenant_id)
    demos_waiting = [student for student in state["students"] if student.get("onboarding_status") == DEMO_SUBMITTED]
    open_offers = [(project, pending_invitation(project)) for project in state["projects"] if pending_invitation(project)]
    status_counts = {status: sum(student.get("onboarding_status") == status for student in state["students"]) for status in ROSTER_STATUSES}
    summary = st.columns(6)
    summary[0].metric("New applications", len(applications))
    summary[1].metric("Demos to review", len(demos_waiting))
    summary[2].metric("In onboarding", status_counts[APPLICANT] + status_counts[DEMO_SENT] + status_counts[APPROVED])
    summary[3].metric("Supervised", status_counts[SUPERVISED])
    summary[4].metric("Trusted", status_counts[TRUSTED])
    summary[5].metric("Mentors", sum(is_mentor(student) for student in state["students"]))
    sections = st.tabs(["Roster", f"Applications ({len(applications)})", f"Demo reviews ({len(demos_waiting)})",
                        f"Project offers ({len(open_offers)})", "Add a volunteer"])
    with sections[0]:
        render_roster()
    with sections[1]:
        render_applications(applications)
    with sections[2]:
        render_demo_reviews()
    with sections[3]:
        render_pending_offers(open_offers)
    with sections[4]:
        render_add_volunteer()

with tabs[2]:
    st.markdown('<span id="matchboard"></span>', unsafe_allow_html=True)
    st.markdown("### Matchboard")
    board_statuses = ["Open", "Offered", "In progress", REVIEW_STATUS, "Done"]

    def needs_action(project: dict) -> bool:
        assigned_student = student_by_id(project.get("assigned_student_id"))
        return (
            (project["status"] == "Open" and not pending_invitation(project))
            or project["status"] == REVIEW_STATUS
            or (project["status"] == "In progress" and not project.get("mentor_approval") and mentor_review_required(assigned_student))
            or (project["status"] == "Done" and assigned_student is not None and not project.get("thanks", {}).get("star"))
        )

    counts = " · ".join(f"{status} **{sum(project['status'] == status for project in state['projects'])}**" for status in board_statuses)
    st.markdown(counts)
    filters = st.columns([2, 2, 1.2, 1])
    board_query = filters[0].text_input("Search", placeholder="Problem, solution or volunteer", key="board_search").strip().casefold()
    board_status = filters[1].multiselect("Status", board_statuses, key="board_status")
    board_work = filters[2].selectbox("Work type", ["All", WORK_SETUP, WORK_NEW_BUILD], key="board_work")
    filters[3].markdown("<div style='height:1.8rem'></div>", unsafe_allow_html=True)
    only_action = filters[3].toggle("Needs my action", key="board_action")
    with st.expander("How matching works"):
        st.caption("Transparent score: skills 60% (weighted by proof: Nonprofit-verified 1.0 · Skill check passed 0.6 · Evidence 0.4 · Self-listed 0.2) · "
                   "availability 20% · cause 10% · advanced-level fit 10%. Only approved volunteers (Supervised or Trusted) are matched; "
                   "personal data needs Trusted. Volunteers who don't meet a project's rule are hidden.")
    board_projects = []
    for project in state["projects"]:
        volunteer_name = (student_by_id(project.get("assigned_student_id")) or {}).get("name", "")
        text = " ".join([project.get("organization", ""), project.get("problem_type", ""), project.get("problem_summary", ""),
                         project.get("suggested_solution", ""), volunteer_name]).casefold()
        if board_query and board_query not in text:
            continue
        if board_status and project["status"] not in board_status:
            continue
        if board_work != "All" and project_work_type(project) != board_work:
            continue
        if only_action and not needs_action(project):
            continue
        board_projects.append(project)
    if not state["projects"]:
        st.info("No projects yet. Scope a need to start the board.")
    elif not board_projects:
        st.info("No projects match these filters.")
    for project in board_projects:
        assigned = student_by_id(project.get("assigned_student_id"))
        demo_label = " · DEMO DATA" if project.get("demo_project") else ""
        flag = "🔔 " if needs_action(project) else ""
        title = f"{flag}{project['problem_type']} · {project['status']}{' · ' + assigned['name'] if assigned else ''}{demo_label}"
        just_completed = project["id"] == st.session_state.get("just_completed_id")
        with st.expander(title, expanded=just_completed or project["status"] in {"Open", "Offered", "Matched", "In progress", REVIEW_STATUS}):
            st.markdown(f"**Problem:** {project['problem_summary']}")
            st.markdown(f"**Solution:** {project['suggested_solution']}")
            st.caption(f"Work type: {project_work_type(project)} · Data: {project_data_sensitivity(project)} · {project.get('effort_hours', 0)} volunteer hours")
            render_data_mode(project, assigned)
            if effort_warning(project):
                st.warning(effort_warning(project))
            interested = [student["name"] for student in state["students"] if student["id"] in project.get("interested_student_ids", [])]
            if interested and not assigned:
                st.caption(f"Said they're interested (from a nudge): {', '.join(interested)}")
            if project.get("reuse_template_id"):
                template = next((item for item in state["templates"] if item["id"] == project["reuse_template_id"]), None)
                if template:
                    student_hours_saved = max(0, int(template.get("estimated_build_hours", project.get("build_effort_hours", 1))) - 1)
                    st.markdown(f"<span class='status-pill'>Reusing · {template['title']}</span> &nbsp; about 1 hour to customize", unsafe_allow_html=True)
                    st.caption(f"Saves ~{student_hours_saved} volunteer hours vs building new.")
            invitation = pending_invitation(project)
            declined_ids = set(project.get("declined_student_ids", []))
            if declined_ids:
                declined_names = [student["name"] for student in state["students"] if student["id"] in declined_ids]
                st.caption(f"Declined by: {', '.join(declined_names)}")
            if assigned:
                st.write(f"Accepted by **{assigned['name']}**")
            elif invitation:
                st.markdown(f"<span class='status-pill'>Emailed · waiting for reply</span> &nbsp; **{invitation['student_name']}** was sent the project card", unsafe_allow_html=True)
                with st.expander("View the email", expanded=False):
                    render_invitation(invitation)
                st.caption("Simulate the volunteer's reply:")
                render_offer_reply(project, "board")
            else:
                all_matches = [
                    match for match in score_students(project, state["students"], state["projects"], limit=None)
                    if match["student"]["id"] not in declined_ids
                ]
                matches = all_matches[:3]
                if not matches:
                    st.info("No eligible volunteers right now. Only approved volunteers (Supervised or Trusted) get real projects, and personal data needs a Trusted volunteer.")
                for match in matches:
                    student = match["student"]
                    match_cols = st.columns([2, 1, 1])
                    match_cols[0].markdown(f"**{student['name']}**" + (f" · {student['major']}" if student.get("major") else ""))
                    match_cols[0].markdown(f"<span class='small-muted'>Why they can take this project: {match['why']}</span>", unsafe_allow_html=True)
                    match_cols[0].caption(match["skill_proofs"] + " · " + match["reason"])
                    match_cols[1].metric("Match", f"{match['score']:.0%}")
                    if match_cols[2].button("Email offer", key=f"offer-{project['id']}-{student['id']}"):
                        try:
                            assign_volunteer(project, student, state["students"], state["projects"])
                        except AssignmentBlocked as blocked:
                            st.error(f"Can't assign {student['name']}: {blocked}")
                        else:
                            persist()
                            st.rerun()
                hidden = len([student for student in state["students"] if not assignment_check(student, project)["ok"]])
                if hidden:
                    st.caption(f"{plural(hidden, 'volunteer')} hidden: they don't meet this project's rule.")
                render_assign_anyone(project)
            if project["status"] in {"Matched", "In progress", REVIEW_STATUS}:
                reused = next((item for item in state["templates"] if item["id"] == project.get("reuse_template_id")), None)
                st.caption(f"Volunteer's starting point: {'customizing ' + reused['title'] if reused else 'building from scratch'}")
            if project["status"] in {"Matched", "In progress"}:
                st.caption("In progress. The volunteer will email you when the work is done.")
                for change in project.get("change_requests", [])[-1:]:
                    st.caption(f"Your last change request: {change['comment']}")
                render_mentor_review(project, assigned)
                blocked = not project.get("mentor_approval") and mentor_review_required(assigned)
                if st.button("Mark as done", key=f"done-{project['id']}", disabled=blocked,
                             help=MENTOR_APPROVAL_REQUIRED if blocked else "Use this if the volunteer told you by email that the work is finished."):
                    mark_project_done(project, assigned)
            if project["status"] == REVIEW_STATUS:
                completion = project.get("completion", {})
                st.markdown(f"<span class='status-pill'>Ready for your review</span> &nbsp; **{completion.get('submitted_by', 'The volunteer')}** handed over the work", unsafe_allow_html=True)
                with st.container(border=True):
                    st.markdown(f"**What was built:** {completion.get('summary', '')}")
                    st.markdown("**Where to find it:**\n" + "\n".join(f"- {link}" for link in completion.get("links", [])))
                    st.markdown(f"**How to use it:** {completion.get('how_to_use', '')}")
                    if completion.get("notes"):
                        st.markdown(f"**Notes:** {completion['notes']}")
                    st.caption("Volunteer confirmed: " + " · ".join(completion.get("checklist", [])))
                render_mentor_review(project, assigned)
                review_cols = st.columns(2)
                blocked = not project.get("mentor_approval") and mentor_review_required(assigned)
                if review_cols[0].button("Mark as done", type="primary", key=f"confirm-{project['id']}", width="stretch",
                                         disabled=blocked, help=MENTOR_APPROVAL_REQUIRED if blocked else None):
                    mark_project_done(project, assigned)
                with review_cols[1].popover("Request changes", width="stretch"):
                    comment = st.text_area("What needs to change?", key=f"changes-{project['id']}")
                    if st.button("Send to volunteer", key=f"send-changes-{project['id']}", disabled=not comment.strip()):
                        request_changes(project, comment)
                        accepted = next((item for item in project.get("invitations", []) if item.get("status") == "Accepted"), {})
                        if accepted:
                            subject, body = changes_requested_notice(project, comment, accepted.get("portal_link", ""))
                            project["change_requests"][-1]["delivery"] = send_email(accepted.get("to", ""), subject, body)
                        persist()
                        st.rerun()
            if project["status"] == "Done":
                render_thanks(project, assigned)
            if project["status"] == "Done" and project.get("handoff_guide"):
                st.download_button("Download handoff guide", project["handoff_guide"], file_name=f"handoff-{project['id'][:8]}.md", mime="text/markdown", key=f"handoff-{project['id']}")
                st.markdown(project["handoff_guide"])
                if not project.get("reuse_template_id") and not project.get("library_template_id"):
                    st.caption("Next: add a data-free version of this work in the Library tab so other nonprofits can reuse it.")

with tabs[3]:
    render_library(state["templates"])
    completed_consented = [
        project for project in state["projects"]
        if project["status"] == "Done"
        and not project.get("reuse_template_id")
        and not project.get("library_template_id")
    ]
    if completed_consented:
        st.markdown("#### Add completed work to the library")
        st.caption("Pick a project you confirmed as complete. AI removes organization and people names, contact details, and project-specific data from the public draft. Review it before publishing.")
        project_by_label = {f"{item['organization']} · {item['problem_type']}": item for item in completed_consented}
        selected_label = st.selectbox("Completed project", list(project_by_label))
        source = project_by_label[selected_label]
        assigned_builder = student_by_id(source.get("assigned_student_id"))
        builder_name = assigned_builder["name"] if assigned_builder else "Tech Bridge volunteer team"
        pending_draft = st.session_state.get("library_draft")
        if not pending_draft or pending_draft.get("project_id") != source["id"]:
            if st.button("Prepare privacy-scrubbed template and guide", type="primary", key=f"prepare-template-{source['id']}"):
                draft, draft_warning = sanitize_library_draft(source, builder_name)
                st.session_state.library_draft = {"project_id": source["id"], "draft": draft}
                st.session_state.library_draft_warning = draft_warning
                st.rerun()
        else:
            if st.session_state.get("library_draft_warning"):
                st.warning("AI sanitization was unavailable; a local redaction draft was prepared. Review every field carefully.")
            elif os.environ.get("ANTHROPIC_API_KEY"):
                st.success("AI prepared a de-identified draft. Review and confirm it before publication.")
            else:
                st.info("No AI key configured; a local redaction draft is ready for review.")
            draft = pending_draft["draft"]
            with st.form("review_library_template"):
                template_title = st.text_input("Generic template title", value=draft["title"])
                generic_summary = st.text_area("Reusable solution", value=draft["summary"], height=90)
                keywords = st.text_input("Search keywords", value=", ".join(draft["keywords"]))
                steps = st.text_area("Reusable steps · one per line", value="\n".join(draft["steps"]), height=100)
                public_guide = st.text_area("Reusable handoff guide", value=draft["handoff_guide"], height=220)
                checked_clean = st.checkbox("I confirm this draft has no nonprofit name, personal name, phone number, email, client/donor/volunteer data, credentials, or confidential details.")
                publish_clicked = st.form_submit_button("Publish under CC BY 4.0", type="primary")
                if publish_clicked and not checked_clean:
                    st.error("Tick the confirmation box above before publishing.")
                elif publish_clicked:
                    reviewed_draft = dict(draft)
                    reviewed_draft.update({
                        "title": template_title,
                        "summary": generic_summary,
                        "keywords": [keyword.strip() for keyword in keywords.split(",") if keyword.strip()],
                        "steps": [step.strip() for step in steps.splitlines() if step.strip()],
                        "handoff_guide": public_guide,
                    })
                    new_template = build_template_from_project(
                        source, reviewed_draft, builder_name,
                        assigned_builder.get("volunteer_profile_id") if assigned_builder else None,
                    )
                    state["templates"], state["projects"] = publish_workspace_solution(
                        tenant_id, source["id"], new_template,
                    )
                    st.session_state.pop("library_draft", None)
                    st.session_state.pop("library_draft_warning", None)
                    st.session_state.offer_notice = "Published. The data-free template and handoff guide are now in the shared library."
                    st.rerun()

with tabs[4]:
    st.markdown("### Impact, made legible")
    organization_name = tenant_account["organization_name"]
    projects = projects_for_organization(state["projects"], organization_name)
    impact = impact_summary(projects, state["templates"])
    if impact["projects_completed"]:
        completed_label = "project" if impact["projects_completed"] == 1 else "projects"
        st.markdown(f"### {organization_name}: {impact['projects_completed']} {completed_label} completed, {impact['staff_hours_saved_per_week']} staff hours saved each week")
    else:
        st.markdown(f"### {organization_name} has no completed projects yet")
    st.caption(f"Showing impact for {organization_name} only.")
    impact_metrics = st.columns(5)
    impact_metrics[0].metric("New volunteer builds", impact["new_builds"])
    impact_metrics[1].metric("Projects completed", impact["projects_completed"])
    impact_metrics[2].metric("Staff hours saved / week", impact["staff_hours_saved_per_week"])
    impact_metrics[3].metric("Volunteer hours saved by reuse", impact["volunteer_hours_saved_by_reuse"])
    impact_metrics[4].metric("Volunteer time value", f"${impact['volunteer_time_value']:,.2f}")
    st.caption(f"Projects posted: {impact['projects_posted']} · matched: {impact['projects_matched']} · completed: {impact['projects_completed']} · volunteer hours contributed: {impact['volunteer_hours_contributed']} · volunteer time valued at ${VOLUNTEER_HOURLY_VALUE:.2f}/hour (Independent Sector, 2026). Impact counts completed projects only.")
    rows = []
    for project in projects:
        assigned = student_by_id(project.get("assigned_student_id"))
        rows.append({
            "Organization": project["organization"], "Need": project["problem_type"],
            "Status": project["status"], "Volunteer": assigned["name"] if assigned else "—",
            "Reuse": "Yes" if project.get("reuse_template_id") else "New build",
            "Record": "Demo data" if project.get("demo_project") else "Community project",
            "Staff hrs saved / week": project["hours_wasted_per_week"] if project["status"] == "Done" else 0,
        })
    table_filters = st.columns([3, 1])
    shown_statuses = table_filters[0].multiselect("Status", sorted({row["Status"] for row in rows}), key="impact_status")
    rows = [row for row in rows if not shown_statuses or row["Status"] in shown_statuses]
    csv = "\n".join([",".join(rows[0].keys())] + [",".join(f'"{value}"' for value in row.values()) for row in rows]) if rows else ""
    table_filters[1].markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
    table_filters[1].download_button("Download CSV", csv, file_name="tech-bridge-impact.csv", mime="text/csv", disabled=not rows, width="stretch")
    st.dataframe(rows, width="stretch", hide_index=True)
    st.caption("AI suggests; a volunteer and nonprofit review before building. Matching uses the published weighted formula. All names and project details shown as demo records are fictional.")
def render_coordinator_skill_tools(chosen: dict) -> None:
    """Coordinator-only: proof records with private reference details, evidence, and background checks."""
    profile = enrich_profile(chosen)
    st.caption("Coordinator only. Reference names, contact details and evidence links never appear in nonprofit or shared views.")
    proofs = [proof for proof in list_skill_proofs(profile["id"], coordinator=True) if proof["level"] >= 2]
    if not proofs:
        st.caption("No evidence, skill checks or stars recorded yet.")
    for proof in proofs:
        private = proof.get("private") or {}
        details = " · ".join(f"{key.replace('_', ' ')}: {value}" for key, value in private.items())
        st.caption(f"{PROOF_ICONS[proof['level']]} {badge_label(proof['skill'])} · {proof['source']} · confirmed by {proof['confirmed_by']} · "
                   f"{proof['created_at'][:10]}{' · demo' if proof['demo'] else ''}" + (f" · 🔒 {details}" if details else ""))
    tool_cols = st.columns(2)
    with tool_cols[0].popover("Add evidence (Level 2)", width="stretch"):
        with st.form(f"evidence-{profile['id']}"):
            skill = st.selectbox("Skill", SKILLS)
            evidence_type = st.radio("Evidence", EVIDENCE_TYPES)
            link = st.text_input("Link you checked (portfolio or certificate verification)")
            reference_name = st.text_input("Reference name (coordinator-only)")
            relationship = st.selectbox("Reference is their", REFERENCE_RELATIONSHIPS)
            contact = st.text_input("Reference contact (coordinator-only)")
            confirmed = st.checkbox("I confirmed this evidence myself")
            if st.form_submit_button("Save evidence", type="primary"):
                if not confirmed:
                    st.error("Confirm the evidence before saving.")
                else:
                    try:
                        add_skill_evidence(profile["id"], skill, evidence_type, {
                            "link": link, "reference_name": reference_name if evidence_type == "Reference" else "",
                            "relationship": relationship if evidence_type == "Reference" else "", "contact": contact if evidence_type == "Reference" else "",
                        })
                    except ValueError as error:
                        st.error(str(error))
                    else:
                        st.rerun()
    cleared = tool_cols[1].toggle("Background check cleared", value=bool(profile.get("background_check_cleared")), key=f"bg-{profile['id']}",
                                  help="Needed for projects with vulnerable people (children, survivors). Coordinator-only.")
    if cleared != bool(profile.get("background_check_cleared")):
        set_background_check(profile["id"], cleared)
        st.rerun()
    concerns = list_concerns(tenant_id)
    st.markdown("##### Concerns reported")
    if not concerns:
        st.caption("None.")
    for concern in concerns:
        project = next((item for item in state["projects"] if item["id"] == concern["project_id"]), {})
        volunteer = volunteer_profiles.get(concern.get("volunteer_id") or "", {})
        st.markdown(f"- {concern['created_at'][:10]} · {project.get('problem_type', 'Project')} · {volunteer.get('name', 'volunteer')}: {concern['note']}")


def flow_steps(student: dict) -> list[tuple[str, str, str]]:
    """The whole onboarding-to-Trusted flow for one volunteer: (step, who and where, state: done / now / todo / stopped)."""
    status = student.get("onboarding_status", APPLICANT)
    own_projects = [project for project in state["projects"] if project.get("assigned_student_id") == student["id"]]
    accepted = any(invitation.get("student_id") == student["id"] and invitation.get("status") == "Accepted"
                   for project in state["projects"] for invitation in project.get("invitations", []))
    handed_over = any(project.get("completion") or project.get("status") == "Done" for project in own_projects)
    stage = {APPLICANT: 2, DEMO_SENT: 3, DEMO_SUBMITTED: 4, APPROVED: 5, REJECTED: 4}.get(status, 6)
    if status == SUPERVISED:
        stage = 6 + int(accepted) + int(accepted and handed_over) + int(student.get("reviewed_tasks", 0) >= 1 and accepted and handed_over)
    elif status == TRUSTED:
        stage = 11 if is_mentor(student) else 10
    steps = [
        ("Apply", "Volunteer · \"Try it: apply\" above"),
        ("Add to roster", "You · Volunteers → Applications"),
        ("Send a demo project", "You · Volunteers → Roster card"),
        ("Submit the demo", "Volunteer · My nonprofits tab"),
        ("Review the demo", "Mentor · Volunteers → Demo reviews"),
        ("Accept the agreement", "Volunteer · My nonprofits tab"),
        ("Accept a project offer", "You · Matchboard → Volunteer · Mailbox tab"),
        ("Hand over the work", "Volunteer · Project page tab"),
        ("Mentor approved → Done → Star", "Mentor and you · Matchboard"),
        (f"Trusted after {TRUSTED_TASKS} reviewed, starred tasks", "Automatic"),
        ("Promote to Mentor (optional)", "You · Volunteers → Roster card"),
    ]
    result = []
    for index, (step, where) in enumerate(steps):
        if status == REJECTED and index == 4:
            result.append((step, f"not approved · can reapply after {REAPPLY_DAYS} days", "stopped"))
        elif status == REJECTED and index > 4:
            result.append((step, where, "todo"))
        else:
            result.append((step, where, "done" if index < stage else "now" if index == stage else "todo"))
    return result


def render_flow_card(student: dict, profile: dict) -> None:
    icons = {"done": "✅", "now": "👉", "todo": "⬜", "stopped": "❌"}
    with st.container(border=True):
        st.markdown(f"**{student['name']}** &nbsp;{volunteer_pills(student, profile)}", unsafe_allow_html=True)
        st.caption(f"{student.get('email') or 'no email on file'} · {progress_text(student) if student.get('onboarding_status') == SUPERVISED else 'onboarding with your nonprofit'}")
        st.markdown("**Your next step with them**")
        render_roster_actions(student, st.container(), prefix="flow")
        st.markdown("**The whole flow**")
        st.markdown("\n".join(
            f"{number}. {icons[state_]} {'**' + step + '**' if state_ == 'now' else step}  \n<span class='small-muted'>{where}</span>"
            for number, (step, where, state_) in enumerate(flow_steps(student), start=1)
        ), unsafe_allow_html=True)
        link = impact_link(profile["impact_token"], APP_BASE_URL)
        copy_link_button(link)
        st.markdown(f"<span class='small-muted'>[Their private link]({link})</span>", unsafe_allow_html=True)
    with st.expander("How each email reply works"):
        render_reply_guide()


def render_project_pages(student: dict) -> None:
    offers = [
        (project, invitation) for project in state["projects"] for invitation in project.get("invitations", [])
        if invitation.get("student_id") == student["id"] and invitation.get("status") == "Accepted"
    ]
    if not offers:
        st.caption("Once they accept a project offer, the page where they build and hand over the work appears here.")
        return
    titles = {f"{project['problem_type']} · {project['status']}": invitation for project, invitation in offers}
    picked = st.selectbox("Project", list(titles), key="volunteer_view_project")
    with st.container(border=True):
        render_volunteer_portal(titles[picked]["token"])


with tabs[5]:
    st.markdown("### Volunteer view")
    st.caption("See the app exactly as a volunteer does and play both sides of the whole flow. Demo only: in real use only the volunteer sees "
               "their page, on their private link. Here it shows only what involves your nonprofit.")
    with st.expander("➕ Try it: apply as a new volunteer (your public \"Volunteer with us\" form)"):
        render_application_form(organization_form_key(tenant_id))
        st.caption("Then add them in Volunteers → Applications, and pick them below.")
    candidates = [student for student in state["students"] if student.get("volunteer_profile_id") in volunteer_profiles]
    picker = st.columns([1.2, 1.4, 2.4])
    view_status = picker[0].selectbox("Status", ["All", *ROSTER_STATUSES], key="volunteer_view_status")
    view_query = picker[1].text_input("Search", placeholder="Name or email", key="volunteer_view_search").strip().casefold()
    candidates = [
        student for student in candidates
        if (view_status == "All" or student.get("onboarding_status") == view_status)
        and (not view_query or view_query in f"{student['name']} {student.get('email', '')}".casefold())
    ]
    named: dict[str, dict] = {}
    for student in candidates:
        label = f"{student['name']} · {student.get('onboarding_status', APPLICANT)}"
        while label in named:
            label += " (another)"
        named[label] = student
    if not named:
        picker[2].selectbox("See the app as", ["No volunteers match"], disabled=True, key="volunteer_view_empty")
        st.info("No volunteers match. Change the filters, or add someone through \"Try it: apply\" above.")
    else:
        newest = next((label for label, student in reversed(list(named.items())) if not student.get("demo_student")), None)
        default = newest or next((label for label, student in named.items() if student["name"] == "Jordan Ellis"), next(iter(named)))
        chosen_label = picker[2].selectbox("See the app as", list(named), index=list(named).index(default), key="volunteer_view_pick")
        student = named[chosen_label]
        profile = volunteer_profiles[student["volunteer_profile_id"]]
        left, right = st.columns([1, 2.4], gap="large")
        with left:
            render_flow_card(student, profile)
            if not coordinator_mode():
                st.caption("🛡️ Turn on Coordinator mode in the sidebar for evidence, references and background checks.")
        with right:
            extra = {"🧰 Project page": lambda: render_project_pages(student)}
            if coordinator_mode():
                extra["🛡️ Coordinator tools"] = lambda: render_coordinator_skill_tools(profile)
            render_my_impact(profile, editable=True, token=profile["impact_token"], scope_organization_id=tenant_id, extra_tabs=extra)
