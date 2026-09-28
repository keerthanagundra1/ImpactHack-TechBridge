# Tech Bridge

Tech Bridge turns nonprofit workflow problems into small volunteer projects, checks for an existing data-free solution pattern, and helps carry finished work forward.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

The shared library starts with four published data-free starter patterns. Each account has a private nonprofit workspace; registering a fictional seed nonprofit loads only that nonprofit's demo project and a private fictional volunteer roster. New nonprofits start with an empty project list. Seeded records are labeled as demo data. The account database is stored in `data/tech_bridge_tenants.sqlite3`; **Reset demo data** restores only the signed-in workspace and leaves the shared library untouched.

## Using the app

Signed-in nonprofits have six tabs. Each list has filters so it stays manageable as the roster and project list grow.

| Tab | What it's for | Filters |
|---|---|---|
| 🧭 Scope a need | Describe a problem, review the AI project card, and post it | — |
| 👥 Volunteers | Summary numbers, plus sub-tabs for **Roster**, **Applications**, **Demo reviews**, **Project offers** and **Add a volunteer** | Roster: search, status, skills, availability, sort; paginated |
| 📋 Matchboard | Every project with matches, offers, Mentor review, Done and thanks. 🔔 marks projects that need you | Search, status, work type, **Needs my action** |
| 📚 Library | The shared, data-free solutions, and publishing your completed work | Search, mission, skills, sort; paginated |
| 📈 Impact | Your nonprofit's results | Table status filter and **Download CSV** |
| 🙋 Volunteer view | See the app as any volunteer and play the whole flow (see [Volunteer mailbox](#volunteer-mailbox)) | Status, search |

## Demo scenarios

Every workspace with the seeded demo roster also gets eight ready-made scenarios (labeled demo data), so a demo can start anywhere in the flow. They're listed in the sidebar under **🎬 Demo scenarios**, and **Reset demo data** restores them. They're defined in `demo_scenarios.py`.

| # | Scenario | Who | Where to look | Try |
|---|---|---|---|---|
| 1 | Demo not approved: feedback sent, can reapply in 30 days | Tyler Robinson | Volunteers → Roster; Volunteer view → Mailbox | Read the feedback email and see the reapply date |
| 2 | Demo deadline passed | Mia Thompson | Volunteers → Roster | **Resend demo project** |
| 3 | Demo approved, waiting for the confidentiality agreement | Harper Davis | Volunteer view → My nonprofits | Accept the agreement; she becomes Supervised |
| 4 | Project offer waiting for a reply | Zara Hussain | Matchboard; Volunteers → Project offers; Volunteer view → Mailbox | Accept or decline the offer |
| 5 | Supervised work waiting for Mentor approval | Hannah Okafor | Matchboard (🔔 Needs my action) | **Mentor approved**, then **Mark as done** |
| 6 | Changes requested, resubmitted, ready for review | Daniel Okoye | Matchboard; Volunteer view → Mailbox | Review the handoff, then approve or request changes again |
| 7 | Done, waiting for a star, one star from Trusted (2 of 3) | Caleb Brooks | Matchboard | **Give a star**; he becomes Trusted and gets the "You're now Trusted" email |
| 8 | Personal-data project | Donor tracker | Matchboard (Open) | Only Trusted volunteers appear in its matches |

These add to the stages already seeded: Taylor's application, Jordan with a demo sent, Alex with a demo submitted, Noah at 1 of 3, the Trusted volunteers, and Amina as a Mentor.

## Accounts and data isolation

- Nonprofits create an account with a unique organization name, email, and password. Passwords are salted and hashed with PBKDF2; they are not stored as plaintext.
- Projects and volunteer profiles are stored in organization-keyed workspaces. Login loads only that account's workspace. The only cross-organization application data is the reviewed, data-free solution library.
- Reset affects only the signed-in nonprofit's workspace. It does not reset the shared library or another nonprofit's data.
- This is prototype authentication, not production identity management: email ownership is not verified, there is no password recovery or MFA, SQLite data is not encrypted at rest, and deployment needs HTTPS. Use fictional/demo data until this is replaced with managed identity, verified organization membership, and production storage controls.
- The old `data/tech_bridge_data.json` is retained as a local legacy archive; authenticated app flows do not load its projects or volunteers. Its solution templates initialize the shared library when the tenant database is first created.
- Set `TECH_BRIDGE_DATABASE` to choose a different SQLite file path. Keep that file private and excluded from source control.

## Volunteer workflow

1. The nonprofit posts a reviewed project card. It is automatically emailed to the best-scoring volunteer who has confirmed confidentiality (status **Offered**).
2. The email contains the card, a link to the solution library pre-filtered for the problem type (`?library_search=`), and a **private volunteer link** (`?invite=<token>`). Volunteers don't need an account; the unguessable token only opens that one invitation.
3. On the private page the volunteer accepts or declines. A decline emails the next best match; if nobody is left, the project returns to **Open**. (Nonprofit staff can also record the reply from the Volunteer inbox or Matchboard.)
4. Accepting moves the project straight to **In progress**. The volunteer reviews similar library solutions and picks a starting point (build from scratch or customize a match).
5. When the work is done, the volunteer submits a handoff on their private page: links to the work, what was built, how staff use it, optional notes, and a checklist (ownership transferred, personal access removed, only sample data used, staff can open every link). Submitting emails the nonprofit's account address that the work is done, and the project shows **Ready for review**.
6. The nonprofit reviews the handoff on the Matchboard and either clicks **Mark as done** (status **Done**; a handoff guide is generated from the volunteer's notes and links, and the project counts toward Impact) or **requests changes** (back to **In progress**; the volunteer is emailed and sees the comment on their page). If the volunteer tells the nonprofit by email instead, the nonprofit can also click **Mark as done** while the project is In progress.
7. The nonprofit adds completed new builds to the shared library from the Library tab: AI prepares a privacy-scrubbed draft, the nonprofit reviews it and publishes it under CC BY 4.0, credited to the volunteer. Volunteers never publish to the library directly.

Signed-out visitors with a `library_search` link see a public, read-only view of the shared library only (search, steps, handoff guides). Nonprofit projects and volunteer rosters stay behind the login.

## Volunteer retention

Volunteers never log in. Each volunteer has one global profile (keyed by email, shared across every nonprofit roster they're on) with a **private impact link** (`?impact=<token>`). The nonprofit copies it from the roster in the Volunteers tab (**Copy link**). An invalid token shows only an error. The logic lives in `volunteer_retention.py`; storage is the `volunteer_profiles`, `notifications`, and `concerns` tables in the tenant database.

- **My impact** (`?impact=`): "Your work has helped N nonprofits", unread count, notifications with an **Email preview** (no email is sent), solutions built with reuse counts, staff hours saved per week, stars, badges, thank-you notes, trust level, a downloadable HTML certificate (print to PDF) and a LinkedIn snippet. Volunteers edit their causes, hours per week, **Pause - I'm taking a break**, name-credit consent, and display name here.
- **Reuse notification**: when a reuse of a library solution is marked Done, the original builder is notified: "Your {solution} just helped {mission type}. It has now helped {n} nonprofits and saves them about {h} staff hours every week."
- **Thanks (positive only)**: after Done, the nonprofit can give one optional **star** with an optional thank-you note (AI can draft it). A star adds +1 star and one "verified by a nonprofit" badge per project skill. No star records nothing. **Report a concern to the coordinator** is private to the coordinator.
- **Onboarding status** is per nonprofit: Applicant → Demo sent → Approved / Rejected → Supervised → Trusted. See [Volunteer onboarding](#volunteer-onboarding). Paused volunteers are never matched, invited, or nudged.
- **Nudges**: posting a project nudges other unpaused volunteers whose skills and causes fit ("A new project matching your skills just came in. Interested?"). They answer Accept / Not now on their private link. There is at most one nudge per volunteer per week.
- **Credit**: library cards say "Built by {display name}" (full name, first name + last initial, or nickname) with the builder's badges, linking to a public profile (`?volunteer=<id>`). With consent off it says "Built by a Tech Bridge volunteer". The home page shows a community milestone banner (10, 25, 50, 100, 250...). There are no leaderboards.
- **Privacy**: shared views (library, public profiles, notifications, email previews, certificates) show work, credit, and totals only. They never show which nonprofit a volunteer worked for or which nonprofit gave a star; nonprofits appear only by mission type ("an animal shelter"). Thank-you notes are scrubbed of the nonprofit's name and contact details.
- **Coordinator tools** (coordinator mode only) appear as an extra tab in the Volunteer view: skill evidence and references, background checks, and concerns.
- **Demo data** (all labeled): Priya S. (Trusted, 6 stars, built the Volunteer Sign-up Sheet reused by 4 nonprofits, 3 notifications, 1 thank-you note), Jordan Ellis (New, pending nudge), Jacob Miller (paused), Grace Kim (name credit off), Amina Yusuf (Mentor).

## Volunteer onboarding

Each nonprofit onboards its own volunteers on its private roster. Every volunteer proves themselves before touching real work: they complete a demo project with sample data, a mentor approves them, and their first few real tasks are reviewed until they have a strong track record. The logic is in `onboarding.py`; applications are stored in the `applications` table, and each volunteer's status lives on that nonprofit's roster entry.

| Step | Who | What happens | Status |
|---|---|---|---|
| 1. Apply | Volunteer | Fills in the nonprofit's public **Volunteer with us** form (`?apply=<nonprofit key>`; the link is under Volunteers → Applications): name, email, phone, skills, hours per week, causes and a short note. It lands in that nonprofit's **New applications** only. | Applicant |
| 2. Add | NGO | Confirms or edits the skill tags and clicks **Add to roster**. | Applicant |
| 3. Demo project | NGO | **Send demo project**: the app suggests a short task from the volunteer's skills (one per skill, fake data only) with a deadline, 7 days by default. The volunteer submits it on their private link. | Demo sent → Demo submitted |
| 4. Mentor review | Mentor | **Volunteers → Demo reviews**: **Approve**, or **Reject** with short, kind feedback that the volunteer sees. A rejected volunteer can reapply after 30 days. The automatic check is only a hint for the mentor. | Approved / Rejected |
| 5. Confidentiality | Volunteer | Accepts the confidentiality agreement on their private link before any real task. | Supervised |
| 6. Supervised tasks | Mentor | Every task needs **Mentor approved** before the nonprofit can mark it Done. The card shows "2 of 3 reviewed tasks completed". | Supervised |
| 7. Trusted | Automatic | After 3 mentor-approved tasks, each with a star from the nonprofit, the volunteer becomes Trusted at that nonprofit. Mentor review becomes optional, they can take personal-data work, and the nonprofit can **Promote to Mentor**. | Trusted |

**Who is a Mentor?** NGO staff (the signed-in nonprofit), or a Trusted volunteer the nonprofit promotes. Mentors review demo projects and Supervised volunteers' work.

**Assignment gate** (enforced in matching, nudges, invitations and **Assign a specific volunteer**, which shows the reason when it blocks):

| Project | Who can take it |
|---|---|
| Normal work (Setup of a proven fix, or a new build without sensitive data) | Supervised or Trusted, with a signed confidentiality agreement, listing at least half of the skills |
| Personal data (donors, clients) | Trusted |
| Vulnerable people (children, survivors) | Trusted + background check cleared by the coordinator |

Projects start in **Sample data** mode; the nonprofit can switch to **Real data** only with a Trusted volunteer. Only the nonprofit can give a star.

**Skill proof labels.** Each skill shows its strongest proof: 🏅 Nonprofit-verified xN (only from stars) > ✅ Skill check passed (an approved demo project) > 📎 Evidence (portfolio, reference or certificate, confirmed by the coordinator) > 📝 Self-listed. Labels are shown on matches and profiles, and they weight the skill part of the match score (1.0 / 0.6 / 0.4 / 0.2), but they don't decide who can be assigned. Reference names, contact details and evidence links are coordinator-only.

**Coordinator mode.** The sidebar switch adds a **Coordinator tools** tab to the Volunteer view: evidence and reference details, background checks, and concerns. If `TECH_BRIDGE_COORDINATOR_PASSCODE` is set, turning it on needs the passcode. If it isn't set, it is a labeled demo toggle; set a passcode before anyone else uses the app.

**Demo data** (all labeled):
- An application from Taylor Nguyen in New applications.
- Jordan Ellis at Demo sent, and Alex Rivera with a demo submitted and waiting for review.
- Noah Patel Supervised (1 of 3 reviewed tasks).
- Priya, Marcus and Lucas Trusted; Amina Yusuf Trusted and a Mentor.
- The other seeded volunteers are Supervised.
- Volunteers who were already on a roster before this change were migrated as Supervised.

## Volunteer mailbox

Every email a volunteer would get is collected in one mailbox, newest first. Each email shows a **Needs a reply** or status badge, the full email, and how replying works. No real email is sent in the demo. The logic is in `volunteer_mailbox.py`.

- **Volunteer's private link:** their whole mailbox, with real replies. Offers and nudges are answered with Accept / Decline or Accept / Not now; the demo and the confidentiality agreement are answered in **Your nonprofits** on the same page.
- **Volunteer view tab:** for demos, the nonprofit plays both sides in one place. The flow card on the left shows the checklist of the whole flow (apply → add → demo → mentor review → agreement → project offer → hand over the work → Mentor approved, done, star → Trusted → Mentor) and your next action, such as **Send demo project**. On the right is the volunteer's real page, in tabs: Mailbox, My nonprofits (demo form, agreement), My impact, Settings and Project page. **Try it: apply** opens the public form. It shows only what involves your nonprofit; in real use only the volunteer sees their page.

| Email | How the volunteer replies | What happens |
|---|---|---|
| Added to a roster | No reply needed | The nonprofit sends a demo project next |
| Demo project | Submit it on the private link | Before the deadline it goes to Volunteers → Demo reviews; after the deadline it expires and the nonprofit can resend it |
| Demo approved | Accept the confidentiality agreement | They become Supervised and can be matched; until then they aren't |
| Demo not approved | No reply needed | They read the feedback and can reapply after 30 days |
| Welcome (Supervised) | No reply needed | Offers can arrive; each task needs Mentor approval |
| Project offer | Accept or Decline | Accept: In progress, and the project page opens. Decline: next best match, or back to Open |
| New matching project (nudge) | Accept or Not now | Accept: they get the offer if it's still open, otherwise they're marked interested. At most one nudge a week |
| Changes requested | Update the work and resubmit on the project page | Back to Ready for review |
| Star, solution reused, now Trusted, now a Mentor | No reply needed | Their private page updates |

Onboarding and notification emails never name a nonprofit. Project offers and change requests come from the nonprofit that sent them. A nonprofit's demo view shows only the email it sent that volunteer, plus labeled demo data.

### Email setup

Invitations are sent over SMTP when these environment variables are set; otherwise they stay in the in-app Volunteer inbox. Demo addresses (`@example.org`) are never emailed.

| Variable | Purpose |
|---|---|
| `SMTP_HOST` | SMTP server, e.g. `smtp.gmail.com` or `smtp.sendgrid.net` |
| `SMTP_PORT` | Defaults to `587` (STARTTLS) |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | SMTP login (for Gmail, an app password) |
| `SMTP_FROM` | Sender address; defaults to `SMTP_USERNAME` |
| `TECH_BRIDGE_BASE_URL` | Public app URL used in email links; defaults to `http://localhost:8501` |

Each invitation records its delivery status (Emailed, Demo inbox only, or Email failed), shown on the Matchboard.

## AI setup

The app runs without credentials using its keyword fallback. To enable Claude scoping, bio skill extraction, and handoff drafting, set `ANTHROPIC_API_KEY` in the environment. `ANTHROPIC_MODEL` is optional and defaults to `claude-sonnet-5` (verify availability for your Anthropic account before deployment).

If AI is enabled, a submitted problem description and the relevant project details are sent to Anthropic. Do not enter identifying client, donor, volunteer, health, or other sensitive information. Local SQLite storage is a hackathon prototype, not a production data-protection system.

## Privacy and reuse

- Volunteers confirm that they have signed the confidentiality agreement before being added to a nonprofit workspace. The downloadable agreement is a draft, not legal advice or an executed contract.
- Projects stay private unless the nonprofit chooses to publish a reviewed, data-free pattern under CC BY 4.0 after confirming the work is complete.
- AI prepares a de-identified template and reusable handoff guide; the nonprofit must review and confirm the draft before publishing. Organization identity and records are not copied into the library.
- Reuse cards display volunteer attribution, nonprofit reuse count, and estimated volunteer hours saved versus a new build. The dashboard reports the featured one-build-to-many-nonprofits story, weekly staff hours saved, and volunteer hours saved by reuse.
- Legacy local demo fixtures migrate to the current demo story while non-demo projects, volunteers, and templates are preserved.
- AI suggestions and matches are reviewed by the nonprofit and volunteer before work begins. Matching scores are calculated by code using the displayed weights.

## Tests

```powershell
python -m pytest -v
```

## Streamlit Community Cloud

Deploy this repository with `app.py` as the entry point and add `ANTHROPIC_API_KEY` (and optionally `ANTHROPIC_MODEL`) in the app's Secrets settings. SQLite on Streamlit Community Cloud may reset when the hosted app restarts; use persistent managed storage and a verified identity provider before real nonprofits rely on it.