"""CAT-Translate client for an OpenAI-compatible llama-server."""

from __future__ import annotations

import json
from typing import Any

import httpx

_DIRECTIONS = {
    "ja_to_en": ("Japanese", "English"),
    "en_to_ja": ("English", "Japanese"),
}

_STOP_TOKENS: tuple[str, ...] = (
    "</s>",
    "<|im_end|>",
    "<|endoftext|>",
    "<|eot_id|>",
)

_AUTO_SYSTEM_PROMPT = (
    "If the user prompt is English, translate it into Japanese. "
    "If the user prompt is Japanese, translate it into English. "
    "Output translation only. Do not include the instruction, preamble, or explanations. "
    "Keep __CR_PROTECTED_<n>__ placeholders verbatim."
)

_DIRECTED_SYSTEM_PROMPTS = {
    "ja_to_en": (
        "英語に翻訳してください。"
        "翻訳結果のみを出力し、指示文や前置き、説明は含めないでください。"
        "__CR_PROTECTED_<n>__プレースホルダーはそのまま保持してください。"
    ),
    "en_to_ja": (
        "Translate to Japanese. "
        "Output translation only. Do not include the instruction, preamble, or explanations. "
        "Keep __CR_PROTECTED_<n>__ placeholders verbatim."
    ),
}

_PROMPT_MODES = ("structured", "official", "auto", "directed")


def _build_prompt(
    direction: str,
    text: str,
    strong: bool = False,
    mode: str = "official",
) -> tuple[str | None, str]:
    """Build (system, user) prompt for ``direction``.

    All modes use a single user message with no system role:
    CAT-Translate-1.4b was trained on the official single-user format and
    mishandles the ``system`` role (it echoes/translates the system text
    instead of the user text — observed as the system prompt leaking into
    the translation output).

    Modes (``translation.cat_prompt_mode``):
    - ``official`` (default): legacy single user message, no system role.
    - ``directed``: instruction in the source language
      (JA→EN: Japanese, EN→JA: English) + blank line + raw text.
      ``strong`` is ignored.
    - ``auto``: auto-detect instruction + blank line + raw text.
      ``direction``/``strong`` are ignored.
    - ``structured``: instruction + output-only constraint (normal) or
      bold instruction + delimiters + placeholder directive (strong retry).
    """
    if mode not in _PROMPT_MODES:
        raise ValueError(f"unsupported CAT prompt mode: {mode}")
    if mode == "auto":
        return None, f"{_AUTO_SYSTEM_PROMPT}\n\n{text}"
    if mode == "directed":
        if direction not in _DIRECTED_SYSTEM_PROMPTS:
            raise ValueError(f"unsupported CAT-Translate direction: {direction}")
        return None, f"{_DIRECTED_SYSTEM_PROMPTS[direction]}\n\n{text}"
    source, target = _DIRECTIONS[direction]
    if mode == "official":
        return None, f"Translate the following {source} text into {target}.\n\n{text}"
    if not strong:
        return None, (
            f"Translate the following {source} text into {target}.\n"
            "Output translation only. Do not include the instruction, preamble, or explanations.\n\n"
            f"{text}"
        )
    return None, (
        f"**Translate the following {source} text into {target}.**\n\n"
        "Output translation only, no explanations. "
        "Keep __CR_PROTECTED_<n>__ placeholders verbatim.\n\n"
        f"---\n{text}\n---"
    )


def strip_stop_tokens(text: str) -> str:
    """Strip trailing EOS tokens (and leading BOS tokens) from translated text.

    LLM-based translation models and SentencePiece tokenizers frequently leak
    trailing special tokens such as ``</s>`` or ``<|im_end|>``.
    """
    if not text:
        return text

    changed = True
    result = text
    while changed:
        changed = False
        stripped = result.rstrip()
        for tok in _STOP_TOKENS:
            if stripped.endswith(tok):
                result = stripped[: -len(tok)].rstrip()
                changed = True
                break

    result_l = result.lstrip()
    if result_l.startswith("<s>"):
        result = result_l[len("<s>") :].lstrip()

    return result


import re as _re

# Instruction-echo preamble: model repeats the JA rendering of
# "Translate the following English text into Japanese." instead of translating.
# Only stripped from the head (max 2 lines) to avoid touching legitimate body text.
_PREAMBLE_LINE_RES = (
    _re.compile(r"^\s*以下の英文を日本語に翻訳してください[。．.]?\s*$"),
    _re.compile(r"^\s*以下の英語.+を日本語に翻訳.*$"),
    _re.compile(r"^\s*以下を日本語に翻訳.*$"),
    _re.compile(r"^\s*Translate the following English text into Japanese\.?\s*$", _re.IGNORECASE),
    _re.compile(r"^\s*(Japanese\s+)?Translation\s*:\s*$", _re.IGNORECASE),
)

