import pytest

from app import minutes_generator as mg
from minutes import ActionItem, Decision, MeetingMinutes, Topic

TRANSCRIPT = "Ravi will finish the editor by Wednesday. We decided to use a pre-recorded demo."


def test_empty_transcript_is_rejected():
    with pytest.raises(ValueError):
        mg.generate_minutes("   ")


def test_basic_engine_keeps_the_original_keys(monkeypatch):
    monkeypatch.setenv("MINUTES_ENGINE", "basic")
    result = mg.generate_minutes(TRANSCRIPT)
    assert result["engine"] == "basic"
    for key in ("summary", "key_discussions", "decisions", "action_items", "transcript"):
        assert key in result


def test_falls_back_to_basic_when_the_llm_fails(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("ollama is down")

    monkeypatch.delenv("MINUTES_ENGINE", raising=False)
    monkeypatch.setattr(mg, "_llm_minutes", boom)
    result = mg.generate_minutes(TRANSCRIPT)
    assert result["engine"] == "basic"
    assert result["action_items"]


def test_llm_result_keeps_old_keys_and_adds_new_ones(monkeypatch):
    fake = MeetingMinutes(
        title="Demo plan",
        summary="The team planned the demo.",
        participants=["Ravi"],
        topics=[Topic(title="Editor", summary="Needs work", start_time=14.0)],
        decisions=[Decision(decision="Use a pre-recorded demo", context="Safer")],
        action_items=[ActionItem(task="Finish the editor", owner="Ravi", deadline="Wednesday")],
    )
    monkeypatch.delenv("MINUTES_ENGINE", raising=False)
    monkeypatch.setattr("minutes.generate_minutes", lambda text, **kw: fake)

    result = mg.generate_minutes(TRANSCRIPT)

    assert result["engine"] == "llm"
    assert result["title"] == "Demo plan"
    assert result["decisions"] == ["Use a pre-recorded demo"]            # old shape
    assert "Ravi" in result["action_items"][0]
    assert "Wednesday" in result["action_items"][0]
    assert result["action_item_details"][0]["owner"] == "Ravi"            # new data
    assert result["topics"][0]["start_time"] == 14.0
    assert "transcript" in result and "summary" in result and "key_discussions" in result


def test_segments_reach_the_llm_with_timestamps(monkeypatch):
    seen = {}

    def fake(text, **kwargs):
        seen["text"] = text
        return MeetingMinutes(title="t", summary="s")

    monkeypatch.delenv("MINUTES_ENGINE", raising=False)
    monkeypatch.setattr("minutes.generate_minutes", fake)
    mg.generate_minutes("plain text", segments=[{"start": 14.0, "end": 19.0, "text": "Hello"}])
    assert seen["text"] == "[00:00:14] Hello"