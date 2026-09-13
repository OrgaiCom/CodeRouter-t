# 第三者コンポーネント

## CAT-Translate-1.4B

- 著作権者: CyberAgent AI Lab
- ライセンス: MIT
- 公式モデル: <https://huggingface.co/cyberagent/CAT-Translate-1.4b>
- CodeRouterにはモデルファイルを同梱しません。`scripts/download_cat_translate.py` で利用者が取得します。
- モデルカード記載の推奨プロンプトは、`Translate the following {src_lang} text into {tgt_lang}.` 形式です。
- ベースモデル `sbintuitions/sarashina2.2-1b` もモデルカード上はMITライセンスです。

## CAT-Translate GGUF量子化版

- 配布元: mradermacher
- モデル: `mradermacher/CAT-Translate-1.4b-GGUF`
- 用途: `installCodeRouter.bat cat` が取得するllama.cpp用GGUF
- ライセンス表示: 配布ページではMITと表示されています。元モデルはCyberAgentのCAT-Translate-1.4Bです。
- 配布ページ: <https://huggingface.co/mradermacher/CAT-Translate-1.4b-GGUF>
- CodeRouterはこのモデルファイルをGitリポジトリへ同梱しません。

## Argos Translateモデル

- CodeRouterの既存Argosバックエンドは、Argos公式の`ja↔en`モデルをダウンロードします。
- Argos Translate本体: MITまたはCC0（[公式ライセンス](https://github.com/argosopentech/argos-translate/blob/master/LICENSE)）。
- ダウンロード元・SHA256は [`scripts/setup_argos_models.py`](scripts/setup_argos_models.py) に定義しています。
- CATバックエンドを使う場合、Argosモデルは不要です。

## OPUS-MTモデル（High-Quality Argosビルド）

- `Helsinki-NLP/opus-mt-jap-en`
- `Helsinki-NLP/opus-mt-en-jap`
- ライセンス: 各モデルカードではApache-2.0。High-Quality Argosモデルのビルド時にのみ使用します。
- [ja→enモデル](https://huggingface.co/Helsinki-NLP/opus-mt-jap-en)
- en→jaモデルも同じHelsinki-NLPのOPUS-MT系列です。

## llama.cpp

- 用途: CAT-Translate GGUFを`llama-server`で提供する外部実行基盤
- ライセンス: MIT
- 公式リポジトリ: <https://github.com/ggml-org/llama.cpp>
- CodeRouterはllama.cppをPython依存関係として組み込みません。利用者の環境へ任意で導入します。

## md-translator

CodeRouterの実装は `rockbenben/md-translator` のコードをコピー・移植していません。Markdown構造を保護して自然言語部分を翻訳するという一般的な設計方針のみを参考にしています。
