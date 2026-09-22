"""English-response directive injection tests (per-request, post JA->EN).

Covers: last_user (default) / system / both, idempotency,
source_role=system skip, tool_result-only skip, OpenAI variants,
TranslationConfig defaults.
"""
from __future__ import annotations

from coderouter.adapters.base import ChatRequest, Message
from coderouter.config.schemas import TranslationConfig
from coderouter.jp_translation.directive import (
    DEFAULT_DIRECTIVE,
    ensure_english_directive_anthropic,
    ensure_english_directive_openai,
)
from coderouter.translation.anthropic import AnthropicMessage, AnthropicRequest

D = DEFAULT_DIRECTIVE
MARKER = "Always respond in English"


def _anth_req(messages, system=None):
    return AnthropicRequest(
        model="m",
        max_tokens=16,
        messages=[AnthropicMessage(role=r, content=c) for r, c in messages],
        system=system,
    )


def test_config_defaults_on_last_user():
    cfg = TranslationConfig()
    assert cfg.enforce_english_response is True
    assert cfg.enforce_english_position == "last_user"
    assert MARKER in cfg.enforce_english_directive
    assert cfg.enforce_english_directive.startswith("**")


def test_anthropic_last_user_str():
    req = _anth_req([("user", "hello")])
    out = ensure_english_directive_anthropic(req, D, "last_user")
    assert out.messages[-1].content.endswith(D)
    assert MARKER in out.messages[-1].content
    # original untouched
    assert req.messages[-1].content == "hello"


def test_anthropic_last_user_list_appends_to_text():
    req = _anth_req([("user", [{"type": "text", "text": "hi"}, {"type": "image", "source": {}}])])
    out = ensure_english_directive_anthropic(req, D, "last_user")
    blocks = out.messages[-1].content
    assert blocks[0]["text"].endswith(D)
    assert blocks[1] == {"type": "image", "source": {}}


def test_anthropic_idempotent():
    req = _anth_req([("user", "hello")])
    once = ensure_english_directive_anthropic(req, D, "last_user")
    twice = ensure_english_directive_anthropic(once, D, "last_user")
    assert twice.messages[-1].content.count(MARKER) == 1


def test_anthropic_skips_system_reminder_turn():
    req = AnthropicRequest(
        model="m",
        max_tokens=16,
        messages=[
            AnthropicMessage(role="user", content="real question"),
            AnthropicMessage(role="user", content="<system-reminder>foo</system-reminder>", source_role="system"),
        ],
        system=None,
    )
    out = ensure_english_directive_anthropic(req, D, "last_user")
    # Genuine user turn gets the directive; reminder turn untouched.
    assert MARKER in out.messages[0].content
    assert MARKER not in out.messages[1].content


def test_anthropic_skips_tool_result_only():
    req = _anth_req(
        [
            ("user", "question"),
            ("assistant", [{"type": "text", "text": "ans"}]),
            ("user", [{"type": "tool_result", "tool_use_id": "t", "content": "out"}]),
        ]
    )
    out = ensure_english_directive_anthropic(req, D, "last_user")
    # Falls back to the earlier genuine user turn.
    assert MARKER in out.messages[0].content
    assert out.messages[2].content == [{"type": "tool_result", "tool_use_id": "t", "content": "out"}]


def test_anthropic_system_positions():
    req = _anth_req([("user", "hello")], system=None)
    out = ensure_english_directive_anthropic(req, D, "system")
    assert out.system == D
    assert MARKER not in out.messages[-1].content

    req2 = _anth_req([("user", "hello")], system="base")
    out2 = ensure_english_directive_anthropic(req2, D, "system")
    assert out2.system == f"base\n{D}"

    req3 = _anth_req([("user", "hello")], system="base")
    out3 = ensure_english_directive_anthropic(req3, D, "both")
    assert out3.system == f"base\n{D}"
    assert MARKER in out3.messages[-1].content


def test_anthropic_system_list_form():
    req = _anth_req(
        [("user", "hello")],
        system=[{"type": "text", "text": "sys"}],
    )
    out = ensure_english_directive_anthropic(req, D, "system")
    assert out.system[0]["text"] == f"sys\n{D}"


def _chat_req(messages):
    return ChatRequest(
        model="m",
        messages=[Message(role=r, content=c) for r, c in messages],
    )


def test_openai_last_user_str_and_idempotent():
    req = _chat_req([("user", "hello")])
    out = ensure_english_directive_openai(req, D, "last_user")
    assert out.messages[-1].content.endswith(D)
    twice = ensure_english_directive_openai(out, D, "last_user")
    assert twice.messages[-1].content.count(MARKER) == 1


def test_openai_system_prepend_when_absent():
    req = _chat_req([("user", "hello")])
    out = ensure_english_directive_openai(req, D, "system")
    assert out.messages[0].role == "system"
    assert out.messages[0].content == D


def test_openai_last_user_list_and_tool_skip():
    req = _chat_req(
        [
            ("user", "question"),
            ("assistant", "ans"),
            ("user", [{"type": "text", "text": ""}]),
        ]
    )
    out = ensure_english_directive_openai(req, D, "last_user")
    # Empty-text turn has no usable text -> falls back to earlier user turn.
    assert MARKER in out.messages[0].content
