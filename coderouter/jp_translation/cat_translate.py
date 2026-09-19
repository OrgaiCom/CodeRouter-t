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
    """Clean model output: strip wrapping fences and leaked stop tokens (e.g. </s>)."""
    cleaned = strip_stop_tokens(content.strip())
    cleaned = _strip_fences(cleaned)
    cleaned = strip_stop_tokens(cleaned.strip())
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
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self.max_new_tokens = max_new_tokens
        self._client = httpx.Client(timeout=timeout_s, transport=transport)
        self._available = False

    def load(self) -> None:
        """Check that the configured server is reachable without generating text."""
        response = self._client.get(f"{self.endpoint}/models")
        response.raise_for_status()
        self._available = True

    def is_available(self) -> bool:
        return self._available

    def translate(self, text: str, direction: str) -> str:
        if direction not in _DIRECTIONS:
            raise ValueError(f"unsupported CAT-Translate direction: {direction}")
        if not text.strip():
            return text
        source, target = _DIRECTIONS[direction]
        prompt = f"Translate the following {source} text into {target}.\n\n{text}"
        # 4096-char chunks (~2k tokens) need a proportionally large output
        # budget; the fixed default (512) would truncate long chunks.
        # Rough estimate: 1 char ~= 2 tokens worst case, capped at 8192 (model ctx).
        max_tokens = max(self.max_new_tokens, min(8192, len(text) * 2 + 64))
        # Leave room for the prompt itself inside the 8192 context window
        # (conservative 1 char ~= 1 token for the input side).
        max_tokens = min(max_tokens, max(256, 8192 - len(text)))
        response = self._client.post(
            f"{self.endpoint}/chat/completions",
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
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
