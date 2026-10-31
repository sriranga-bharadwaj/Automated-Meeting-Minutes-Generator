import json
import os
import re
from typing import Callable, Optional

import ollama
from pydantic import BaseModel, Field, ValidationError

from .schema import MeetingMinutes, ActionItem, Decision, Topic
from .prompts import (
    SYSTEM_PROMPT,
    build_user_prompt,
    OVERVIEW_SYSTEM_PROMPT,
    build_overview_prompt,
    ACTION_SYSTEM_PROMPT,
    build_action_prompt,
)

DEFAULT_MODEL = os.environ.get("MINUTES_MODEL", "qwen2.5:7b")
NUM_CTX = 8192        # context window we ask Ollama for (default is only 4096)
CHUNK_WORDS = 1200    # max words of transcript per chunk
OVERLAP_LINES = 3     # lines repeated between neighbouring chunks

STOPWORDS = {
    "a", "an", "the", "for", "and", "or", "to", "of", "in", "on", "at", "by",
    "it", "is", "be", "we", "will", "that", "this", "with", "as",
}


class MinutesGenerationError(Exception):
    """Raised when minutes cannot be generated or the output is invalid."""


class Overview(BaseModel):
    title: str
    summary: str


class LLMTopic(BaseModel):
    title: str
    summary: str
    start_quote: Optional[str] = None     # first words of the line where the topic begins


class LLMMinutes(BaseModel):
    """What we ask the model for. Same as MeetingMinutes, except topics carry
    a quote instead of a start_time, because we compute the time ourselves."""
    title: str
    summary: str
    participants: list[str] = Field(default_factory=list)
    topics: list[LLMTopic] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)


class ActionPassItem(BaseModel):
    source_quote: str = ""
    task: str
    owner: Optional[str] = None
    deadline: Optional[str] = None


class ActionPass(BaseModel):
    action_items: list[ActionPassItem] = Field(default_factory=list)


# ---------- LLM call helper ----------

def _chat_json(model, system, user, schema_model, max_retries):
    last_error = None
    for _ in range(max_retries + 1):
        try:
            response = ollama.chat(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                format=schema_model.model_json_schema(),
                options={"temperature": 0, "num_ctx": NUM_CTX},
            )
            return schema_model.model_validate_json(response["message"]["content"])
        except (ValidationError, json.JSONDecodeError) as e:
            last_error = e                      # bad output: try again
        except Exception as e:
            raise MinutesGenerationError(f"LLM call failed: {e}") from e
    raise MinutesGenerationError(
        f"Model returned invalid output after {max_retries + 1} attempts: {last_error}"
    )


# ---------- chunking ----------

def chunk_transcript(
    transcript: str,
    max_words: int = CHUNK_WORDS,
    overlap_lines: int = OVERLAP_LINES,
) -> list[str]:
    lines = [ln for ln in transcript.splitlines() if ln.strip()]
    chunks, current, count = [], [], 0
    for line in lines:
        n = len(line.split())
        if current and count + n > max_words:
            chunks.append("\n".join(current))
            current = current[-overlap_lines:]          # carry the overlap forward
            count = sum(len(ln.split()) for ln in current)
        current.append(line)
        count += n
    if current:
        chunks.append("\n".join(current))
    return chunks


# ---------- timestamps ----------

TS_RE = re.compile(r"\[(\d+):(\d{2}):(\d{2})\]")


def _line_seconds(line: str) -> Optional[int]:
    m = TS_RE.search(line)
    if not m:
        return None
    h, mnt, s = (int(x) for x in m.groups())
    return h * 3600 + mnt * 60 + s


def find_start_time(quote: Optional[str], chunk: str) -> Optional[float]:
    """Find the transcript line that best matches the quote and return its time in seconds."""
    if not quote:
        return None
    qset = set(re.findall(r"\w+", quote.lower()))
    if not qset:
        return None
    best, best_score = None, 0.0
    for line in chunk.splitlines():
        secs = _line_seconds(line)
        if secs is None:
            continue
        words = set(re.findall(r"\w+", TS_RE.sub("", line).lower()))
        score = len(qset & words) / len(qset)       # share of quote words found in the line
        if score > best_score:                      # '>' keeps the earliest line on ties
            best, best_score = secs, score
    return float(best) if best is not None and best_score >= 0.6 else None


def _to_minutes(llm: LLMMinutes, chunk: str) -> MeetingMinutes:
    return MeetingMinutes(
        title=llm.title,
        summary=llm.summary,
        participants=llm.participants,
        topics=[
            Topic(
                title=t.title,
                summary=t.summary,
                start_time=find_start_time(t.start_quote, chunk),
            )
            for t in llm.topics
        ],
        decisions=llm.decisions,
        action_items=llm.action_items,
    )


# ---------- focused action-item pass ----------

DEADLINE_RE = re.compile(r"\b((?:before|after|by|until|within)\s+[^.,;!?]+)", re.IGNORECASE)

