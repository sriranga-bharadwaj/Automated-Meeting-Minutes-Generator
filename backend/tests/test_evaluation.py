import pytest

from app.evaluation import normalise, word_error_rate


def test_identical_text_has_zero_error():
    assert word_error_rate("We decided to ship on Friday.", "we decided to ship on friday") == 0.0


def test_counts_substitution_deletion_and_insertion():
    assert word_error_rate("a b c d", "a x c d") == pytest.approx(0.25)   # 1 substitution
    assert word_error_rate("a b c d", "a b d") == pytest.approx(0.25)     # 1 deletion
    assert word_error_rate("a b c d", "a b c x d") == pytest.approx(0.25) # 1 insertion


def test_everything_missing_is_one_hundred_percent():
    assert word_error_rate("one two three", "") == 1.0


def test_punctuation_case_and_apostrophes_are_ignored():
    assert word_error_rate("Let's start, everyone!", "lets start everyone") == 0.0


def test_empty_reference_is_rejected():
    with pytest.raises(ValueError):
        word_error_rate("  ", "anything")


def test_hindi_words_are_not_broken_apart():
    assert normalise("नमस्ते, सब लोग।") == ["नमस्ते", "सब", "लोग"]
    assert word_error_rate("नमस्ते सब लोग", "नमस्ते सब लोग") == 0.0
