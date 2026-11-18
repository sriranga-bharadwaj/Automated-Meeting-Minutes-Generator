"""Accuracy metrics for speech-to-text evaluation (no external dependencies)."""
from __future__ import annotations

import unicodedata


def normalise(text: str) -> list[str]:
    """Lower-case, drop punctuation and apostrophes, and split into words.

    Combining marks (e.g. Hindi vowel signs) are kept, so Hindi words stay intact.
    """
    cleaned = []
    for ch in text.lower():
        if ch in "'’":
            continue  # "let's" and "lets" count as the same word
        if unicodedata.category(ch)[0] in "PS":
            cleaned.append(" ")
        else:
            cleaned.append(ch)
    return "".join(cleaned).split()


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Word error rate = (substitutions + deletions + insertions) / reference words."""
    ref, hyp = normalise(reference), normalise(hypothesis)
    if not ref:
        raise ValueError("The reference text is empty.")

    previous = list(range(len(hyp) + 1))
    for i, ref_word in enumerate(ref, start=1):
        current = [i] + [0] * len(hyp)
        for j, hyp_word in enumerate(hyp, start=1):
            current[j] = min(
                previous[j] + 1,                              # deletion
                current[j - 1] + 1,                           # insertion
                previous[j - 1] + (ref_word != hyp_word),     # substitution
            )
        previous = current
    return previous[-1] / len(ref)
