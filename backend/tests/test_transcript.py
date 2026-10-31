from types import SimpleNamespace

from minutes import segments_to_transcript, format_timestamp


def test_format_timestamp():
    assert format_timestamp(0) == "[00:00:00]"
    assert format_timestamp(72.9) == "[00:01:12]"
    assert format_timestamp(3723) == "[01:02:03]"


def test_dict_segments():
    segs = [{"start": 5.2, "end": 9.0, "text": " Hello team. "},
            {"start": 14.0, "end": 19.0, "text": "Upload page is done."}]
    assert segments_to_transcript(segs) == (
        "[00:00:05] Hello team.\n[00:00:14] Upload page is done."
    )


def test_object_segments_like_faster_whisper():
    segs = [SimpleNamespace(start=31.4, end=36.0, text=" It works on short clips. ")]
    assert segments_to_transcript(segs) == "[00:00:31] It works on short clips."


def test_empty_segments_are_skipped():
    segs = [{"start": 1, "end": 2, "text": "   "}, {"start": 3, "end": 4, "text": "Hi"}]
    assert segments_to_transcript(segs) == "[00:00:03] Hi"