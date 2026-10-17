"""Tests for ``${VAR}`` / ``$VAR`` expansion in providers.yaml.

Covers the ``_expand_env_vars`` helper (Task 1) and its integration into
``load_config`` for ``translation.cat_endpoint`` (Task 2), including the
security boundary: command-execution fields (``restart_command`` etc.)
are deliberately NOT expanded, preserving the v2.13.0 code-execution-
vector gating.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from coderouter.config.loader import _expand_env_vars, load_config
from coderouter.config.schemas import CodeRouterConfig


# ---------------------------------------------------------------------------
# Task 1: _expand_env_vars unit tests
# ---------------------------------------------------------------------------

def test_expand_defined_braced_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRANSLATE_PORT", "9999")
    assert _expand_env_vars("http://127.0.0.1:${TRANSLATE_PORT}/v1") == "http://127.0.0.1:9999/v1"


def test_expand_defined_bare_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_HOST", "example.com")
    assert _expand_env_vars("https://$MY_HOST/api") == "https://example.com/api"


def test_undefined_var_left_intact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UNSET_VAR", raising=False)
    assert _expand_env_vars("${UNSET_VAR}") == "${UNSET_VAR}"


def test_undefined_var_in_url_left_intact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRANSLATE_PORT", raising=False)
    result = _expand_env_vars("http://127.0.0.1:${TRANSLATE_PORT}/v1")
    assert result == "http://127.0.0.1:${TRANSLATE_PORT}/v1"


def test_mixed_defined_and_undefined(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRANSLATE_PORT", "8765")
    monkeypatch.delenv("MISSING", raising=False)
    result = _expand_env_vars("${TRANSLATE_PORT}/${MISSING}")
    assert result == "8765/${MISSING}"


def test_no_dollar_sign_unchanged() -> None:
    assert _expand_env_vars("http://127.0.0.1:8765/v1") == "http://127.0.0.1:8765/v1"


def test_non_string_passthrough() -> None:
    assert _expand_env_vars(123) == 123  # type: ignore[arg-type]
    assert _expand_env_vars(None) is None  # type: ignore[arg-type]
    assert _expand_env_vars(True) is True  # type: ignore[arg-type]


def test_dollar_digit_not_expanded(monkeypatch: pytest.MonkeyPatch) -> None:
    """``$5`` is not a valid env var name and must pass through untouched."""
    monkeypatch.setenv("5", "nope")
    assert _expand_env_vars("price is $5") == "price is $5"


def test_multiple_vars_in_one_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("TRANSLATE_PORT", "8765")
    assert _expand_env_vars("http://$HOST:${TRANSLATE_PORT}/v1") == "http://127.0.0.1:8765/v1"


# ---------------------------------------------------------------------------
# Task 2: load_config integration
# ---------------------------------------------------------------------------

def _write_minimal_yaml(path: Path, translation: dict | None = None) -> None:
    """Write a minimal valid providers.yaml with optional translation block."""
    doc: dict = {
        "default_profile": "default",
        "providers": [
            {
                "name": "local",
                "base_url": "http://localhost:8080/v1",
                "model": "m",
            }
        ],
        "profiles": [{"name": "default", "providers": ["local"]}],
    }
    if translation is not None:
        doc["translation"] = translation
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")


def test_load_config_expands_cat_endpoint_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``${TRANSLATE_PORT}`` in cat_endpoint is expanded at load time."""
    cfg_file = tmp_path / "providers.yaml"
    _write_minimal_yaml(
        cfg_file,
        translation={
            "backend": "cat_translate",
            "cat_endpoint": "http://127.0.0.1:${TRANSLATE_PORT}/v1",
        },
    )
    monkeypatch.setenv("TRANSLATE_PORT", "9999")
    cfg = load_config(cfg_file)
    assert cfg.translation.cat_endpoint == "http://127.0.0.1:9999/v1"


def test_load_config_leaves_undefined_cat_endpoint_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Undefined ``${TRANSLATE_PORT}`` survives — the operator sees their typo,
    not an opaque ``http://127.0.0.1:/v1``."""
    cfg_file = tmp_path / "providers.yaml"
    _write_minimal_yaml(
        cfg_file,
        translation={
            "backend": "cat_translate",
            "cat_endpoint": "http://127.0.0.1:${TRANSLATE_PORT}/v1",
        },
    )
    monkeypatch.delenv("TRANSLATE_PORT", raising=False)
    cfg = load_config(cfg_file)
    assert cfg.translation.cat_endpoint == "http://127.0.0.1:${TRANSLATE_PORT}/v1"


def test_load_config_no_expansion_when_plain_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plain URL with no ``$`` is not touched."""
    cfg_file = tmp_path / "providers.yaml"
    _write_minimal_yaml(
        cfg_file,
        translation={
            "backend": "cat_translate",
            "cat_endpoint": "http://127.0.0.1:8765/v1",
        },
    )
    monkeypatch.setenv("TRANSLATE_PORT", "9999")
    cfg = load_config(cfg_file)
    assert cfg.translation.cat_endpoint == "http://127.0.0.1:8765/v1"


def test_load_config_does_not_expand_restart_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Security: command-execution fields are NOT expanded.

    ``restart_command`` names an executable. Expanding ``${VAR}`` there
    would let an env var steer the command, reopening the code-execution
    vector that v2.13.0's CWD-config gating closed. Only cat_endpoint
    is in scope.
    """
    cfg_file = tmp_path / "providers.yaml"
    doc = {
        "default_profile": "default",
        "providers": [
            {
                "name": "local",
                "base_url": "http://localhost:8080/v1",
                "model": "m",
                "restart_command": "${EVIL_CMD} --arg",
            }
        ],
        "profiles": [{"name": "default", "providers": ["local"]}],
    }
    cfg_file.write_text(yaml.safe_dump(doc), encoding="utf-8")
    monkeypatch.setenv("EVIL_CMD", "rm -rf /")
    cfg = load_config(cfg_file)
    # The literal ${EVIL_CMD} survives — not expanded to the env value.
    assert cfg.providers[0].restart_command == "${EVIL_CMD} --arg"


def test_load_config_default_cat_endpoint_is_8765(tmp_path: Path) -> None:
    """When translation block has no cat_endpoint, the schema default
    (8765) applies — confirming the default-value change in Task 3."""
    cfg_file = tmp_path / "providers.yaml"
    _write_minimal_yaml(
        cfg_file,
        translation={"backend": "cat_translate"},
    )
    cfg = load_config(cfg_file)
    assert cfg.translation.cat_endpoint == "http://127.0.0.1:8765/v1"
