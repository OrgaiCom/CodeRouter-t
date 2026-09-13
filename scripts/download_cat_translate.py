#!/usr/bin/env python3
"""Download CAT-Translate model files without bundling them in CodeRouter."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Download CAT-Translate-1.4b from Hugging Face")
    parser.add_argument("--output", type=Path, default=Path("models/CAT-Translate-1.4b"))
    parser.add_argument("--repo", default="cyberagent/CAT-Translate-1.4b")
    args = parser.parse_args()

    hf = shutil.which("hf") or shutil.which("huggingface-cli")
    if hf is None:
        print("hf または huggingface-cli をインストールしてください。", file=sys.stderr)
        return 2
    args.output.mkdir(parents=True, exist_ok=True)
    command = [hf, "download", args.repo, "--local-dir", str(args.output)]
    completed = subprocess.run(command, check=False)
    if completed.returncode == 0:
        print(f"CAT-Translate を {args.output} に配置しました。")
        print("llama-server で使う場合は、別途 llama.cpp 対応形式へ変換したモデルを指定してください。")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

