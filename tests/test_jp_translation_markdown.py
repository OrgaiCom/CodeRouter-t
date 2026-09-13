from __future__ import annotations

import contextlib
import re
from unittest.mock import Mock

import pytest

from coderouter.jp_translation.masking import mask_text, unmask_text
from coderouter.jp_translation.translator import _translate_chunked

_JA_KANA_RE = re.compile(r"[\u3040-\u309F\u30A0-\u30FF]")


def _counting_manager() -> tuple[Mock, dict[str, int]]:
    """Mock manager that preserves placeholders and counts backend calls."""
    calls = {"ja_to_en": 0, "en_to_ja": 0}
    manager = Mock()
    manager.is_available.return_value = True

    def _ja_en(masked_text: str) -> str:
        calls["ja_to_en"] += 1
        # Simulate translation: replace Japanese prose, keep placeholders/pipes.
        return masked_text.replace("日本語の説明", "description in English")

    def _en_ja(masked_text: str) -> str:
        calls["en_to_ja"] += 1
        return masked_text + " です"

    manager.translate_ja_to_en.side_effect = _ja_en
    manager.translate_en_to_ja.side_effect = _en_ja
    return manager, calls


def test_markdown_structure_is_round_tripped_without_masking_prose() -> None:
    text = (
        "---\n"
        "title: 日本語の文書\n"
        "---\n\n"
        "# 見出し\n\n"
        "> 引用\n\n"
        "- 項目\n"
        "  - 子項目\n\n"
        "<span>HTML</span> と $x^2$\n"
        "\n| 項目 | 説明 |\n| --- | --- |\n| A | 内容 |\n"
    )

    masked, mapping = mask_text(text)

    assert "title: 日本語の文書" not in masked
    assert "# " not in masked
    assert "<span>" not in masked
    assert "| --- | --- |" not in masked
    assert "見出し" in masked
    assert "引用" in masked
    assert unmask_text(masked, mapping) == text


def test_markdown_elements_round_trip() -> None:
    cases = [
        "# 見出しレベル1",
        "## 見出しレベル2",
        "- 箇条書き項目",
        "  - ネストした項目",
        "1. 番号付き項目",
        "> 引用文の内容",
        "- [ ] 未完了タスク",
        "- [x] 完了タスク",
        "~~取り消し線~~ の内容",
        "インライン `getUser()` コードを含む文",
        "リンク [CodeRouter](https://example.com/docs) の説明",
        "画像 ![代替テキスト](https://example.com/img.png) の説明",
        "<div class=\"note\">HTMLブロック</div> の説明",
        "$$x^2 + y^2$$ と $x^2$ の数式",
        "```ts\nconst x: number = 1;\n``` の前後の文",
    ]
    for text in cases:
        masked, mapping = mask_text(text)
        assert unmask_text(masked, mapping) == text, f"round-trip failed: {text!r}"


def test_task_checkbox_and_strikethrough_markers_protected() -> None:
    masked, mapping = mask_text("- [ ] タスクの内容")
    assert "- [ ]" not in masked
    assert "タスクの内容" in masked
    assert unmask_text(masked, mapping) == "- [ ] タスクの内容"

    masked2, mapping2 = mask_text("~~削除~~ された部分")
    assert "~~" not in masked2
    assert "された部分" in masked2
    assert unmask_text(masked2, mapping2) == "~~削除~~ された部分"


def test_latex_protected_but_currency_not_masked() -> None:
    masked, mapping = mask_text("数式 $x^2$ の説明")
    assert "$x^2$" not in masked
    assert unmask_text(masked, mapping) == "数式 $x^2$ の説明"

    masked2, mapping2 = mask_text("価格は $100 です")
    assert "$100" in masked2
    assert mapping2 == {} or "$100" in unmask_text(masked2, mapping2)


def test_table_pipes_stay_as_structure() -> None:
    """Cell pipes must NOT be masked: the table stays one translation unit."""
    text = "| 項目 | 説明 |\n| --- | --- |\n| A | 日本語の説明 |"
    masked, mapping = mask_text(text)
    # Structure preserved inline, separator row protected, prose translatable.
    assert "|" in masked
    assert "| --- | --- |" not in masked
    assert "日本語の説明" in masked
    assert unmask_text(masked, mapping) == text


