#!/usr/bin/env python3
"""Build CodeRouter-t high-quality Argos packages (offline-capable generator).

Base models (Apache-2.0,要実在確認):
  ja -> en: Helsinki-NLP/opus-mt-jap-en
  en -> ja: Helsinki-NLP/opus-mt-en-jap

Pipeline:
  1. snapshot_download (HF Marian)
  2. ct2-transformers-converter --quantization int8
  3. Argos-compatible dir (model/, sentencepiece.model, metadata.json, README)
  4. zip -> .argosmodel
  5. SHA256SUMS.json

URL/SHA256は捏造しない。生成後にReleaseへ公開し、
scripts/setup_argos_models.py MODEL_REGISTRY["high-quality"]へ転記する。

Requirements (build時のみ):
    pip install huggingface_hub ctranslate2 transformers sentencepiece

Usage:
    python scripts/build_hq_argos_models.py --output-dir models/hq
    python scripts/build_hq_argos_models.py --pairs ja_en --output-dir models/hq

Design notes:
  - HFのSentencePiece名は source.spm とは限らないため候補探索する。
  - StanzaはArgos公式1.1同様に必要になる場合がある。--stanza-dir指定時は
    同梱し、未指定時は警告のみ(TranslatorManagerのinstall可否で検証すること)。
  - manager.pyはARGOS_DEVICE_TYPE=cuda済みのため、生成物は既存経路
    install_from_path -> get_translation_from_codes()でそのまま使える想定。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

MODELS: dict[str, dict[str, str]] = {
    "ja_en": {
        "hf": "Helsinki-NLP/opus-mt-jap-en",
        "from_code": "ja",
        "from_name": "Japanese",
        "to_code": "en",
        "to_name": "English",
    },
    "en_ja": {
        "hf": "Helsinki-NLP/opus-mt-en-jap",
        "from_code": "en",
        "from_name": "English",
        "to_code": "ja",
        "to_name": "Japanese",
    },
}

# HF Marian系で見られるSentencePiece候補(優先順)
SPM_CANDIDATES = (
    "source.spm",
    "spm.source",
    "sentencepiece.bpe.model",
    "sentence_spm.model",
)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_sentencepiece(model_dir: Path) -> Path:
    for name in SPM_CANDIDATES:
        p = model_dir / name
        if p.is_file():
            return p
    # フォールバック: *.spm / *.model の先頭1件
    fallbacks = sorted(model_dir.glob("*.spm")) + sorted(model_dir.glob("*.model"))
    if fallbacks:
        return fallbacks[0]
    raise FileNotFoundError(f"SentencePiece not found in {model_dir} (tried {SPM_CANDIDATES})")


def build_metadata(config: dict[str, str]) -> dict[str, str]:
    try:
        from argostranslate import package as _pkg  # type: ignore[import-untyped]

        argos_ver = str(getattr(_pkg, "__version__", "1.5"))
    except Exception:
        argos_ver = "1.5"
    return {
        "package_version": "1.0",
        "argos_version": argos_ver,
        "from_code": config["from_code"],
        "from_name": config["from_name"],
        "to_code": config["to_code"],
        "to_name": config["to_name"],
    }


def convert_to_ct2(model_dir: Path, output_dir: Path, quantization: str = "int8") -> None:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    subprocess.run(
        [
            "ct2-transformers-converter",
            "--model",
            str(model_dir),
            "--output_dir",
            str(output_dir),
            "--quantization",
            quantization,
        ],
        check=True,
    )


def create_package(
    key: str,
    config: dict[str, str],
    ct2_dir: Path,
    hf_dir: Path,
    output_dir: Path,
    stanza_dir: Path | None = None,
) -> Path:
    package_name = f"translate-{key}-opus-mt-1_0"
    package_dir = output_dir / package_name
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True)

    shutil.copytree(ct2_dir, package_dir / "model")
    shutil.copy2(find_sentencepiece(hf_dir), package_dir / "sentencepiece.model")

    if stanza_dir and stanza_dir.is_dir():
        shutil.copytree(stanza_dir, package_dir / "stanza", dirs_exist_ok=True)

    (package_dir / "metadata.json").write_text(
        json.dumps(build_metadata(config), indent=4, ensure_ascii=False),
        encoding="utf-8",
    )
    (package_dir / "README.md").write_text(
        f"# {config['from_name']} -> {config['to_name']}\n\n"
        f"CodeRouter-t high-quality model.\n\nBase model:\n{config['hf']}\n\nLicense:\nApache-2.0\n",
        encoding="utf-8",
    )

    archive_base = output_dir / package_name
    archive = shutil.make_archive(
        str(archive_base), "zip", root_dir=output_dir, base_dir=package_name
    )
    archive_path = Path(archive)
    final_path = archive_path.with_suffix(".argosmodel")
    if final_path.exists():
        final_path.unlink()
    archive_path.rename(final_path)
    return final_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", type=Path, default=Path("models/hq"))
    p.add_argument("--pairs", choices=["ja_en", "en_ja", "both"], default="both")
    p.add_argument("--quantization", default="int8")
    p.add_argument("--stanza-dir", type=Path, default=None)
    p.add_argument("--hf-ja-en", default=MODELS["ja_en"]["hf"])
    p.add_argument("--hf-en-ja", default=MODELS["en_ja"]["hf"])
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    import tempfile

    args = parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    configs = {k: dict(v) for k, v in MODELS.items()}
    configs["ja_en"]["hf"] = args.hf_ja_en
    configs["en_ja"]["hf"] = args.hf_en_ja
    keys = ["ja_en", "en_ja"] if args.pairs == "both" else [args.pairs]

    # 遅延import: 単体テスト・--helpはHFなしで動く
    from huggingface_hub import snapshot_download

    hashes: dict[str, str] = {}
    for key in keys:
        cfg = configs[key]
        print(f"\n=== {key} ===\nModel: {cfg['hf']}")
        with tempfile.TemporaryDirectory(prefix=f"coderouter-{key}-") as tmp:
            work = Path(tmp)
            hf_dir = Path(snapshot_download(repo_id=cfg["hf"], local_dir=str(work / "hf")))
            ct2_dir = work / "ct2"
            convert_to_ct2(hf_dir, ct2_dir, args.quantization)
            package = create_package(key, cfg, ct2_dir, hf_dir, args.output_dir, args.stanza_dir)
        digest = sha256_of(package)
        hashes[package.name] = digest
        print(f"\nPackage : {package}\nSHA256  : {digest}")
        if args.stanza_dir is None:
            print("[warn] stanza未同梱。install_from_pathで検証し、必要なら--stanza-dirで再生成。")

    manifest = args.output_dir / "SHA256SUMS.json"
    manifest.write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    print(f"\nSHA256 manifest: {manifest}")
    print("Next: .argosmodelをRelease公開し、URL+SHA256をMODEL_REGISTRYへ転記。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
