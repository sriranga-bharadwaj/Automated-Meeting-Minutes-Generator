"""Convert the dict from app.minutes_generator.generate_minutes into the
`Minutes` shape the React frontend expects (frontend/src/types.ts)."""
import re
from datetime import date, timedelta
from typing import Optional
from uuid import uuid4

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _new_id() -> str:
    return uuid4().hex[:8]


def base_date(value: Optional[str]) -> date:
    """Date part of the meeting's datetime string, or today if it can't be read."""
    m = re.match(r"\s*(\d{4})-(\d{2})-(\d{2})", value or "")
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return date.today()


def resolve_due(deadline: Optional[str], base: date) -> str:
    """'yyyy-mm-dd' when the deadline can be resolved with confidence, else ''."""
    if not deadline:
        return ""
    text = deadline.strip().lower()
    iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if iso:
        return iso.group(1)
    if text.startswith("after "):
        return ""                                    # "after the review": no date
    if re.search(r"\bnext\s+(" + "|".join(WEEKDAYS) + r")\b", text):
        return ""                                    # "next Friday" is ambiguous
    if "tomorrow" in text:
        return (base + timedelta(days=1)).isoformat()
    if re.search(r"\b(today|tonight|end of (the )?day|eod)\b", text):
        return base.isoformat()
    for name, index in WEEKDAYS.items():
        if re.search(rf"\b{name}\b", text):
            ahead = (index - base.weekday()) % 7 or 7   # next occurrence after the meeting
            return (base + timedelta(days=ahead)).isoformat()
    return ""


def canonical_owner(owner: Optional[str], attendee_names: list[str]) -> str:
    """Attendee's full name when the owner matches one, 'Unassigned' when empty."""
    if not owner or not owner.strip():
        return "Unassigned"
    cleaned = owner.strip()
    low = cleaned.lower()
    for name in attendee_names:
        if name.lower() == low:
            return name
    for name in attendee_names:
        parts = name.lower().split()
        if parts and parts[0] == low:
            return name
    return cleaned


def _action(task, owner, deadline, base, names) -> dict:
    due = resolve_due(deadline, base)
    task = (task or "").strip()
    if deadline and not due and deadline.strip().lower() not in task.lower():
        task = f"{task} ({deadline.strip()})"        # keep the wording the date field can't hold
    return {
        "id": _new_id(),
        "task": task,
        "owner": canonical_owner(owner, names),
        "due": due,
        "status": "Open",
    }


def to_ui_minutes(result: dict, meta: dict, version: int = 1) -> dict:
    base = base_date(meta.get("datetime"))
    attendees = [a for a in meta.get("attendees", []) if a.get("name")]
    names = [a["name"] for a in attendees]
    title = (meta.get("title") or result.get("title") or "Meeting minutes").strip()

    if result.get("engine") == "llm":
        topics = []
        if result.get("summary"):
            topics.append({"id": _new_id(), "title": "Overview", "summary": result["summary"]})
        topics += [
            {"id": _new_id(), "title": t.get("title", ""), "summary": t.get("summary", "")}
            for t in result.get("topics", [])
        ]
        decisions = [
            {"id": _new_id(), "statement": d["decision"]}
            for d in result.get("decision_details", []) if d.get("decision")
        ]
        actions = [
            _action(a.get("task"), a.get("owner"), a.get("deadline"), base, names)
            for a in result.get("action_item_details", []) if a.get("task")
        ]
    else:  # keyword fallback: plain strings only
        discussion = " ".join(result.get("key_discussions", []))
        topics = [{"id": _new_id(), "title": "Discussion", "summary": discussion}] if discussion else []
        decisions = [{"id": _new_id(), "statement": s} for s in result.get("decisions", [])]
        actions = [_action(s, None, None, base, names) for s in result.get("action_items", [])]

    # No "confidence" fields on purpose: the module doesn't compute one.
    return {
        "version": version,
        "title": title,
        "datetime": meta.get("datetime", ""),
        "agenda": meta.get("agenda", ""),
        "attendees": attendees,
        "topics": topics,
        "decisions": decisions,
        "actionItems": actions,
    }