PLACEHOLDER_OWNERS = {
    "someone", "somebody", "anyone", "anybody", "nobody", "no one", "everyone",
    "everybody", "unknown", "unassigned", "none", "null", "n/a", "na", "tbd",
    "team", "the team", "speaker", "attendee", "late attendee", "participant",
}
NAME_FILLER = {"and", "the", "of", "team"}


def _clean_owner(owner: Optional[str], text: str) -> Optional[str]:
    """Drop placeholder owners ('Someone') and names that never occur in the transcript."""
    if not owner or not owner.strip():
        return None
    owner = owner.strip()
    if owner.lower() in PLACEHOLDER_OWNERS:
        return None
    text_words = set(re.findall(r"\w+", text.lower()))
    tokens = [t for t in re.findall(r"\w+", owner.lower()) if t not in NAME_FILLER]
    return owner if any(t in text_words for t in tokens) else None


def _best_line_index(quote: Optional[str], lines: list[str]) -> Optional[int]:
    if not quote:
        return None
    qset = set(re.findall(r"\w+", quote.lower()))
    if not qset:
        return None
    best, best_score = None, 0.0
    for i, line in enumerate(lines):
        words = set(re.findall(r"\w+", TS_RE.sub("", line).lower()))
        score = len(qset & words) / len(qset)
        if score > best_score:
            best, best_score = i, score
    return best if best_score >= 0.6 else None


def find_line(quote: Optional[str], chunk: str) -> Optional[str]:
    """Return the transcript line that best matches the quote (timestamps not required)."""
    lines = chunk.splitlines()
    i = _best_line_index(quote, lines)
    return lines[i] if i is not None else None


def fallback_deadline(line: Optional[str]) -> Optional[str]:
    """Safety net: pull 'before the review' / 'by Friday' out of the source line."""
    if not line:
        return None
    m = DEADLINE_RE.search(TS_RE.sub("", line))
    return m.group(1).strip() if m else None


def _deadline_supported(deadline: str, window: str) -> bool:
    """Is the deadline really mentioned in (or right after) the task's source line?"""
    words = {w for w in re.findall(r"\w+", deadline.lower()) if w not in STOPWORDS}
    if not words:
        return True
    present = set(re.findall(r"\w+", TS_RE.sub("", window).lower()))
    return len(words & present) / len(words) >= 0.6


def _extract_actions(model: str, chunk: str, max_retries: int) -> list[ActionItem]:
    result = _chat_json(model, ACTION_SYSTEM_PROMPT, build_action_prompt(chunk),
                        ActionPass, max_retries)
    lines = chunk.splitlines()
    items = []
    for a in result.action_items:
        idx = _best_line_index(a.source_quote, lines)
        line = lines[idx] if idx is not None else None
        window = " ".join(lines[idx:idx + 2]) if idx is not None else None

        deadline = a.deadline
        if deadline and window and not _deadline_supported(deadline, window):
            deadline = None          # the model borrowed it from a neighbouring task
        if deadline is None:
            deadline = fallback_deadline(line) or fallback_deadline(find_line(a.task, chunk))

        items.append(ActionItem(task=a.task, owner=_clean_owner(a.owner, chunk), deadline=deadline))
    return items


# ---------- merging ----------

def _words(text: str) -> set:
    return {w for w in re.findall(r"\w+", text.lower()) if w not in STOPWORDS}


def _similar(a: str, b: str, threshold: float = 0.7) -> bool:
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return False
    # overlap coefficient: a short text contained in a longer one still matches
    return len(wa & wb) / min(len(wa), len(wb)) >= threshold


def _owners_compatible(a: Optional[str], b: Optional[str]) -> bool:
    return a is None or b is None or a.lower() == b.lower()


def _dedupe_actions(items: list[ActionItem]) -> list[ActionItem]:
    kept: list[ActionItem] = []
    for item in items:
        dup = next(
            (k for k in kept
             if _owners_compatible(k.owner, item.owner) and _similar(k.task, item.task)),
            None,
        )
        if dup is None:
            kept.append(item)
            continue
        if len(item.task) > len(dup.task):
            dup.task = item.task                  # keep the more detailed wording
        if dup.owner is None:
            dup.owner = item.owner
        if dup.deadline is None:
            dup.deadline = item.deadline
    return kept


def _merge_main_into_focused(
    focused: list[ActionItem],
    main: list[ActionItem],
    threshold: float = 0.5,
) -> list[ActionItem]:
    """Focused-pass items are authoritative; main-pass items only add what is new."""
    out = list(focused)
    for item in main:
        dup = next(
            (k for k in out
             if _owners_compatible(k.owner, item.owner)
             and _similar(k.task, item.task, threshold)),
            None,
        )
        if dup is None:
            out.append(item)
            continue
        if dup.owner is None:
            dup.owner = item.owner
        if dup.deadline is None:
            dup.deadline = item.deadline
    return out


