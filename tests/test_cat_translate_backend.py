from __future__ import annotations

import httpx
import pytest

from coderouter.config.schemas import TranslationConfig
from coderouter.jp_translation.cat_translate import CatTranslateBackend
from coderouter.jp_translation.manager import TranslatorManager


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
