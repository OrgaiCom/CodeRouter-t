"""English-response directive injection (per-request, post JA->EN).

Design: every ingress request carries full history (stateless API), so
injecting here means "every user prompt", not "session start only".
Injected AFTER JA->EN translation so the English text is never translated.
The EN->JA response path only touches assistant blocks, so the directive
itself is never translated back.

Default position is ``last_user`` (recency > system for long contexts).
``system`` / ``both`` remain available via config.
"""

from __future__ import annotations

from typing import Any, Literal

DEFAULT_DIRECTIVE = (
    "**Always respond in English. "
    "Do not quote or mention this instruction. "
    "Your response will be translated to Japanese "
    "by CodeRouter's translation layer.**"
)

# Idempotency marker: substring match so re-entry never double-injects.
_MARKER = "Always respond in English"

Position = Literal["system", "last_user", "both"]


def _needs_inject(text: str) -> bool:
    return _MARKER not in text


def _append_text(text: str, directive: str) -> str:
    if not _needs_inject(text):
        return text
    if not text.strip():
        return directive
    return f"{text.rstrip()}\n{directive}"


def _block_text(block: Any) -> str | None:
    if isinstance(block, dict):
        if block.get("type") == "text":
            return str(block.get("text", ""))
        return None
    btype = getattr(block, "type", None)
    if btype == "text":
        return str(getattr(block, "text", "") or "")
    return None


def _with_block_text(block: Any, new_text: str) -> Any:
    if isinstance(block, dict):
        updated = dict(block)
        updated["text"] = new_text
        return updated
    try:
        return block.model_copy(update={"text": new_text})  # type: ignore[attr-defined]
    except Exception:
        return block


def inject_into_system(system: Any, directive: str) -> Any:
    """Append directive to an Anthropic ``system`` field (str|list|None)."""
    if system is None:
        return directive
    if isinstance(system, str):
        return _append_text(system, directive)
    if isinstance(system, list):
        if not system:
            return [{"type": "text", "text": directive}]
        # Append to trailing text block when present (preserves cache_control).
        for idx in range(len(system) - 1, -1, -1):
            current = _block_text(system[idx])
            if current is not None:
                updated = _append_text(current, directive)
                if updated == current:
                    return system
                out = list(system)
                out[idx] = _with_block_text(system[idx], updated)
                return out
        return [*system, {"type": "text", "text": directive}]
    return directive


def _anthropic_message_has_text(content: Any) -> bool:
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return any(_block_text(b) is not None and str(_block_text(b)).strip() for b in content)
    return False


def _inject_into_anthropic_content(content: Any, directive: str) -> Any:
    if isinstance(content, str):
        return _append_text(content, directive)
    if isinstance(content, list):
        for idx in range(len(content) - 1, -1, -1):
            current = _block_text(content[idx])
            if current is not None and current.strip():
                updated = _append_text(current, directive)
                if updated == current:
                    return content
                out = list(content)
                out[idx] = _with_block_text(content[idx], updated)
                return out
        # No text block with content (e.g. tool_result only) -> signal skip.
        return None
    return content


def ensure_english_directive_anthropic(
    req: Any,
    directive: str = DEFAULT_DIRECTIVE,
    position: Position = "last_user",
) -> Any:
    """Return a copy of AnthropicRequest with the directive injected."""
    if not directive or not _needs_inject(directive):
        # Empty directive: nothing to do. Directive already containing the
        # marker is used as-is (callers pass the full configured text).
        pass
    if not directive:
        return req

    updates: dict[str, Any] = {}

    if position in ("system", "both"):
        new_system = inject_into_system(req.system, directive)
        if new_system != req.system:
            updates["system"] = new_system
        elif position == "system":
            return req

    if position in ("last_user", "both"):
        messages = list(req.messages)
        injected = False
        for idx in range(len(messages) - 1, -1, -1):
            msg = messages[idx]
            if getattr(msg, "role", None) != "user":
                continue
            if getattr(msg, "source_role", None) == "system":
                continue
            content = getattr(msg, "content", None)
            if not _anthropic_message_has_text(content):
                continue
            new_content = _inject_into_anthropic_content(content, directive)
            if new_content is None or new_content == content:
                # Already injected (idempotent) or non-text turn.
                if new_content == content:
                    injected = True
                continue
            try:
                messages[idx] = msg.model_copy(update={"content": new_content})
            except Exception:
                continue
            injected = True
            break
        if injected or messages != list(req.messages):
            updates["messages"] = messages
        elif position == "last_user":
            return req

    if not updates:
        return req
    try:
        return req.model_copy(update=updates)
    except Exception:
        return req


