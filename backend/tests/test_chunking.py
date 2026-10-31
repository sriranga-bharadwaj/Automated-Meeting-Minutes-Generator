from minutes import ActionItem
from minutes.generator import chunk_transcript, _dedupe_actions
from minutes import Decision
from minutes.generator import _dedupe_decisions
from minutes.generator import find_start_time
from minutes.generator import find_line, fallback_deadline
from minutes.generator import _merge_main_into_focused
from minutes.generator import _drop_task_decisions

def make_transcript(n_lines, words_per_line=10):
    return "\n".join(
        f"[00:00:{i:03d}] " + " ".join(["word"] * words_per_line)
        for i in range(n_lines)
    )


def test_short_transcript_is_one_chunk():
    assert len(chunk_transcript(make_transcript(5))) == 1


def test_long_transcript_is_split():
    chunks = chunk_transcript(make_transcript(300), max_words=500)
    assert len(chunks) > 1


def test_no_line_is_lost():
    t = make_transcript(300)
    seen = set()
    for c in chunk_transcript(t, max_words=500):
        seen.update(c.splitlines())
    assert seen == set(t.splitlines())


def test_chunks_overlap():
    chunks = chunk_transcript(make_transcript(300), max_words=500, overlap_lines=3)
    assert chunks[1].splitlines()[:3] == chunks[0].splitlines()[-3:]


def test_dedupe_merges_same_task_and_keeps_deadline():
    items = [
        ActionItem(task="Record a sample meeting", owner="Meera", deadline=None),
        ActionItem(task="Record the sample meeting", owner="Meera", deadline="Monday"),
    ]
    out = _dedupe_actions(items)
    assert len(out) == 1
    assert out[0].deadline == "Monday"


def test_dedupe_keeps_different_owners_apart():
    items = [
        ActionItem(task="Write the README", owner="Ravi"),
        ActionItem(task="Write the README", owner="Priya"),
    ]
    assert len(_dedupe_actions(items)) == 2

def test_dedupe_actions_with_different_wording():
    items = [
        ActionItem(task="Record a sample meeting for the demo", owner="Meera", deadline="Monday"),
        ActionItem(task="Record the sample meeting and send it to Priya by Monday",
                   owner="Meera", deadline="Monday"),
    ]
    out = _dedupe_actions(items)
    assert len(out) == 1
    assert "Priya" in out[0].task          # kept the more detailed wording


def test_missing_owner_is_filled_from_other_chunk():
    items = [
        ActionItem(task="Record the sample meeting", owner=None),
        ActionItem(task="Record the sample meeting", owner="Meera", deadline="Monday"),
    ]
    out = _dedupe_actions(items)
    assert len(out) == 1
    assert out[0].owner == "Meera"
    assert out[0].deadline == "Monday"


def test_dedupe_decisions_short_inside_long():
    items = [
        Decision(decision="Use a pre-recorded demo"),
        Decision(decision="Use a pre-recorded five-minute meeting for the demo"),
    ]
    assert len(_dedupe_decisions(items)) == 1


def test_different_decisions_stay_apart():
    items = [
        Decision(decision="Use Postgres for storage"),
        Decision(decision="Launch the beta on Friday"),
    ]
    assert len(_dedupe_decisions(items)) == 2

CHUNK = (
    "[00:00:14] Ravi, where are we with the frontend screens?\n"
    "[00:00:19] The upload page is done.\n"
    "[01:02:03] Meera, can you record the sample meeting?"
)


def test_find_start_time_exact():
    assert find_start_time("Ravi, where are we with the frontend screens?", CHUNK) == 14.0


def test_find_start_time_handles_hours():
    assert find_start_time("Meera, can you record", CHUNK) == 3723.0


def test_find_start_time_tolerates_small_errors():
    assert find_start_time("Ravi where are we with the front end screens", CHUNK) == 14.0


def test_find_start_time_no_match_returns_none():
    assert find_start_time("completely unrelated sentence here", CHUNK) is None


def test_find_start_time_without_timestamps_returns_none():
    assert find_start_time("hello there", "hello there\nhow are you") is None

def test_decision_context_follows_the_longer_wording():
    items = [
        Decision(decision="Use a pre-recorded demo",
                 context="Discussed options, no choice made"),
        Decision(decision="Use a pre-recorded five-minute meeting for the demo",
                 context="Safer if the internet fails"),
    ]
    out = _dedupe_decisions(items)
    assert len(out) == 1
    assert out[0].context == "Safer if the internet fails"

def test_fallback_deadline_event():
    assert fallback_deadline("[00:00:31] I'll swap them out before the review.") == "before the review"


def test_fallback_deadline_day():
    assert fallback_deadline("I should have it ready by Wednesday.") == "by Wednesday"


def test_fallback_deadline_none():
    assert fallback_deadline("It works on short clips but longer ones are slow.") is None


def test_find_line_returns_the_whole_line():
    chunk = (
        "[00:00:31] Mostly. The copy is final but the images are placeholders. "
        "I'll swap them out before the review.\n"
        "[00:00:42] When's the review again?"
    )
    assert "before the review" in find_line("Mostly. The copy is final", chunk)

def test_main_pass_duplicate_is_absorbed_by_focused_pass():
    focused = [ActionItem(task="Swap out the images on the pricing page",
                          owner="Anita", deadline="before the review")]
    main = [ActionItem(task="Replace placeholders with final images on the pricing page",
                       owner="Anita")]
    out = _merge_main_into_focused(focused, main)
    assert len(out) == 1
    assert out[0].deadline == "before the review"


def test_main_pass_unique_item_is_kept():
    focused = [ActionItem(task="Email the beta users", owner=None)]
    main = [ActionItem(task="Book the meeting room", owner="Dev")]
    assert len(_merge_main_into_focused(focused, main)) == 2

def test_find_line_by_task_wording_gives_the_deadline():
    chunk = (
        "[00:01:23] One more thing, someone needs to write the README before submission. "
        "Nobody has volunteered yet.\n"
        "[00:01:31] Let's leave that open for now and revisit it next meeting."
    )
    assert fallback_deadline(find_line("Write the README", chunk)) == "before submission"

def test_task_assignment_is_not_a_decision():
    decisions = [
        Decision(decision="Move review to Thursday"),
        Decision(decision="Dev will look at refund bug after review"),
    ]
    actions = [ActionItem(task="Look at refund bug", owner="Dev", deadline="after the review")]
    out = _drop_task_decisions(decisions, actions)
    assert [d.decision for d in out] == ["Move review to Thursday"]


def test_real_decision_is_kept():
    decisions = [Decision(decision="Use a pre-recorded five-minute meeting for the demo")]
    actions = [ActionItem(task="Record the sample meeting and send it to Priya", owner="Meera")]
    assert len(_drop_task_decisions(decisions, actions)) == 1