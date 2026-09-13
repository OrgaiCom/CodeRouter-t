"""CAT-Translate client for an OpenAI-compatible llama-server."""

from __future__ import annotations

import json
from typing import Any

import httpx

_DIRECTIONS = {
    "ja_to_en": ("Japanese", "English"),
    "en_to_ja": ("English", "Japanese"),
}


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
        response = self._client.post(
            f"{self.endpoint}/chat/completions",
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "top_p": 1.0,
                "max_tokens": self.max_new_tokens,
                "stream": False,
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
        return content.strip()

    def close(self) -> None:
        self._available = False
        self._client.close()
