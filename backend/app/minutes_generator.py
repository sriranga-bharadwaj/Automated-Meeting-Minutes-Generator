"""Meeting-minutes generation for the API.

generate_minutes() uses the LLM generator (the `minutes` package, running a
local model through Ollama). If that is unavailable or fails, it falls back to
the original keyword-based draft, so the API keeps working on machines without
Ollama.

The returned dict always has the original keys (summary, key_discussions,
decisions, action_items, transcript) plus an "engine" field ("llm" or "basic").
LLM results also carry richer fields: title, participants, topics,
decision_details and action_item_details.

Set MINUTES_ENGINE=basic to skip the LLM entirely.
"""
import logging
import os
import re

logger = logging.getLogger(__name__)


def basic_minutes(transcript: str) -> dict:
    """Generate a basic structured meeting-minutes draft from a transcript."""
    if not transcript or not transcript.strip():
        raise ValueError("Transcript cannot be empty.")

    text = re.sub(r"\s+", " ", transcript).strip()
    sentences = re.split(r"(?<=[.!?])\s+", text)

    action_keywords = (
        "will ",
        "should ",
        "need to ",
        "needs to ",
        "must ",
        "action item",
        "follow up",
        "follow-up",
        "assigned to",
    )

    decision_keywords = (
        "decided ",
        "decision",
        "agreed ",
        "approved ",
        "confirmed ",
        "resolved ",
    )

    action_items = [
        sentence
        for sentence in sentences
        if any(keyword in sentence.lower() for keyword in action_keywords)
    ]

    decisions = [
        sentence
        for sentence in sentences
        if any(keyword in sentence.lower() for keyword in decision_keywords)
    ]

    return {
        "engine": "basic",
        "summary": text,
        "key_discussions": sentences[:10],
        "decisions": decisions,
        "action_items": action_items,
        "transcript": text,
    }


def _describe_action(item: dict) -> str:
    owner = item.get("owner") or "unassigned"
    deadline = item.get("deadline") or "none"
    return f"{item['task']} [owner: {owner}; deadline: {deadline}]"


def _llm_minutes(transcript: str, segments=None, progress=None) -> dict:
    # Imported here so the API still starts if the LLM dependencies are missing.
    from minutes import generate_minutes as llm_generate, segments_to_transcript

    llm_input = (segments_to_transcript(segments) if segments else "") or transcript
    data = llm_generate(llm_input, progress=progress).model_dump()
    plain = re.sub(r"\s+", " ", transcript).strip()

    return {
        "engine": "llm",
        "title": data["title"],
        "summary": data["summary"],
        "participants": data["participants"],
        "topics": data["topics"],
        "decision_details": data["decisions"],
        "action_item_details": data["action_items"],
        # Original keys, same shape as before (lists of strings):
        "key_discussions": [f"{t['title']}: {t['summary']}" for t in data["topics"]],
        "decisions": [d["decision"] for d in data["decisions"]],
        "action_items": [_describe_action(a) for a in data["action_items"]],
        "transcript": plain,
    }


def generate_minutes(transcript: str, segments=None, progress=None) -> dict:
    """Generate meeting minutes: LLM first, keyword draft as the fallback."""
    if not transcript or not transcript.strip():
        raise ValueError("Transcript cannot be empty.")

    if os.getenv("MINUTES_ENGINE", "auto").lower() != "basic":
        try:
            return _llm_minutes(transcript, segments, progress)
        except Exception:
            logger.exception("LLM minutes generation failed; using the basic draft instead")

    return basic_minutes(transcript)