_PREAMBLE_PREFIX_RES = (
    _re.compile(r"^\s*以下の英文を日本語に翻訳してください[。．.]?\s*"),
    _re.compile(r"^\s*Translate the following English text into Japanese\.?\s*", _re.IGNORECASE),
)


def strip_preamble(text: str) -> str:
    """Strip leading instruction-echo lines (max 2) from translated text."""
    if not text:
        return text
    lines = text.splitlines()
    stripped_count = 0
    while lines and stripped_count < 2:
        first = lines[0]
        if not first.strip():
            lines.pop(0)
            continue
        if any(p.match(first) for p in _PREAMBLE_LINE_RES):
            lines.pop(0)
            stripped_count += 1
            continue
        # Same-line prefix: "以下の英文を...。本文" → keep body part
        new_first = first
        for p in _PREAMBLE_PREFIX_RES:
            new_first = p.sub("", new_first, count=1)
        if new_first != first:
            lines[0] = new_first
            stripped_count += 1
        break
    result = "\n".join(lines).lstrip()
    # Stripped everything → return empty so caller can fallback
    return result


def _strip_fences(content: str) -> str:
    """Remove a wrapping ``` fence if the model echoed one around the translation."""
    stripped = content.strip()
    if stripped.startswith("```") and stripped.endswith("```") and len(stripped) > 6:
        lines = stripped.splitlines()
        # Drop opening fence (``` or ```lang) and closing fence.
        body = "\n".join(lines[1:-1]).strip()
        if body:
            return body
    return stripped


def _clean_translated_text(content: str) -> str:
    """Clean model output: strip wrapping fences, leaked stop tokens, and instruction echo."""
    cleaned = strip_stop_tokens(content.strip())
    cleaned = _strip_fences(cleaned)
    cleaned = strip_stop_tokens(cleaned.strip())
    cleaned = strip_preamble(cleaned.strip())
    return cleaned


class CatTranslateBackend:
    """Small, synchronous client; model inference stays outside CodeRouter."""

    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:8080/v1",
        model: str = "CAT-Translate-1.4b",
        timeout_s: float = 30.0,
        max_new_tokens: int = 512,
        *,
        transport: httpx.BaseTransport | None = None,
        prompt_mode: str = "official",
    ) -> None:
        if prompt_mode not in _PROMPT_MODES:
            raise ValueError(f"unsupported CAT prompt mode: {prompt_mode}")
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self.max_new_tokens = max_new_tokens
        self._prompt_mode = prompt_mode
        self._client = httpx.Client(timeout=timeout_s, transport=transport)
        self._available = False

    def load(self) -> None:
        """Check that the configured server is reachable without generating text."""
        response = self._client.get(f"{self.endpoint}/models")
        response.raise_for_status()
        self._available = True

    def is_available(self) -> bool:
        return self._available

    def translate(
        self,
        text: str,
        direction: str,
        *,
        strong: bool = False,
        mode: str | None = None,
    ) -> str:
        if direction not in _DIRECTIONS:
            raise ValueError(f"unsupported CAT-Translate direction: {direction}")
        if not text.strip():
            return text
        effective_mode = mode or self._prompt_mode
        system, prompt = _build_prompt(direction, text, strong, effective_mode)
        if system is None:
            messages = [{"role": "user", "content": prompt}]
        else:
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ]
        # 4096-char chunks (~2k tokens) need a proportionally large output
        # budget; the fixed default (512) would truncate long chunks.
        # Rough estimate: 1 char ~= 2 tokens worst case, capped at 8192 (model ctx).
        # Timeout is intentionally NOT extended on retries (operator decision).
        max_tokens = max(self.max_new_tokens, min(8192, len(text) * 2 + 64))
        # Leave room for the prompt itself inside the 8192 context window
        # (conservative 1 char ~= 1 token for the input side).
        max_tokens = min(max_tokens, max(256, 8192 - len(text)))
        response = self._client.post(
            f"{self.endpoint}/chat/completions",
            json={
                "model": self.model,
                "messages": messages,
                "temperature": 0.0,
                "top_p": 1.0,
                "max_tokens": max_tokens,
                "stream": False,
                "stop": list(_STOP_TOKENS),
            },
        )
        response.raise_for_status()
        try:
            payload: dict[str, Any] = response.json()
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("CAT-Translate returned an invalid response") from exc
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("CAT-Translate returned empty translation")
        return _clean_translated_text(content.strip())

    def close(self) -> None:
        self._available = False
        self._client.close()
