#!/usr/bin/env python3
"""Download CAT-Translate GGUF for llama-server without bundling it in CodeRouter.

Default matches ``llamaServe.bat``: the public quantized GGUF
``mradermacher/CAT-Translate-1.4b-GGUF / CAT-Translate-1.4b.Q4_K_M.gguf``
(~931MB) into ``models/cat-translate/``.

The original CyberAgent Safetensors (``cyberagent/CAT-Translate-1.4b``) can NOT
be served by llama-server directly, so GGUF is the default. Use --repo/--filename
to override.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_REPO = "mradermacher/CAT-Translate-1.4b-GGUF"
DEFAULT_FILENAME = "CAT-Translate-1.4b.Q4_K_M.gguf"
DEFAULT_DEST = Path("models/cat-translate")


def _download_via_hf_cli(repo: str, filename: str, dest: Path) -> int:
    hf = shutil.which("hf") or shutil.which("huggingface-cli")
    if hf is None:
        return -1
    dest.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")
    command = [hf, "download", repo, filename, "--local-dir", str(dest)]
    completed = subprocess.run(command, check=False)
    return completed.returncode


def _download_via_hub_api(repo: str, filename: str, dest: Path) -> int:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print(
            "hf / huggingface-cli も huggingface_hub もありません。"
            '先に pip install --upgrade "huggingface_hub[hf_transfer]" を実行してください。',
            file=sys.stderr,
        )
        return 2
    dest.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")
    path = hf_hub_download(repo_id=repo, filename=filename, local_dir=str(dest))
    print(f"保存: {path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Download CAT-Translate GGUF for llama-server")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--filename", default=DEFAULT_FILENAME)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    args = parser.parse_args()

    existing = args.dest / Path(args.filename).name
    if existing.exists():
        print(f"既存のGGUFを使用します: {existing}")
        return 0

    rc = _download_via_hf_cli(args.repo, args.filename, args.dest)
    if rc == -1:
        rc = _download_via_hub_api(args.repo, args.filename, args.dest)
    if rc == 0:
        print(f"CAT-Translate GGUF を {args.dest} に配置しました。")
        print("起動例: llamaServe.bat (llama-server --host 127.0.0.1 --port 8080 -c 8192)")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
