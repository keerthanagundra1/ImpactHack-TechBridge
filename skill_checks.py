"""Practice tasks (skill checks): one short task per skill, fake sample data only.

Answers are graded with simple rules (expected answers). AI is used only for short free-text
answers, and only when ANTHROPIC_API_KEY is set; otherwise a keyword rule grades them too.
A result is "pass" or "not yet" plus one line of friendly feedback. Nothing negative is shown publicly.
"""

from __future__ import annotations

import os
import re
from typing import Any

RETRY_HOURS = 24


def _q(prompt: str, kind: str, accept: list[str] | float, hint: str, keywords: list[str] | None = None) -> dict[str, Any]:
    return {"prompt": prompt, "kind": kind, "accept": accept, "hint": hint, "keywords": keywords or []}


PRACTICE_TASKS: dict[str, dict[str, Any]] = {
    "Google Sheets/Excel": {
        "title": "Clean a volunteer sign-up list",
        "minutes": 10,
        "instructions": "Remove duplicates from this volunteer list and count sign-ups per week. A duplicate is a row where every column matches another row.",
        "sample": "Name,Email,Week\nAna Diaz,ana@example.org,1\nBen Cole,ben@example.org,1\nAna Diaz,ana@example.org,1\nCai Wong,cai@example.org,2\nDee Park,dee@example.org,2\nBen Cole,ben@example.org,2\nEli Ford,eli@example.org,2\nCai Wong,cai@example.org,2\nFay Ruiz,fay@example.org,3",
        "questions": [
            _q("How many rows are left after removing duplicate rows?", "number", 7, "Two rows are exact copies of another row."),
            _q("How many sign-ups are there in week 2 after removing duplicates?", "number", 4, "Count week-2 rows once each; Cai appears twice in week 2."),
        ],
    },
    "Apps Script": {
        "title": "Read a small Apps Script function",
        "minutes": 10,
        "instructions": "Read the function and answer without running it.",
        "sample": "function countYes(rows) {\n  let n = 0;\n  for (const row of rows) {\n    if (row[2] === 'Yes') n++;\n  }\n  return n;\n}\ncountYes([['Ana','w1','Yes'], ['Ben','w1','No'], ['Cai','w2','Yes'], ['Dee','w2','yes']]);",
        "questions": [
            _q("What number does countYes return for the sample?", "number", 2, "=== is case-sensitive, so 'yes' is not 'Yes'."),
            _q("Which string method would make 'yes' count too? (just the method name)", "text", ["tolowercase", "touppercase"], "Normalize the case of row[2] before comparing."),
        ],
    },
    "Airtable/No-code": {
        "title": "Set up a shift table",
        "minutes": 10,
        "instructions": "A pantry is building a Shifts table in Airtable with fake data.",
        "sample": "Shifts: Shift date · Volunteer name · Role · Confirmed?",
        "questions": [
            _q("Which field type should 'Shift date' use?", "text", ["date"], "Pick the type that lets you sort and filter by day."),
            _q("To show only upcoming shifts in a view, what do you add to the view?", "text", ["filter"], "Views can hide rows that don't match a condition."),
        ],
    },
    "Zapier/Make automation": {
        "title": "Plan a thank-you automation",
        "minutes": 10,
        "instructions": "Send a thank-you email draft whenever a row is added to a fake Donations sheet (Name, Email, Amount).",
        "sample": "Donations sheet columns: Name · Email · Amount",
        "questions": [
            _q("What trigger event starts the automation? (a few words)", "text", ["new row", "row added", "new spreadsheet row"], "It starts when the sheet gets a new entry."),
            _q("Which step between the trigger and the email skips test rows where Amount is 0?", "text", ["filter", "condition", "path", "router"], "Automations can stop unless a condition is true."),
        ],
    },
    "Python": {
        "title": "Predict the output",
        "minutes": 10,
        "instructions": "Read the code and answer without running it.",
        "sample": "signups = ['ana', 'ben', 'ana', 'cai', 'ben', 'ana']\nprint(len(set(signups)))\nprint(signups.count('ana'))",
        "questions": [
            _q("What does the first print show?", "number", 3, "set() keeps one copy of each name."),
            _q("What does the second print show?", "number", 3, "count() counts every occurrence."),
        ],
    },
    "SQL/Databases": {
        "title": "Read a grouped query",
        "minutes": 10,
        "instructions": "Table volunteers(name, city, hours) holds fake rows: (Ana, Dallas, 3), (Ben, Plano, 4), (Cai, Dallas, 5), (Dee, Irving, 7), (Eli, Plano, 6).",
        "sample": "SELECT city, SUM(hours) FROM volunteers\nGROUP BY city ORDER BY SUM(hours) DESC LIMIT 1;",
        "questions": [
            _q("Which city does the query return?", "text", ["plano"], "Add up the hours for each city first."),
            _q("What is SUM(hours) for Dallas?", "number", 8, "Dallas has two rows."),
        ],
    },
    "Power BI/Tableau": {
        "title": "Plan a small attendance dashboard",
        "minutes": 12,
        "instructions": "Fake monthly attendance for a tutoring program.",
        "sample": "Month,Attendance\nJan,42\nFeb,38\nMar,50\nApr,45",
        "questions": [
            _q("What is total attendance for January-March?", "number", 130, "Add Jan, Feb and Mar only."),
            _q("Which chart type best shows attendance over the months? (one word)", "text", ["line"], "Trends over time usually use one continuous mark."),
        ],
    },
    "Data analysis": {
        "title": "Summarize volunteer hours",
        "minutes": 10,
        "instructions": "Fake weekly hours for five volunteers.",
        "sample": "2, 4, 4, 5, 10",
        "questions": [
            _q("What is the median?", "number", 4, "Sort the values and take the middle one."),
            _q("Which value is the outlier?", "number", 10, "One value is far from the rest."),
        ],
    },
    "Web design (HTML/CSS)": {
        "title": "Accessible page basics",
        "minutes": 10,
        "instructions": "An adoption page needs to work with screen readers.",
        "sample": "<img src=\"luna.jpg\">\n<a href=\"/adopt\">Adopt</a> <a href=\"/foster\">Foster</a>",
        "questions": [
            _q("Which attribute gives the image a text alternative?", "text", ["alt"], "It's a three-letter attribute on <img>."),
            _q("Which HTML element should wrap the main navigation links?", "text", ["nav"], "There's a semantic element named for navigation."),
        ],
    },
    "WordPress/Squarespace/Wix": {
        "title": "Site settings for staff",
        "minutes": 10,
        "instructions": "Staff at a fake nonprofit need to keep a WordPress site current.",
        "sample": "Admin menu: Posts · Pages · Appearance > Menus · Plugins · Users",
        "questions": [
            _q("Where do you change the site's main menu links?", "text", ["menus", "menu", "navigation", "appearance"], "Look under Appearance."),
            _q("Which WordPress role lets staff edit all pages but not install plugins?", "text", ["editor"], "It's between Author and Administrator."),
        ],
    },
    "JavaScript/React": {
        "title": "Predict the output",
        "minutes": 10,
        "instructions": "Read the code and answer without running it.",
        "sample": "const hours = [2, 3, 5];\nconsole.log(hours.reduce((a, b) => a + b, 0));\nconsole.log([1, 2, 3].map(x => x * 2).filter(x => x > 2).length);",
        "questions": [
            _q("What does the first console.log print?", "number", 10, "reduce adds each value to the running total."),
            _q("What does the second console.log print?", "number", 2, "Double each value first, then keep those above 2."),
        ],
    },
    "UX design": {
        "title": "Fix a long sign-up form",
        "minutes": 15,
        "instructions": "A pantry's (fake) volunteer sign-up form has 14 fields and many people quit halfway.",
        "sample": "Fields include: name, email, phone, address, birthday, emergency contact, T-shirt size, 3 availability grids, skills, how you heard about us, photo release, comments.",
        "questions": [
            _q("In 2-3 sentences: what would you change first, and why?", "free", [], "Think about which fields are truly needed on day one.",
               ["fewer", "remove", "shorter", "short", "required", "optional", "later", "split", "steps", "test", "drop", "cut", "essential"]),
        ],
    },
    "Canva/Graphics": {
        "title": "Flyer pre-print check",
        "minutes": 10,
        "instructions": "A (fake) animal shelter's adoption-event flyer is about to be printed.",
        "sample": "Flyer: event title, date, time, address, 3 pet photos, QR code, logo.",
        "questions": [
            _q("List three things you'd check before it's printed.", "free", [], "Think about readability, accuracy and print settings.",
               ["contrast", "readable", "font", "size", "date", "time", "address", "location", "spelling", "typo", "qr", "logo", "bleed", "resolution", "photo", "consent"]),
        ],
    },
    "Mobile apps": {
        "title": "Check-in app with weak Wi-Fi",
        "minutes": 10,
        "instructions": "A (fake) food distribution check-in app is used where Wi-Fi drops out.",
        "sample": "Volunteers scan a QR code per household; the scan must never be lost.",
        "questions": [
            _q("What approach keeps check-ins when there's no connection? (a few words)", "text", ["offline", "sync", "local storage", "cache", "queue"], "Store on the phone first, upload later."),
        ],
    },
    "CRM setup (e.g., HubSpot/Salesforce Nonprofit)": {
        "title": "Model donors in a CRM",
        "minutes": 10,
        "instructions": "Set up a (fake) donor list in a nonprofit CRM.",
        "sample": "Fake data: Ana Diaz gave $25 in May and $40 in June.",
        "questions": [
            _q("What record type stores Ana herself?", "text", ["contact", "person", "constituent"], "It's the record for a person."),
            _q("What record type stores each gift?", "text", ["donation", "gift", "opportunity"], "Each gift is its own record linked to the person."),
        ],
    },
}


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9. ]", "", (value or "").casefold()).strip()


