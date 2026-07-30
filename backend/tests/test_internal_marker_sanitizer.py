from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.nlp.internal_marker_sanitizer import InternalMarkerStreamSanitizer, strip_internal_control_markers


def _run(chunks: list[str]) -> list[str]:
    sanitizer = InternalMarkerStreamSanitizer()
    output = [sanitizer.feed(chunk) for chunk in chunks]
    output.append(sanitizer.flush())
    return output


def test_complete_category_marker_in_one_chunk() -> None:
    assert _run(["[[category:technical]]", "AI is software..."]) == ["", "AI is software..", "."]


def test_category_marker_split_across_two_chunks() -> None:
    assert "".join(_run(["[[cate", "gory:technical]]AI is software..."])) == "AI is software..."


def test_category_marker_split_across_many_chunks() -> None:
    assert "".join(_run(["[[cate", "gory:tech", "nical]]", "AI is software..."])) == "AI is software..."


def test_marker_followed_immediately_by_answer_text() -> None:
    assert "".join(_run(["[[category:technical]]AI is software..."])) == "AI is software..."


def test_marker_followed_by_newline_and_answer_text() -> None:
    assert "".join(_run(["[[category:technical]]\n", "AI is software..."])) == "AI is software..."


def test_leading_whitespace_before_marker_is_removed() -> None:
    assert "".join(_run([" \n[[category:technical]]\n", "AI is software..."])) == "AI is software..."


def test_multiple_consecutive_known_markers_are_removed() -> None:
    assert "".join(_run(["[[category:technical]][[mode:answer]]", "AI is software..."])) == "AI is software..."


def test_multiple_markers_split_across_chunks_are_removed() -> None:
    chunks = ["[[cate", "gory:technical]][[mo", "de:answer]]AI"]
    assert "".join(_run(chunks)) == "AI"


def test_normal_matrix_indexing_remains_unchanged() -> None:
    assert "".join(_run(["Use matrix[i][j] to access an element."])) == "Use matrix[i][j] to access an element."


def test_nested_list_syntax_remains_unchanged() -> None:
    assert "".join(_run(["Example: [[1, 2], [3, 4]]"])) == "Example: [[1, 2], [3, 4]]"


def test_unknown_marker_remains_unchanged() -> None:
    assert "".join(_run(["[[unknown:value]] is part of the answer."])) == "[[unknown:value]] is part of the answer."


def test_incomplete_marker_at_end_of_stream_is_dropped_when_it_is_control_like_prefix() -> None:
    sanitizer = InternalMarkerStreamSanitizer()
    assert sanitizer.feed("[[cate") == ""
    assert sanitizer.flush() == ""


def test_flush_preserves_valid_remaining_text() -> None:
    sanitizer = InternalMarkerStreamSanitizer()
    assert sanitizer.feed("AI") == "A"
    assert sanitizer.flush() == "I"


def test_empty_chunks_do_not_fail() -> None:
    sanitizer = InternalMarkerStreamSanitizer()
    assert sanitizer.feed("") == ""
    assert sanitizer.flush() == ""


def test_unicode_answer_text_remains_unchanged() -> None:
    text = "AI helps summarize resumes and answer प्रश्न clearly."
    assert "".join(_run([text])) == text


def test_final_cleanup_is_idempotent() -> None:
    once = strip_internal_control_markers("[[category:technical]]\nAI is software.")
    twice = strip_internal_control_markers(once)
    assert once == "AI is software."
    assert twice == once


def test_concurrent_streams_use_isolated_state() -> None:
    left = InternalMarkerStreamSanitizer()
    right = InternalMarkerStreamSanitizer()
    assert left.feed("[[cate") == ""
    assert right.feed("Use [[1, 2], [3, 4]]") == "Use [[1, 2], [3, 4]]"
    assert left.feed("gory:technical]]AI") == "A"
    assert left.flush() == "I"
    assert right.flush() == ""
