from datetime import date

from app.minutes_adapter import base_date, canonical_owner, resolve_due, to_ui_minutes

SUNDAY = date(2026, 11, 1)

LLM_RESULT = {
    "engine": "llm",
    "title": "Model title",
    "summary": "The team planned the demo.",
    "participants": ["Ravi"],
    "topics": [{"title": "Editor", "summary": "Needs work", "start_time": 14.0}],
    "decision_details": [{"decision": "Use a pre-recorded demo", "context": "Safer"}],
    "action_item_details": [
        {"task": "Finish the editor", "owner": "Ravi", "deadline": "Wednesday"},
        {"task": "Fix the refund bug", "owner": None, "deadline": "after the review"},
    ],
}
META = {
    "title": "Sprint sync",
    "datetime": "2026-11-01T10:00",
    "agenda": "Demo plan",
    "attendees": [{"name": "Ravi Kumar", "email": "ravi@example.com"}],
}


def test_weekday_resolves_to_the_next_occurrence():
    assert resolve_due("Wednesday", SUNDAY) == "2026-11-04"
    assert resolve_due("by Friday", SUNDAY) == "2026-11-06"


def test_same_weekday_means_next_week():
    assert resolve_due("Sunday", SUNDAY) == "2026-11-08"


def test_relative_days():
    assert resolve_due("tomorrow", SUNDAY) == "2026-11-02"
    assert resolve_due("end of the day tomorrow", SUNDAY) == "2026-11-02"
    assert resolve_due("today", SUNDAY) == "2026-11-01"


def test_event_and_ambiguous_deadlines_stay_unresolved():
    for text in ["before the review", "after the review on Thursday", "next Friday", "next week", "", None]:
        assert resolve_due(text, SUNDAY) == ""


def test_iso_date_passes_through():
    assert resolve_due("2026-12-01", SUNDAY) == "2026-12-01"


def test_base_date_from_datetime_local_string():
    assert base_date("2026-11-01T10:30") == date(2026, 11, 1)
    assert isinstance(base_date(""), date)
    assert isinstance(base_date("garbage"), date)


def test_canonical_owner():
    names = ["Ravi Kumar", "Priya"]
    assert canonical_owner("ravi", names) == "Ravi Kumar"
    assert canonical_owner("Priya", names) == "Priya"
    assert canonical_owner("Meera", names) == "Meera"
    assert canonical_owner(None, names) == "Unassigned"
    assert canonical_owner("  ", names) == "Unassigned"


def test_llm_result_is_converted():
    ui = to_ui_minutes(LLM_RESULT, META)
    assert ui["title"] == "Sprint sync"                  # the user's own title wins
    assert ui["version"] == 1
    assert ui["topics"][0]["title"] == "Overview"
    assert ui["topics"][0]["summary"] == "The team planned the demo."
    assert ui["topics"][1]["title"] == "Editor"
    assert ui["decisions"][0]["statement"] == "Use a pre-recorded demo"
    first, second = ui["actionItems"]
    assert first["owner"] == "Ravi Kumar"
    assert first["due"] == "2026-11-04"
    assert first["status"] == "Open"
    assert second["owner"] == "Unassigned"
    assert second["due"] == ""
    assert second["task"] == "Fix the refund bug (after the review)"


def test_no_invented_confidence():
    ui = to_ui_minutes(LLM_RESULT, META)
    assert all("confidence" not in item for item in ui["decisions"] + ui["actionItems"])


def test_every_item_has_a_unique_id():
    ui = to_ui_minutes(LLM_RESULT, META)
    items = ui["topics"] + ui["decisions"] + ui["actionItems"]
    assert all(item["id"] for item in items)
    assert len({item["id"] for item in items}) == len(items)


def test_keyword_fallback_result_is_converted():
    basic = {
        "engine": "basic", "summary": "x",
        "key_discussions": ["We met.", "Ravi will finish it."],
        "decisions": ["We decided to ship."],
        "action_items": ["Ravi will finish it."],
        "transcript": "x",
    }
    ui = to_ui_minutes(basic, META)
    assert ui["topics"][0]["title"] == "Discussion"
    assert ui["decisions"][0]["statement"] == "We decided to ship."
    assert ui["actionItems"][0]["owner"] == "Unassigned"
    assert ui["actionItems"][0]["due"] == ""