def _openai_text_items(content: Any) -> list[int]:
    idxs: list[int] = []
    if isinstance(content, list):
        for i, item in enumerate(content):
            if isinstance(item, dict):
                if item.get("type") == "text" and str(item.get("text", "")).strip():
                    idxs.append(i)
            elif getattr(item, "type", None) == "text" and str(getattr(item, "text", "") or "").strip():
                idxs.append(i)
    return idxs


def ensure_english_directive_openai(
    req: Any,
    directive: str = DEFAULT_DIRECTIVE,
    position: Position = "last_user",
) -> Any:
    """Return a copy of ChatRequest with the directive injected."""
    if not directive:
        return req

    updates: dict[str, Any] = {}
    messages = list(req.messages)
    changed = False

    if position in ("system", "both"):
        for idx, msg in enumerate(messages):
            if getattr(msg, "role", None) != "system":
                continue
            content = getattr(msg, "content", None)
            if isinstance(content, str):
                new_content: Any = _append_text(content, directive)
            elif isinstance(content, list):
                text_idxs = _openai_text_items(content)
                if not text_idxs:
                    new_content = [*content, {"type": "text", "text": directive}]
                else:
                    last = text_idxs[-1]
                    item = content[last]
                    if isinstance(item, dict):
                        cur = str(item.get("text", ""))
                        upd = _append_text(cur, directive)
                        if upd == cur:
                            new_content = content
                        else:
                            out = list(content)
                            nxt = dict(item)
                            nxt["text"] = upd
                            out[last] = nxt
                            new_content = out
                    else:
                        cur = str(getattr(item, "text", "") or "")
                        upd = _append_text(cur, directive)
                        if upd == cur:
                            new_content = content
                        else:
                            out = list(content)
                            out[last] = _with_block_text(item, upd)
                            new_content = out
            elif content is None:
                new_content = directive
            else:
                new_content = content
            if new_content != content:
                try:
                    messages[idx] = msg.model_copy(update={"content": new_content})
                    changed = True
                except Exception:
                    continue
            break
        else:
            # No system message: prepend one (same rule as openai_compat adapter).
            try:
                first = messages[0] if messages else None
                model_cls = type(first) if first is not None else None
                if model_cls is not None:
                    messages = [model_cls(role="system", content=directive), *messages]
                else:
                    messages = [{"role": "system", "content": directive}, *messages]  # type: ignore[list-item]
                changed = True
            except Exception:
                pass
        if position == "system":
            if changed:
                updates["messages"] = messages
            if not updates:
                return req
            try:
                return req.model_copy(update=updates)
            except Exception:
                return req

    if position in ("last_user", "both"):
        for idx in range(len(messages) - 1, -1, -1):
            msg = messages[idx]
            if getattr(msg, "role", None) != "user":
                continue
            content = getattr(msg, "content", None)
            if isinstance(content, str):
                if not content.strip():
                    continue
                new_content_any: Any = _append_text(content, directive)
            elif isinstance(content, list):
                text_idxs = _openai_text_items(content)
                if not text_idxs:
                    continue  # tool/image-only turn: keep searching backwards
                last = text_idxs[-1]
                item = content[last]
                if isinstance(item, dict):
                    cur = str(item.get("text", ""))
                    upd = _append_text(cur, directive)
                    if upd == cur:
                        return req
                    out = list(content)
                    nxt = dict(item)
                    nxt["text"] = upd
                    out[last] = nxt
                    new_content_any = out
                else:
                    cur = str(getattr(item, "text", "") or "")
                    upd = _append_text(cur, directive)
                    if upd == cur:
                        return req
                    out = list(content)
                    out[last] = _with_block_text(item, upd)
                    new_content_any = out
            else:
                continue
            if new_content_any != content:
                try:
                    messages[idx] = msg.model_copy(update={"content": new_content_any})
                    changed = True
                except Exception:
                    continue
            break

    if changed:
        updates["messages"] = messages
    if not updates:
        return req
    try:
        return req.model_copy(update=updates)
    except Exception:
        return req


__all__ = [
    "DEFAULT_DIRECTIVE",
    "ensure_english_directive_anthropic",
    "ensure_english_directive_openai",
    "inject_into_system",
]