def test_tech_terms_round_trip() -> None:
    cases = [
        "C# のプロパティを修正してください",
        "Python の関数 getUser() を呼び出す",
        "TypeScript の interface UserService を実装する",
        '{"name": "test", "value": 1} を返す',
        "PowerShell で Get-ChildItem を実行する",
        "パス C:\\Users\\test\\file.ts を開く",
        "コマンド npm test を実行して",
        "API の UserService.getUser を呼び出す",
        "URL https://example.com/api を参照する",
    ]
    for text in cases:
        masked, mapping = mask_text(text)
        assert unmask_text(masked, mapping) == text, f"round-trip failed: {text!r}"


def test_100cell_table_is_single_backend_call() -> None:
    """100セルでもバックエンド呼び出しは1回 (セル数に比例させない)。"""
    rows = [f"| {i} | 日本語の説明 {i} |" for i in range(100)]
    text = "| ID | 説明 |\n| --- | --- |\n" + "\n".join(rows)
    assert len(text) < 4096  # single-chunk前提の確認

    manager, calls = _counting_manager()
    result = _translate_chunked(text, "ja_to_en", manager)

    assert calls["ja_to_en"] == 1
    assert "description in English" in result
    assert "|" in result  # 表構造が残っている


def test_large_table_call_count_not_proportional_to_cells() -> None:
    """チャンク超過の大テーブルでも呼び出し数はチャンク数止まり。"""
    rows = [f"| {i} | 日本語の説明テキスト {i} の詳細内容について |" for i in range(300)]
    text = "| ID | 説明 |\n| --- | --- |\n" + "\n".join(rows)
    assert len(text) > 4096

    manager, calls = _counting_manager()
    result = _translate_chunked(text, "ja_to_en", manager)

    assert calls["ja_to_en"] <= 10  # 300セルに対して1桁止まり
    assert calls["ja_to_en"] < 300
    assert "description in English" in result


def test_long_text_chunking_keeps_sentence_units() -> None:
    long_text = "".join(f"これは長い日本語の文章です。段落{i}の内容を説明します。\n\n" for i in range(200))
    assert len(long_text) > 4096

    manager, calls = _counting_manager()
    result = _translate_chunked(long_text, "ja_to_en", manager)

    assert calls["ja_to_en"] >= 2  # 分割はされる
    assert calls["ja_to_en"] <= len(long_text) // 512  # 文字単位の細切れではない
    assert result != ""


def test_en_to_ja_pipeline_yields_japanese() -> None:
    """EN→JA経路で日本語(かな含み)が出ること。中国語化の回帰検知用。"""
    manager = Mock()
    manager.is_available.return_value = True
    manager.translate_en_to_ja.return_value = "バグを修正してください。"
    manager.translate_ja_to_en.return_value = "Please fix the bug."

    result = _translate_chunked("Please fix the bug.", "en_to_ja", manager)
    assert _JA_KANA_RE.search(result) is not None
    assert "バグ" in result


def test_cat_unavailable_raises_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coderouter.jp_translation.manager import TranslatorManager

    class FailingCat:
        def __init__(self, **kwargs: object) -> None:
            pass

        def load(self) -> None:
            raise ConnectionError("refused")

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "coderouter.jp_translation.cat_translate.CatTranslateBackend", FailingCat
    )
    manager = TranslatorManager(
        backend="cat_translate", cat_fallback_to_argos=False
    )
    with pytest.raises(RuntimeError, match="CAT-Translate server is unavailable"):
        manager.load()


def test_cat_unavailable_falls_back_to_argos_with_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """フォールバック有効時は _backend が argos へ切り替わること。"""
    from coderouter.jp_translation.manager import TranslatorManager

    class FailingCat:
        def __init__(self, **kwargs: object) -> None:
            pass

        def load(self) -> None:
            raise ConnectionError("refused")

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "coderouter.jp_translation.cat_translate.CatTranslateBackend", FailingCat
    )
    manager = TranslatorManager(
        backend="cat_translate", cat_fallback_to_argos=True
    )
    with contextlib.suppress(RuntimeError):
        # Argos未導入環境では Argos側のRuntimeErrorで終わる想定
        manager.load()
    assert manager._backend == "argos"
    manager.close()
