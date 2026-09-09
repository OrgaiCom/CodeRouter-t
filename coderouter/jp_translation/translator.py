"""Translation execution logic with protection.

Design: doc/翻訳層設計書.md §3.3, §7
- content block level separation (text vs tool_use/tool_result/image)
- system prompt is never translated
- is_japanese optimization
- Mask → Translate → Unmask with mutation guard + fallback
- v2.18: chunked translation for 128K tokens (524K chars) + failure-reason logging
"""
from __future__ import annotations

import re
from typing import Any

from coderouter.logging import get_logger, log_translation_pair
from coderouter.translation.anthropic import AnthropicRequest, AnthropicResponse

from .manager import TranslatorManager
from .masking import (
    has_placeholder_mutation,
    is_japanese,
    is_pure_japanese,
    mask_text,
    unmask_text,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# v2.18: chunking helpers
# ---------------------------------------------------------------------------

_DEFAULT_CHUNK_SIZE_CHARS = 4096
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[。．.!?！？])\s+|\n{2,}")


def _find_code_spans(text: str) -> list[tuple[int, int]]:
    """Return list of (start,end) for ``` fences to avoid splitting inside."""
    return [m.span() for m in _CODE_FENCE_RE.finditer(text)]


def _is_inside_code_span(pos: int, spans: list[tuple[int, int]]) -> bool:
    for s, e in spans:
        if s <= pos < e:
            return True
    return False


def _chunk_text(text: str, chunk_size_chars: int = _DEFAULT_CHUNK_SIZE_CHARS) -> list[str]:
    """Split text into chunks <= chunk_size without breaking code fences.

    Strategy:
    - Greedy window of chunk_size.
    - Prefer paragraph boundary (\\n\\n) > sentence boundary (。.!? etc) > newline.
    - Never split inside ``` fences; extend to fence end if needed.
    """
    if not text or len(text) <= chunk_size_chars:
        return [text] if text else []

    spans = _find_code_spans(text)
    chunks: list[str] = []
    start = 0
    n = len(text)

    while start < n:
        if start + chunk_size_chars >= n:
            chunks.append(text[start:])
            break

        window_end = start + chunk_size_chars
        # Avoid cutting inside code fence: extend to fence end
        for s, e in spans:
            if s < window_end < e:
                window_end = e
                break

        window = text[start:window_end]

        # Find best split point: rightmost delimiter across all candidates (balanced chunks)
        # Prefer the split closest to window_end to keep chunks large, avoiding tiny tails
        best_pos = -1
        for delim in ("\n\n", "\n", "。", "．", ". ", "! ", "? ", "！", "？"):
            idx = window.rfind(delim)
            if idx == -1:
                continue
            pos = idx + len(delim)
            if pos <= 512 or pos >= len(window):
                continue
            abs_pos = start + pos
            if _is_inside_code_span(abs_pos - 1, spans):
                continue
            if pos > best_pos:
                best_pos = pos
        split_pos = best_pos

        # Fallback: try regex sentence boundary
        if split_pos == -1:
            # Find all sentence boundaries in window
            candidates = [m.end() for m in _SENTENCE_BOUNDARY_RE.finditer(window)]
            # Pick the last candidate that leaves reasonable size
            for cand in reversed(candidates):
                if cand > 512 and cand < len(window):
                    abs_pos = start + cand
                    if not _is_inside_code_span(abs_pos - 1, spans):
                        split_pos = cand
                        break

        if split_pos == -1 or split_pos <= 0:
            split_pos = len(window)

        chunks.append(text[start : start + split_pos])
        start += split_pos

    return chunks


