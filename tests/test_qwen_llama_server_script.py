"""Regression checks for the Windows Qwen3.6 llama.cpp launcher."""

from __future__ import annotations

from pathlib import Path


SCRIPT = Path(__file__).resolve().parent.parent / "llamaQwenServe.bat"


def test_qwen_launcher_uses_the_requested_safe_local_defaults() -> None:
    """The launcher must keep the 35B server private and reproducible."""
    text = SCRIPT.read_text(encoding="utf-8")

    for expected in (
        "--host 127.0.0.1",
        "-ngl %QWEN_N_GPU_LAYERS%",
        "-ncmoe %QWEN_N_CPU_MOE%",
        "-c %QWEN_CTX_SIZE%",
        "-ctk q4_0",
        "-ctv q4_0",
        "--reasoning off",
    ):
        assert expected in text


def test_qwen_launcher_exposes_the_required_overrides() -> None:
    """VRAM tuning must not require editing the checked-in script."""
    text = SCRIPT.read_text(encoding="utf-8")

    for variable in (
        "QWEN_MODEL",
        "QWEN_PORT",
        "QWEN_CTX_SIZE",
        "QWEN_N_GPU_LAYERS",
        "QWEN_N_CPU_MOE",
    ):
        assert f"if not defined {variable}" in text
