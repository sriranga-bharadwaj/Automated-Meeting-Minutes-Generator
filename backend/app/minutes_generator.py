
import re


def generate_minutes(transcript: str) -> dict:
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
        "decision ",
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
        "summary": text,
        "key_discussions": sentences[:10],
        "decisions": decisions,
        "action_items": action_items,
        "transcript": text,
    }