def _translate_with_protection(
    text: str,
    direction: str,
    manager: TranslatorManager,
    chunk_index: int | None = None,
) -> str:
    """Mask → translate → unmask with fallback on mutation."""
    if not text or not text.strip():
        return text

    masked, mapping = mask_text(text)

    # If masked text has no Japanese (JA→EN) we already checked outside,
    # but keep for EN→JA always translate.
    try:
        if direction == "ja_to_en":
            translated_masked = manager.translate_ja_to_en(masked)
        else:
            translated_masked = manager.translate_en_to_ja(masked)
    except Exception as exc:
        extra = {"direction": direction, "reason": "argos-error", "error": str(exc)}
        if chunk_index is not None:
            extra["chunk_index"] = chunk_index
        logger.warning("translation-failed", extra=extra)
        return text

    # Guard: if placeholder was mutated (SentencePiece split etc.), fallback to original
    if mapping and has_placeholder_mutation(translated_masked, mapping):
        extra = {"direction": direction, "reason": "placeholder-mutated", "expected": len(mapping)}
        if chunk_index is not None:
            extra["chunk_index"] = chunk_index
        logger.warning(
            "translation-placeholder-mutated",
            extra=extra,
        )
        # Try to still unmask what survived, but if critical, return original text?
        # We attempt unmask; if result still contains placeholder prefix fragments, return original masked translation unmasked partially?
        # Safer to return original text (transparent fallback) — but we try unmask first.
        # If many placeholders lost, original is safer.
        # Heuristic: if >50% placeholders lost, fallback to original
        from .masking import _PLACEHOLDER_RE

        found = len(_PLACEHOLDER_RE.findall(translated_masked))
        # Use <= 0.5 (not <) so that losing exactly half the placeholders
        # also triggers the safe fallback (e.g. 1 lost out of 2 = 50% loss).
        if found <= len(mapping) * 0.5:
            extra2 = {
                "direction": direction,
                "reason": "placeholder-mutated-heavy-fallback",
                "expected": len(mapping),
                "found": found,
            }
            if chunk_index is not None:
                extra2["chunk_index"] = chunk_index
            logger.warning("translation-fallback", extra=extra2)
            return text

    return unmask_text(translated_masked, mapping)


def _translate_chunked(
    text: str,
    direction: str,
    manager: TranslatorManager,
    chunk_size_chars: int = _DEFAULT_CHUNK_SIZE_CHARS,
) -> str:
    """Chunk-aware wrapper around _translate_with_protection.

    Short text (<=chunk_size) goes through single call.
    Long text is split at paragraph/sentence boundaries (code-fence aware)
    and each chunk is translated independently, then joined.
    """
    if not text or not text.strip():
        return text
    if len(text) <= chunk_size_chars:
        return _translate_with_protection(text, direction, manager)

    chunks = _chunk_text(text, chunk_size_chars)
    if len(chunks) <= 1:
        return _translate_with_protection(text, direction, manager)

    logger.info(
        "translation-chunked",
        extra={
            "direction": direction,
            "reason": "chunked",
            "total_chars": len(text),
            "chunks": len(chunks),
            "chunk_size": chunk_size_chars,
        },
    )

    translated_parts: list[str] = []
    noop_chunks = 0
    for idx, ch in enumerate(chunks):
        t = _translate_with_protection(ch, direction, manager, chunk_index=idx)
        if t == ch and ch.strip():
            # Argos returned same text — not necessarily error, but log for observability at debug
            logger.debug(
                "translation-chunk-noop",
                extra={
                    "direction": direction,
                    "reason": "argos-same-output",
                    "chunk_index": idx,
                    "chunk_chars": len(ch),
                },
            )
            noop_chunks += 1
        translated_parts.append(t)

    if noop_chunks == len(chunks) and len(chunks) > 1:
        logger.warning(
            "translation-all-chunks-noop",
            extra={
                "direction": direction,
                "reason": "all-chunks-noop",
                "chunks": len(chunks),
                "total_chars": len(text),
            },
        )

    return "".join(translated_parts)