def _number(value: str) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", value or "")
    return float(match.group()) if match else None


def _keyword_grade(answer: str, keywords: list[str]) -> bool:
    words = _normalize(answer)
    hits = sum(1 for keyword in keywords if keyword in words)
    return len(words.split()) >= 8 and hits >= 2


def _ai_grade(question: dict[str, Any], answer: str) -> tuple[bool, str] | None:
    """AI grading for a short free-text answer: pass / not yet + one friendly line. None if unavailable."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        from tech_bridge import _anthropic_text, _extract_json

        prompt = (
            "You grade a short practice answer from a student volunteer. Be encouraging and fair. "
            'Return ONLY JSON: {"pass": true|false, "feedback": "<one friendly sentence under 25 words>"}. '
            f"Task: {question['prompt']}\nGood answers usually mention: {', '.join(question['keywords'])}.\nAnswer: {answer[:800]}"
        )
        result = _extract_json(_anthropic_text(prompt, max_tokens=150))
        return bool(result.get("pass")), str(result.get("feedback", ""))[:200]
    except Exception:
        return None


def grade_practice_task(skill: str, answers: list[str]) -> dict[str, Any]:
    """Grade one practice task. Returns {"passed": bool, "feedback": str}."""
    task = PRACTICE_TASKS.get(skill)
    if task is None:
        return {"passed": False, "feedback": "There's no practice task for this skill yet."}
    answers = list(answers) + [""] * (len(task["questions"]) - len(answers))
    for number, (question, answer) in enumerate(zip(task["questions"], answers), start=1):
        if question["kind"] == "number":
            value = _number(answer)
            correct = value is not None and abs(value - float(question["accept"])) < 1e-6
        elif question["kind"] == "text":
            normalized = _normalize(answer)
            correct = bool(normalized) and any(accepted in normalized for accepted in question["accept"])
        else:
            ai = _ai_grade(question, answer)
            if ai is not None:
                if not ai[0]:
                    return {"passed": False, "feedback": ai[1] or f"Not yet. Hint: {question['hint']}"}
                continue
            correct = _keyword_grade(answer, question["keywords"])
        if not correct:
            return {"passed": False, "feedback": f"Not yet - question {number} needs another look. Hint: {question['hint']}"}
    return {"passed": True, "feedback": "Nice work - every answer checks out. This skill is now \"Skill check passed\"."}


def expected_answers(skill: str) -> list[str]:
    """Answers that pass the rule-based grader (used by the coordinator demo)."""
    answers = []
    for question in PRACTICE_TASKS[skill]["questions"]:
        if question["kind"] == "number":
            answers.append(str(int(question["accept"])) if float(question["accept"]).is_integer() else str(question["accept"]))
        elif question["kind"] == "text":
            answers.append(question["accept"][0])
        else:
            answers.append(" ".join(["I would make it", *question["keywords"][:4], "so it is quick and clear for everyone"]))
    return answers

