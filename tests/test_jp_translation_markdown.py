from __future__ import annotations

from coderouter.jp_translation.masking import mask_text, unmask_text


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


def test_large_markdown_table_is_one_translation_unit() -> None:
    rows = [f"| {i} | 日本語の説明 {i} |" for i in range(100)]
    text = "| ID | 説明 |\n| --- | --- |\n" + "\n".join(rows)
    masked, mapping = mask_text(text)

    # Only syntax is protected; all rows remain in one text payload for the caller.
    assert len(mapping) >= 202
    assert unmask_text(masked, mapping) == text