def translate_anthropic_request_ja_to_en(
    req: AnthropicRequest,
    manager: TranslatorManager,
    verbose: bool = False,
    chunk_size_chars: int = _DEFAULT_CHUNK_SIZE_CHARS,
) -> AnthropicRequest:
    """Translate user text blocks JA→EN. System/tool_use/tool_result are skipped.

    This is a synchronous function; caller must asyncio.to_thread if in async context.
    Returns a new AnthropicRequest (mutated copy via model_copy).

    When ``verbose`` is True (default in v2.17), emits one simple
    ``[translation] JA→EN (0.xxxs)`` per request (multi-line, no JSON):

        [translation] JA→EN (0.042s):
        <original>
        ->
        <translated>

    WARN logs (translation-failed etc.) are always emitted regardless of
    ``verbose`` (per v2.17 #2: WARNは常に出す).
    """
    if not manager.is_available():
        logger.warning(
            "translation-skipped",
            extra={"direction": "ja_to_en", "reason": "manager-unavailable"},
        )
        return req

    import time as _time

    # Collect for batch log (request unit)
    _orig_batch: list[str] = []
    _trans_batch: list[str] = []
    _total_elapsed = 0.0
    _skipped_no_japanese = 0
    _skipped_empty = 0

    # Work on a deep copy via model_copy
    # AnthropicRequest.messages is list[AnthropicMessage], content is str | list[dict]
    new_messages = []
    for msg in req.messages:
        role = msg.role
        content = msg.content
        if isinstance(content, str):
            # Short-form string content: only translate if user role and Japanese
            if role == "user" and is_japanese(content):
                _t0 = _time.perf_counter()
                new_content = _translate_chunked(content, "ja_to_en", manager, chunk_size_chars)
                _elapsed = _time.perf_counter() - _t0
                if new_content != content:
                    _orig_batch.append(content)
                    _trans_batch.append(new_content)
                    _total_elapsed += _elapsed
                else:
                    # Log noop reason for this block
                    logger.info(
                        "translation-skipped",
                        extra={
                            "direction": "ja_to_en",
                            "reason": "argos-same-output",
                            "block_chars": len(content),
                        },
                    )
                new_messages.append(msg.model_copy(update={"content": new_content}))
            else:
                # Fix: previous else counted _skipped_empty only when is_japanese==True (dead code)
                # Now correctly: empty vs no-japanese for user role observability
                if not content.strip():
                    _skipped_empty += 1
                elif role == "user" and not is_japanese(content):
                    _skipped_no_japanese += 1
                new_messages.append(msg)
            continue

        # content is list[dict]
        if not isinstance(content, list):
            new_messages.append(msg)
            continue

        new_blocks: list[dict[str, Any]] = []
        for block in content:
            # J-7: Anthropic content may be dict or Pydantic ContentBlock object
            if isinstance(block, dict):
                btype = block.get("type")
                btext = str(block.get("text", ""))
            else:
                btype = getattr(block, "type", None)
                btext = str(getattr(block, "text", "") or "")
            if btype == "text":
                # is_japanese optimization (design 3.3.1)
                if role == "user" and btext and is_japanese(btext):
                    _t0 = _time.perf_counter()
                    new_text = _translate_chunked(btext, "ja_to_en", manager, chunk_size_chars)
                    _elapsed = _time.perf_counter() - _t0
                    if new_text != btext:
                        _orig_batch.append(btext)
                        _trans_batch.append(new_text)
                        _total_elapsed += _elapsed
                    else:
                        logger.info(
                            "translation-skipped",
                            extra={
                                "direction": "ja_to_en",
                                "reason": "argos-same-output",
                                "block_chars": len(btext),
                            },
                        )
                    if isinstance(block, dict):
                        new_block = dict(block)
                        new_block["text"] = new_text
                    else:
                        # Pydantic object: copy with updated text
                        try:
                            new_block = block.model_copy(update={"text": new_text})  # type: ignore[attr-defined]
                        except Exception:
                            new_block = block  # fail-open: keep original on copy error
                    new_blocks.append(new_block)  # type: ignore[arg-type]
                else:
                    if btext.strip():
                        if not is_japanese(btext):
                            _skipped_no_japanese += 1
                        # else role != user: not counted as Japanese skip for user-facing log
                    else:
                        _skipped_empty += 1
                    new_blocks.append(block)  # type: ignore[arg-type]
            elif btype in ("tool_use", "tool_result", "image"):
                # Fully skipped (byte-perfect)
                new_blocks.append(block)  # type: ignore[arg-type]
            else:
                # Unknown block (thinking etc.) — skip translation conservatively
                logger.debug("skip unknown block", extra={"btype": str(btype), "reason": "unknown-block-type"})
                new_blocks.append(block)  # type: ignore[arg-type]
        new_messages.append(msg.model_copy(update={"content": new_blocks}))

    if verbose:
        try:
            if _orig_batch:
                # Join multiple blocks with newline (human readable)
                _orig_text = "\n".join(_orig_batch)
                _trans_text = "\n".join(_trans_batch)
                log_translation_pair(
                    logger,
                    direction="ja_to_en",
                    original=_orig_text,
                    translated=_trans_text,
                    elapsed_s=_total_elapsed,
                    blocks=len(_orig_batch),
                )
            else:
                # No Japanese detected in request — log skipped translation for observability
                # Include reason counts
                if _skipped_no_japanese > 0:
                    reason = "no-japanese-detected"
                elif _skipped_empty > 0:
                    reason = "empty-block"
                else:
                    reason = "no-translatable-block"
                logger.info(
                    "translation-skipped",
                    extra={"direction": "ja_to_en", "reason": reason, "skipped_no_japanese": _skipped_no_japanese, "skipped_empty": _skipped_empty},
                )
                log_translation_pair(
                    logger,
                    direction="ja_to_en",
                    original="(no Japanese text detected)",
                    translated="(no translation needed)",
                    elapsed_s=0.0,
                    blocks=0,
                )
        except Exception:
            pass

    # system field: NEVER translate (design 3.3.2 #1)
    # Even if system is list[ContentBlock] with type text, we skip.
    return req.model_copy(update={"messages": new_messages})