def _dedupe_decisions(items: list[Decision]) -> list[Decision]:
    kept: list[Decision] = []
    for item in items:
        dup = next((k for k in kept if _similar(k.decision, item.decision)), None)
        if dup is None:
            kept.append(item)
            continue
        if len(item.decision) > len(dup.decision):
            dup.decision = item.decision
            if item.context:
                dup.context = item.context   # context travels with its wording
        elif dup.context is None:
            dup.context = item.context
    return kept


def _drop_task_decisions(
    decisions: list[Decision], actions: list[ActionItem], threshold: float = 0.8
) -> list[Decision]:
    """A 'decision' that only restates an assigned task is really an action item."""
    return [
        d for d in decisions
        if not any(_similar(d.decision, a.task, threshold) for a in actions)
    ]


def _dedupe_topics(items: list[Topic]) -> list[Topic]:
    kept: list[Topic] = []
    for item in items:
        if not any(_similar(k.title, item.title) for k in kept):
            kept.append(item)
    return kept


def _dedupe_names(names: list[str]) -> list[str]:
    seen, out = set(), []
    for n in names:
        if n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return out

# ---------- safety net for missed commitments ----------

COMMIT_RE = re.compile(
    r"\bi(?:['’]ll| will|['’]m going to| am going to| should have"
    r"| can (?:take|look|handle|do|get|send|check|pick|own|start))\b"
    r"|\blet me\b",
    re.IGNORECASE,
)


def _uncovered_commitment_lines(chunk: str, actions: list[ActionItem], threshold: float = 0.4) -> list[int]:
    """Indexes of lines that contain a first-person commitment but match no action item."""
    lines = chunk.splitlines()
    missing = []
    for i, line in enumerate(lines):
        if not COMMIT_RE.search(TS_RE.sub("", line)):
            continue
        window_words = _words(TS_RE.sub("", " ".join(lines[max(0, i - 1): i + 1])))
        covered = False
        for a in actions:
            task_words = _words(a.task)
            if task_words and len(task_words & window_words) / len(task_words) >= threshold:
                covered = True
                break
        if not covered:
            missing.append(i)
    return missing


def _add_missed_commitments(
    model: str, chunk: str, actions: list[ActionItem], max_retries: int, max_calls: int = 6
) -> list[ActionItem]:
    lines = chunk.splitlines()
    for i in _uncovered_commitment_lines(chunk, actions)[:max_calls]:
        mini = "\n".join(lines[max(0, i - 1): i + 1])      # the line plus the one before it
        found = _extract_actions(model, mini, max_retries)
        actions = _merge_main_into_focused(actions, found)  # existing items win; new ones are added
    return actions


# ---------- public function ----------

def generate_minutes(
    transcript: str,
    model: str = DEFAULT_MODEL,
    max_retries: int = 2,
    chunk_words: int = CHUNK_WORDS,
    progress: Optional[Callable[[int, int], None]] = None,
) -> MeetingMinutes:
    """Transcript in, structured minutes out.

    progress(done, total) is called after each chunk, so the API / UI
    can show a progress bar.
    """
    if not transcript or not transcript.strip():
        raise MinutesGenerationError("Transcript is empty.")

    chunks = chunk_transcript(transcript, max_words=chunk_words)
    parts: list[MeetingMinutes] = []
    for i, chunk in enumerate(chunks, start=1):
        llm = _chat_json(model, SYSTEM_PROMPT, build_user_prompt(chunk),
                         LLMMinutes, max_retries)
        minutes = _to_minutes(llm, chunk)

        # Remove invented or placeholder names ("Someone", "Late Attendee") before merging,
        # so duplicates with a fake owner can merge with the real one.
        minutes.participants = _dedupe_names(
            [p for p in (_clean_owner(n, chunk) for n in minutes.participants) if p]
        )
        for a in minutes.action_items:
            a.owner = _clean_owner(a.owner, chunk)

        extra = _extract_actions(model, chunk, max_retries)
        minutes.action_items = _merge_main_into_focused(
            _dedupe_actions(extra),
            _dedupe_actions(minutes.action_items),
        )
        minutes.action_items = _add_missed_commitments(model, chunk, minutes.action_items, max_retries)
        minutes.decisions = _drop_task_decisions(minutes.decisions, minutes.action_items)
        parts.append(minutes)
        if progress:
            progress(i, len(chunks))

    if len(parts) == 1:
        return parts[0]

    overview = _chat_json(
        model,
        OVERVIEW_SYSTEM_PROMPT,
        build_overview_prompt([p.summary for p in parts]),
        Overview,
        max_retries,
    )
    return MeetingMinutes(
        title=overview.title,
        summary=overview.summary,
        participants=_dedupe_names([n for p in parts for n in p.participants]),
        topics=_dedupe_topics([t for p in parts for t in p.topics]),
        decisions=_dedupe_decisions([d for p in parts for d in p.decisions]),
        action_items=_dedupe_actions([a for p in parts for a in p.action_items]),
    )