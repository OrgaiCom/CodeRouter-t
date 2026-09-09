"""Bug condition exploration and preservation tests for translator.py log message issue.

**Property 1: Bug Condition** — EN→JA ログの不正確なメッセージ（is_japanese スキップ時）

This test is EXPECTED TO FAIL on unfixed code.
Failure confirms that the bug exists: when `is_japanese()` skips a block,
the unfixed code outputs "(no English text to translate)" instead of the
correct "(already Japanese, skipped translation)".

**Property 2: Preservation** — EN→JA 翻訳成功ケースのログ出力は変更されない

These tests PASS on unfixed code. They confirm baseline behavior to preserve:
- Actual EN→JA translations produce correct log_translation_pair calls
- verbose=False suppresses all log_translation_pair calls

Validates: Requirements 2.1, 3.1, 3.2, 3.3, 3.4, 3.5
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from coderouter.jp_translation.translator import translate_anthropic_response_en_to_ja
from coderouter.translation.anthropic import AnthropicResponse, AnthropicUsage


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_manager(translated_text: str = "翻訳済みテキスト"):
    """Mock TranslatorManager that reports itself as available."""
    m = MagicMock()
    m.is_available.return_value = True
    m.translate_en_to_ja.return_value = translated_text
    return m


def _make_response(*blocks) -> AnthropicResponse:
    """Build an AnthropicResponse from raw content block dicts."""
    return AnthropicResponse(
        id="test-id",
        model="test-model",
        content=list(blocks),
        stop_reason="end_turn",
        usage=AnthropicUsage(input_tokens=10, output_tokens=5),
    )


def _get_log_original(mock_log) -> str:
    """Extract the `original` kwarg from the most recent log_translation_pair call."""
    call_kwargs = mock_log.call_args
    if call_kwargs.kwargs.get("original") is not None:
        return call_kwargs.kwargs["original"]
    # positional: log_translation_pair(logger, *, direction, original, ...)
    # All args are keyword-only after logger, so kwargs should always be populated.
    return call_kwargs.args[2]


# ---------------------------------------------------------------------------
# Property 1: Bug Condition exploration test (FAILS on unfixed code)
# ---------------------------------------------------------------------------


def _make_japanese_response() -> AnthropicResponse:
    """AnthropicResponse with a single Japanese text block (triggers is_japanese() skip)."""
    return _make_response({"type": "text", "text": "こんにちは"})


def test_bug1_is_japanese_skip_logs_correct_message():
    """
    **Validates: Requirements 2.1**

    When translate_anthropic_response_en_to_ja is called with verbose=True and
    the response contains only a Japanese text block (is_japanese() returns True),
    log_translation_pair MUST be called with original="(already Japanese, skipped translation)".

    On UNFIXED code, the actual call uses original="(no English text to translate)",
    so this assertion FAILS — which is the expected outcome confirming the bug exists.

    Counterexample documented:
      log_translation_pair receives original="(no English text to translate)"
      instead of the correct "(already Japanese, skipped translation)"
    """
    manager = _make_manager()
    resp = _make_japanese_response()

    with patch(
        "coderouter.jp_translation.translator.log_translation_pair"
    ) as mock_log, patch(
        "coderouter.jp_translation.translator.is_japanese", return_value=True
    ):
        translate_anthropic_response_en_to_ja(resp, manager, verbose=True)

    assert mock_log.called, "log_translation_pair should have been called with verbose=True"

    actual_original = _get_log_original(mock_log)

    assert actual_original == "(already Japanese, skipped translation)", (
        f"Bug confirmed: log_translation_pair was called with original={actual_original!r} "
        f"instead of '(already Japanese, skipped translation)'. "
        f"This is the bug: is_japanese() skip is indistinguishable from 'no text blocks'."
    )


# ---------------------------------------------------------------------------
# Property 2: Preservation tests (PASS on both unfixed and fixed code)
# ---------------------------------------------------------------------------


def test_preservation_english_text_translation_logged():
    """
    **Validates: Requirements 3.1, 3.2**

    When an English text block is actually translated, log_translation_pair
    MUST be called with direction="en_to_ja", the original English text as
    `original`, and the translated Japanese text as `translated`, blocks=1.

    This behavior must be preserved unchanged by the fix.
    """
    english_text = "Hello, world!"
    japanese_text = "こんにちは、世界！"
    manager = _make_manager(translated_text=japanese_text)
    resp = _make_response({"type": "text", "text": english_text})

    with patch(
        "coderouter.jp_translation.translator.log_translation_pair"
    ) as mock_log, patch(
        "coderouter.jp_translation.translator.is_japanese", return_value=False
    ), patch(
        "coderouter.jp_translation.translator._translate_with_protection",
        return_value=japanese_text,
    ):
        translate_anthropic_response_en_to_ja(resp, manager, verbose=True)

    assert mock_log.called, "log_translation_pair must be called when translation occurs"

    call_kwargs = mock_log.call_args
    assert call_kwargs.kwargs["direction"] == "en_to_ja"
    assert call_kwargs.kwargs["original"] == english_text
    assert call_kwargs.kwargs["translated"] == japanese_text
    assert call_kwargs.kwargs["blocks"] == 1


@pytest.mark.parametrize(
    "english_texts,japanese_texts",
    [
        (["First sentence."], ["最初の文。"]),
        (["Block one.", "Block two."], ["ブロック一。", "ブロック二。"]),
        (["Alpha", "Beta", "Gamma"], ["アルファ", "ベータ", "ガンマ"]),
    ],
)
def test_preservation_multi_block_translation_logged(english_texts, japanese_texts):
    """
    **Validates: Requirements 3.1, 3.2, 3.3**

    For multiple English text blocks, log_translation_pair must receive
    all original texts joined with newlines, all translated texts joined
    with newlines, and blocks=len(english_texts).

    This behavior must be preserved unchanged by the fix.
    """
    content_blocks = [{"type": "text", "text": t} for t in english_texts]
    resp = _make_response(*content_blocks)
    manager = _make_manager()

    translate_side_effects = iter(japanese_texts)

    with patch(
        "coderouter.jp_translation.translator.log_translation_pair"
    ) as mock_log, patch(
        "coderouter.jp_translation.translator.is_japanese", return_value=False
    ), patch(
        "coderouter.jp_translation.translator._translate_with_protection",
        side_effect=lambda text, _dir, _mgr: next(translate_side_effects),
    ):
        translate_anthropic_response_en_to_ja(resp, manager, verbose=True)

    assert mock_log.called, "log_translation_pair must be called when translation occurs"

    call_kwargs = mock_log.call_args
    assert call_kwargs.kwargs["direction"] == "en_to_ja"
    assert call_kwargs.kwargs["original"] == "\n".join(english_texts)
    assert call_kwargs.kwargs["translated"] == "\n".join(japanese_texts)
    assert call_kwargs.kwargs["blocks"] == len(english_texts)


def test_preservation_verbose_false_no_log():
    """
    **Validates: Requirements 3.4**

    When verbose=False, log_translation_pair must NOT be called regardless
    of what the response contains.

    This behavior must be preserved unchanged by the fix.
    """
    resp = _make_response({"type": "text", "text": "Hello, world!"})
    manager = _make_manager()

    with patch(
        "coderouter.jp_translation.translator.log_translation_pair"
    ) as mock_log, patch(
        "coderouter.jp_translation.translator.is_japanese", return_value=False
    ), patch(
        "coderouter.jp_translation.translator._translate_with_protection",
        return_value="こんにちは、世界！",
    ):
        translate_anthropic_response_en_to_ja(resp, manager, verbose=False)

    assert not mock_log.called, (
        "log_translation_pair must NOT be called when verbose=False"
    )


def test_preservation_verbose_false_japanese_input_no_log():
    """
    **Validates: Requirements 3.4**

    When verbose=False and the response is Japanese (is_japanese skip path),
    log_translation_pair must NOT be called.

    This behavior must be preserved unchanged by the fix.
    """
    resp = _make_response({"type": "text", "text": "こんにちは"})
    manager = _make_manager()

    with patch(
        "coderouter.jp_translation.translator.log_translation_pair"
    ) as mock_log, patch(
        "coderouter.jp_translation.translator.is_japanese", return_value=True
    ):
        translate_anthropic_response_en_to_ja(resp, manager, verbose=False)

    assert not mock_log.called, (
        "log_translation_pair must NOT be called when verbose=False, even on is_japanese skip path"
    )


def test_preservation_tool_use_only_response():
    """
    **Validates: Requirements 3.5**

    When the response contains only tool_use blocks (no translatable text),
    log_translation_pair must still be called with verbose=True (skip log).
    The content of the skip log is governed by Property 1 / Property 2 scope;
    this test confirms log_translation_pair IS called once (observability preserved).
    """
    resp = _make_response(
        {"type": "tool_use", "id": "tool-1", "name": "my_tool", "input": {}}
    )
    manager = _make_manager()

    with patch(
        "coderouter.jp_translation.translator.log_translation_pair"
    ) as mock_log:
        translate_anthropic_response_en_to_ja(resp, manager, verbose=True)

    assert mock_log.called, (
        "log_translation_pair must be called once for observability even when no text blocks exist"
    )
    # Should log the 'no translatable text' case — blocks=0
    assert mock_log.call_args.kwargs["blocks"] == 0
    assert mock_log.call_args.kwargs["direction"] == "en_to_ja"


def test_preservation_mixed_japanese_and_english_blocks():
    """
    **Validates: Requirements 3.1, 3.3**

    For a response with mixed Japanese (skipped) and English (translated) blocks,
    only the English blocks should appear in the log. The Japanese blocks are
    skipped by is_japanese() and must not pollute the logged original/translated text.
    """
    english_text = "This is English."
    japanese_text = "これは日本語です。"
    translated = "これは英語です。"

    resp = _make_response(
        {"type": "text", "text": japanese_text},
        {"type": "text", "text": english_text},
    )
    manager = _make_manager()

    def _is_japanese_side_effect(text):
        # Return True for the Japanese text block, False for English
        return text == japanese_text

    with patch(
        "coderouter.jp_translation.translator.log_translation_pair"
    ) as mock_log, patch(
        "coderouter.jp_translation.translator.is_japanese",
        side_effect=_is_japanese_side_effect,
    ), patch(
        "coderouter.jp_translation.translator._translate_with_protection",
        return_value=translated,
    ):
        translate_anthropic_response_en_to_ja(resp, manager, verbose=True)

    assert mock_log.called
    call_kwargs = mock_log.call_args
    # Only the English block should be in the log — not the skipped Japanese block
    assert call_kwargs.kwargs["original"] == english_text
    assert call_kwargs.kwargs["translated"] == translated
    assert call_kwargs.kwargs["blocks"] == 1