def translate_anthropic_response_en_to_ja(
    resp: AnthropicResponse,
    manager: TranslatorManager,
    verbose: bool = False,
    chunk_size_chars: int = _DEFAULT_CHUNK_SIZE_CHARS,
) -> AnthropicResponse:
    """Translate assistant text blocks EN→JA after Repair.

    Skips tool_use, image. Assumes Repair already structured tool_use.
    Skips blocks that are pure Japanese (is_pure_japanese guard, 案B) to
    avoid double-translation; mixed EN+JA is translated to maximize JA output.
    Synchronous; caller must to_thread if needed.

    When ``verbose`` is True (default in v2.17), emits one simple
    ``[translation] EN→JA (0.xxxs)`` per response (multi-line, no JSON).
    If no block was translated, logs model text + "(no translatable...)"
    or "(empty)" for observability.
    WARN logs are always emitted regardless of ``verbose``.
    """
    if not manager.is_available():
        logger.warning(
            "translation-skipped",
            extra={"direction": "en_to_ja", "reason": "manager-unavailable"},
        )
        return resp

    import time as _time

    _orig_batch: list[str] = []
    _trans_batch: list[str] = []
    _total_elapsed = 0.0
    _had_japanese_skip: bool = False
    _raw_texts: list[str] = []
    _noop_blocks = 0
    _empty_blocks = 0

    new_content: list[dict[str, Any]] = []
    for block in resp.content:
        # J-7: AnthropicResponse.content may be dict or Pydantic object
        if isinstance(block, dict):
            btype = block.get("type")
            btext = str(block.get("text", ""))
        else:
            btype = getattr(block, "type", None)
            btext = str(getattr(block, "text", "") or "")
        if btype == "text":
            # 収集: ログでモデル原文を表示するため（案B + empty対応）
            _raw_texts.append(btext)
            if btext and btext.strip():
                # 案B: 純日本語のみスキップ、混在EN+JAは翻訳する
                if is_pure_japanese(btext):
                    _had_japanese_skip = True
                    logger.info(
                        "translation-skipped",
                        extra={"direction": "en_to_ja", "reason": "already-japanese", "block_chars": len(btext)},
                    )
                    new_content.append(block)  # type: ignore[arg-type]
                    continue
                _t0 = _time.perf_counter()
                new_text = _translate_chunked(btext, "en_to_ja", manager, chunk_size_chars)
                _elapsed = _time.perf_counter() - _t0
                if new_text != btext:
                    _orig_batch.append(btext)
                    _trans_batch.append(new_text)
                    _total_elapsed += _elapsed
                else:
                    _noop_blocks += 1
                    logger.info(
                        "translation-skipped",
                        extra={"direction": "en_to_ja", "reason": "argos-same-output", "block_chars": len(btext)},
                    )
                if isinstance(block, dict):
                    new_block = dict(block)
                    new_block["text"] = new_text
                else:
                    try:
                        new_block = block.model_copy(update={"text": new_text})  # type: ignore[attr-defined]
                    except Exception:
                        new_block = block
                new_content.append(new_block)  # type: ignore[arg-type]
            else:
                _empty_blocks += 1
                new_content.append(block)  # type: ignore[arg-type]
        elif btype in ("tool_use",):
            # Skip — tool_use structure is protected
            new_content.append(block)  # type: ignore[arg-type]
        else:
            new_content.append(block)  # type: ignore[arg-type]

    if verbose:
        try:
            if _orig_batch:
                _orig_text = "\n".join(_orig_batch)
                _trans_text = "\n".join(_trans_batch)
                log_translation_pair(
                    logger,
                    direction="en_to_ja",
                    original=_orig_text,
                    translated=_trans_text,
                    elapsed_s=_total_elapsed,
                    blocks=len(_orig_batch),
                )
            else:
                # Response was already Japanese or had no translatable text — log for observability
                if _had_japanese_skip:
                    log_translation_pair(
                        logger,
                        direction="en_to_ja",
                        original="(already Japanese, skipped translation)",
                        translated="(no translation needed)",
                        elapsed_s=0.0,
                        blocks=0,
                    )
                else:
                    # モデル原文を表示し、後に (no translatable text...) を追記
                    # 空の場合は (empty) を追記
                    raw_joined = "\n".join(t for t in _raw_texts if t and t.strip())
                    if raw_joined.strip():
                        display_original = f"{raw_joined}\n(no translatable text in response)"
                        # Determine reason for failure visibility
                        if _noop_blocks > 0:
                            reason = "argos-same-output"
                        elif _empty_blocks > 0:
                            reason = "empty-block"
                        else:
                            reason = "no-translatable-block"
                        logger.info(
                            "translation-skipped",
                            extra={
                                "direction": "en_to_ja",
                                "reason": reason,
                                "noop_blocks": _noop_blocks,
                                "empty_blocks": _empty_blocks,
                                "raw_chars": len(raw_joined),
                            },
                        )
                    else:
                        display_original = "(empty)\n(no translatable text in response)"
                        logger.info(
                            "translation-skipped",
                            extra={"direction": "en_to_ja", "reason": "empty-response", "empty_blocks": _empty_blocks},
                        )
                    log_translation_pair(
                        logger,
                        direction="en_to_ja",
                        original=display_original,
                        translated="(no translation needed)",
                        elapsed_s=0.0,
                        blocks=0,
                    )
        except Exception:
            pass

    return resp.model_copy(update={"content": new_content})


# Backwards-compat aliases for design doc pseudocode names
translate_request = translate_anthropic_request_ja_to_en
translate_response = translate_anthropic_response_en_to_ja
