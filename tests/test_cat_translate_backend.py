from __future__ import annotations

import httpx
import pytest

from coderouter.config.schemas import TranslationConfig
from coderouter.jp_translation.cat_translate import CatTranslateBackend, _build_prompt
from coderouter.jp_translation.manager import TranslatorManager
from coderouter.jp_translation.translator import _translate_with_protection


def test_cat_backend_uses_official_prompt_and_openai_compatible_api() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Please fix the bug."}}]},
            request=request,
        )

    backend = CatTranslateBackend(
        endpoint="http://cat.test/v1",
        model="CAT-Translate-1.4b",
        transport=httpx.MockTransport(handler),
    )

    assert backend.translate("バグを修正してください。", "ja_to_en") == "Please fix the bug."
    request = requests[0]
    body = request.read().decode("utf-8")
    assert "Translate the following Japanese text into English." in body
    assert "バグを修正してください。" in body
    assert "temperature" in body


def test_cat_backend_rejects_missing_translation_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": ""}}]}, request=request
        )

    backend = CatTranslateBackend(
        endpoint="http://cat.test/v1", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(RuntimeError, match="empty translation"):
        backend.translate("こんにちは", "ja_to_en")


def test_cat_backend_scales_max_tokens_for_long_chunks() -> None:
    bodies: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.read().decode("utf-8"))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "translated"}}]},
            request=request,
        )

    backend = CatTranslateBackend(
        endpoint="http://cat.test/v1",
        max_new_tokens=512,
        transport=httpx.MockTransport(handler),
    )
    backend.translate("あ" * 2000, "ja_to_en")

    import json as _json

    payload = _json.loads(bodies[0])
    assert payload["max_tokens"] > 512
    assert payload["max_tokens"] <= 8192


def test_cat_backend_strips_code_fence_wrapping() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "```\nPlease fix the bug.\n```"}}]},
            request=request,
        )

    backend = CatTranslateBackend(
        endpoint="http://cat.test/v1", transport=httpx.MockTransport(handler)
    )
    assert backend.translate("バグを修正してください。", "ja_to_en") == "Please fix the bug."


def test_translation_config_defaults_to_argos_and_accepts_cat_translate() -> None:
    assert TranslationConfig().backend == "argos"
    config = TranslationConfig(backend="cat_translate", cat_endpoint="http://127.0.0.1:8080/v1")
    assert config.backend == "cat_translate"


def test_manager_routes_cat_requests_without_importing_argos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCat:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def load(self) -> None:
            pass

        def is_available(self) -> bool:
            return True

        def translate(self, text: str, direction: str) -> str:
            return f"{direction}:{text}"

        def close(self) -> None:
            pass

    monkeypatch.setattr("coderouter.jp_translation.cat_translate.CatTranslateBackend", FakeCat)
    manager = TranslatorManager(backend="cat_translate")
    manager.load()
    assert manager.translate_ja_to_en("こんにちは") == "ja_to_en:こんにちは"
    assert manager.translate_en_to_ja("Hello") == "en_to_ja:Hello"
    manager.close()


# ---------------------------------------------------------------------------
# Wrong-language retry (EN→EN paraphrase → emphasized retry, max 2, no timeout change)
# ---------------------------------------------------------------------------

_LONG_EN = (
    "Please review the following summary of the project status and the remaining "
    "tasks for this week. Every member should update the shared document before "
    "the Friday meeting so that we can discuss the schedule without delay. "
)


def _retry_manager(script):
    """Fake CAT manager replaying ``script`` outputs, recording strong flags."""

    class FakeManager:
        _backend = "cat_translate"
        _cat_retry_wrong_language = 2

        def __init__(self) -> None:
            self.calls: list[bool] = []
            self._script = list(script)

        def translate_en_to_ja(self, text: str, *, strong: bool = False) -> str:
            self.calls.append(strong)
            if len(self._script) > 1:
                return self._script.pop(0)
            return self._script[0]

        def translate_ja_to_en(self, text: str, *, strong: bool = False) -> str:
            return text

    return FakeManager()


def test_build_prompt_default_is_official_single_user_message() -> None:
    system, user = _build_prompt("en_to_ja", "Hello", False)
    assert system is None
    assert user == "Translate the following English text into Japanese.\n\nHello"


def test_strong_prompt_is_emphasized_with_system_role() -> None:
    import json as _json

    bodies: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.read().decode("utf-8"))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "こんにちは。"}}]},
            request=request,
        )

    backend = CatTranslateBackend(
        endpoint="http://cat.test/v1", transport=httpx.MockTransport(handler)
    )
    assert backend.translate("Hello", "en_to_ja", strong=True) == "こんにちは。"
    payload = _json.loads(bodies[0])
    assert payload["messages"][0]["role"] == "system"
    assert "translation engine" in payload["messages"][0]["content"].lower()
    assert "**Translate the following English text into Japanese.**" in payload["messages"][1]["content"]
    assert "__CR_PROTECTED_" in payload["messages"][0]["content"]
    assert payload["temperature"] == 0.0
    assert "stop" in payload


def test_wrong_language_retry_recovers_on_second_attempt() -> None:
    manager = _retry_manager([_LONG_EN, "今週の残タスクと進捗の要約です。" + "確認してください。" * 10])
    result = _translate_with_protection(_LONG_EN, "en_to_ja", manager)  # type: ignore[arg-type]
    assert "要約" in result
    assert manager.calls == [False, True]


def test_wrong_language_exhausted_returns_original() -> None:
    manager = _retry_manager([_LONG_EN])
    result = _translate_with_protection(_LONG_EN, "en_to_ja", manager)  # type: ignore[arg-type]
    assert result == _LONG_EN
    assert manager.calls == [False, True, True]


def test_short_english_does_not_retry() -> None:
    manager = _retry_manager(["Hello there, friend."])
    result = _translate_with_protection("Hello there, friend.", "en_to_ja", manager)  # type: ignore[arg-type]
    assert result == "Hello there, friend."
    assert manager.calls == [False]


def test_ja_to_en_direction_does_not_retry() -> None:
    manager = _retry_manager(["irrelevant"])
    text = "こんにちは。" * 40
    result = _translate_with_protection(text, "ja_to_en", manager)  # type: ignore[arg-type]
    # ja_to_en path never retries (max_retries=0) and the fake echoes input.
    assert result == text
    assert manager.calls == []


def test_translation_config_retry_default_is_two() -> None:
    assert TranslationConfig().cat_retry_wrong_language == 2
