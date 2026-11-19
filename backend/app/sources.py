"""Source linking (AMG-F-042): which part of the recording backs each topic, decision or action.

Each item is matched to the transcript segment that shares the most words with it. The match
is returned as ``source = {"start": seconds, "end": seconds, "text": the segment}`` so the UI
can play the recording from that moment. Items with no clear match get no source.
"""
import re
from typing import Optional

MIN_SHARED_WORDS = 2
STOP = {
    "the", "a", "an", "to", "of", "and", "in", "on", "for", "will", "by", "is", "are", "we", "it",
    "that", "this", "with", "be", "at", "as", "from", "have", "has", "was", "were", "can", "you",
}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in STOP and len(w) > 1}


def best_segment(text: str, segments: list[dict]) -> Optional[dict]:
    target = _words(text)
    if not target:
        return None
    best, best_score = None, 0.0
    for seg in segments:
        shared = len(target & _words(seg.get("text", "")))
        if shared < MIN_SHARED_WORDS and shared < len(target):
            continue
        score = shared / (len(target) ** 0.5)
        if score > best_score:
            best, best_score = seg, score
    if best is None:
        return None
    return {"start": best["start"], "end": best["end"], "text": best.get("text", "")}


def attach(minutes: dict, segments: list[dict]) -> dict:
    """Return a copy of the UI minutes with a ``source`` on every item that can be linked."""
    if not segments:
        return minutes
    out = dict(minutes)
    out["topics"] = [
        {**t, "source": best_segment(f"{t.get('title', '')} {t.get('summary', '')}", segments)}
        for t in minutes.get("topics", [])
    ]
    out["decisions"] = [
        {**d, "source": best_segment(d.get("statement", ""), segments)} for d in minutes.get("decisions", [])
    ]
    out["actionItems"] = [
        {**a, "source": best_segment(a.get("task", ""), segments)} for a in minutes.get("actionItems", [])
    ]
    return out
