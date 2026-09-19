from __future__ import annotations

import httpx
import pytest

from coderouter.jp_translation.cat_translate import (
    CatTranslateBackend,
    _clean_translated_text,
    strip_stop_tokens,
)
from coderouter.jp_translation.translator import (
    translate_anthropic_request_ja_to_en,
    translate_anthropic_response_en_to_ja,
)
from coderouter.translation.anthropic import AnthropicRequest, AnthropicResponse


def test_strip_stop_tokens_single_and_multiple() -> None:
    # Trailing </s>
    assert strip_stop_tokens("こんにちは！</s>") == "こんにちは！"
    assert strip_stop_tokens("こんにちは！ </s>") == "こんにちは！"
    assert strip_stop_tokens("こんにちは！\n</s>\n") == "こんにちは！"
    assert strip_stop_tokens("こんにちは！</s></s>") == "こんにちは！"
    assert strip_stop_tokens("こんにちは！ </s> </s> ") == "こんにちは！"

    # Other stop tokens
    assert strip_stop_tokens("Hello<|im_end|>") == "Hello"
    assert strip_stop_tokens("Hello<|endoftext|>") == "Hello"
    assert strip_stop_tokens("Hello<|eot_id|>") == "Hello"

    # Leading BOS
    assert strip_stop_tokens("<s>こんにちは！") == "こんにちは！"
    assert strip_stop_tokens("<s>こんにちは！</s>") == "こんにちは！"

    # Mid-sentence markers preserved
    assert strip_stop_tokens("これは<s>取り消し</s>です") == "これは<s>取り消し</s>です"

    # Empty / whitespace
    assert strip_stop_tokens("") == ""
    assert strip_stop_tokens("   ") == "   "


def test_clean_translated_text_with_fences_and_stop_tokens() -> None:
    # </s> at end without fences
    assert _clean_translated_text("翻訳結果です。</s>") == "翻訳結果です。"

    # </s> inside fences
    fenced_inside = "```\n翻訳結果です。</s>\n```"
    assert _clean_translated_text(fenced_inside) == "翻訳結果です。"

    # </s> outside fences
    fenced_outside = "```\n翻訳結果です。\n```</s>"
    assert _clean_translated_text(fenced_outside) == "翻訳結果です。"

    # </s> both inside and outside fences
    fenced_both = "```ja\n翻訳結果です。</s>\n```</s>"
    assert _clean_translated_text(fenced_both) == "翻訳結果です。"


def test_cat_translate_strips_trailing_eos_and_sends_stop_param() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "ご興味のあるCodeRouterプロジェクトに関するどんな課題でも、ぜひご相談ください。 具体的な機能の実装要件、不具合の修正、またはドキュメントの充実などがございましたら、お知らせください！</s>"
                        }
                    }
                ]
            },
            request=request,
        )

    backend = CatTranslateBackend(
        endpoint="http://cat.test/v1",
        model="CAT-Translate-1.4b",
        transport=httpx.MockTransport(handler),
    )

    result = backend.translate(
        "I'm ready to help with any tasks related to the CodeRouter project. Please let me know if you have a specific feature to implement, a bug to fix, or documentation to refine!",
        "en_to_ja",
    )

    expected = "ご興味のあるCodeRouterプロジェクトに関するどんな課題でも、ぜひご相談ください。 具体的な機能の実装要件、不具合の修正、またはドキュメントの充実などがございましたら、お知らせください！"
    assert result == expected

    # Verify stop parameter in request payload
    import json as _json

    body = _json.loads(requests[0].read().decode("utf-8"))
    assert "stop" in body
    assert "</s>" in body["stop"]


def test_translate_anthropic_response_strips_stop_token() -> None:
    class FakeManager:
        _backend = "mock"

        def is_available(self) -> bool:
            return True

        def translate_en_to_ja(self, text: str) -> str:
            return f"{text}の日本語訳</s>"

        def translate_ja_to_en(self, text: str) -> str:
            return f"{text} in English</s>"

    manager = FakeManager()
    resp = AnthropicResponse.model_validate(
        {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello world"}],
            "model": "claude-test",
            "usage": {"input_tokens": 10, "output_tokens": 10},
        }
    )

    result = translate_anthropic_response_en_to_ja(resp, manager, verbose=True)  # type: ignore[arg-type]
    block = result.content[0]
    # Should not end with </s>
    assert block["text"] == "Hello worldの日本語訳"


def test_translate_anthropic_request_strips_stop_token() -> None:
    class FakeManager:
        _backend = "mock"

        def is_available(self) -> bool:
            return True

        def translate_ja_to_en(self, text: str) -> str:
            return f"English translation of {text}</s>"

    manager = FakeManager()
    req = AnthropicRequest.model_validate(
        {
            "model": "claude-test",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "こんにちは世界"}],
        }
    )

    result = translate_anthropic_request_ja_to_en(req, manager, verbose=True)  # type: ignore[arg-type]
    assert result.messages[0].content == "English translation of こんにちは世界"
