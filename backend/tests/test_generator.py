import json
from pathlib import Path

import ollama
import pytest

from minutes import generate_minutes

SAMPLES = Path(__file__).parent / "sample_transcripts"


def ollama_available() -> bool:
    try:
        ollama.list()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not ollama_available(), reason="Ollama is not running"
)


@pytest.fixture(scope="module", params=["meeting_1", "meeting_2"])
def case(request):
    """Runs the (slow) model once per sample; all tests below share it."""
    name = request.param
    transcript = (SAMPLES / f"{name}.txt").read_text()
    expected = json.loads((SAMPLES / f"{name}.expected.json").read_text())
    return generate_minutes(transcript), expected


def test_participants(case):
    result, expected = case
    assert set(result.participants) == set(expected["participants"])


def test_exactly_the_expected_decisions(case):
    result, expected = case
    assert len(result.decisions) == len(expected["decisions"])
    keyword = expected.get("decision_must_mention")
    if keyword:
        assert keyword.lower() in result.decisions[0].decision.lower()


def test_action_item_count(case):
    result, expected = case
    assert len(result.action_items) == len(expected["action_items"])


def test_owners_and_deadlines(case):
    result, expected = case
    for exp in expected["action_items"]:
        matches = [a for a in result.action_items if a.owner == exp["owner"]]
        assert matches, f"no action item with owner {exp['owner']!r}"
        if exp["deadline"] is None:
            assert any(a.deadline is None for a in matches), (
                f"owner {exp['owner']!r} should have no deadline"
            )
        else:
            assert any(
                a.deadline and exp["deadline"].lower() in a.deadline.lower()
                for a in matches
            ), f"owner {exp['owner']!r} should have deadline containing {exp['deadline']!r}"


def test_topic_start_times_are_real_timestamps(case):
    result, _ = case
    transcript_seconds = {
        h * 3600 + m * 60 + s
        for h, m, s in __import__("re").findall(
            r"\[(\d+):(\d{2}):(\d{2})\]",
            (SAMPLES / "meeting_1.txt").read_text()
            + (SAMPLES / "meeting_2.txt").read_text(),
        )
        for h, m, s in [(int(h), int(m), int(s))]
    }
    for t in result.topics:
        assert t.start_time is None or int(t.start_time) in transcript_seconds