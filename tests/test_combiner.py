"""combiner モジュールのテスト。"""

import logging
from pathlib import Path

import pytest

from notebooklm_connector.combiner import combine
from notebooklm_connector.models import CombineConfig


def test_combine_merges_files(tmp_path: Path) -> None:
    """複数ファイルがアルファベット順で結合されること。"""
    input_dir = tmp_path / "md"
    input_dir.mkdir()
    (input_dir / "b_page.md").write_text("# Page B\n", encoding="utf-8")
    (input_dir / "a_page.md").write_text("# Page A\n", encoding="utf-8")

    output_file = tmp_path / "output" / "combined.md"
    config = CombineConfig(input_dir=input_dir, output_file=output_file)
    result = combine(config)

    assert result == output_file
    assert output_file.exists()

    content = output_file.read_text(encoding="utf-8")
    # a_page が先に来ること
    pos_a = content.index("Page A")
    pos_b = content.index("Page B")
    assert pos_a < pos_b


def test_combine_adds_source_header(tmp_path: Path) -> None:
    """ソースヘッダーが付与されること。"""
    input_dir = tmp_path / "md"
    input_dir.mkdir()
    (input_dir / "page.md").write_text("# Page\n", encoding="utf-8")

    output_file = tmp_path / "combined.md"
    config = CombineConfig(input_dir=input_dir, output_file=output_file)
    combine(config)

    content = output_file.read_text(encoding="utf-8")
    assert "<!-- Source: page.md -->" in content


def test_combine_no_source_header(tmp_path: Path) -> None:
    """add_source_header=False でヘッダーが付与されないこと。"""
    input_dir = tmp_path / "md"
    input_dir.mkdir()
    (input_dir / "page.md").write_text("# Page\n", encoding="utf-8")

    output_file = tmp_path / "combined.md"
    config = CombineConfig(
        input_dir=input_dir,
        output_file=output_file,
        add_source_header=False,
    )
    combine(config)

    content = output_file.read_text(encoding="utf-8")
    assert "<!-- Source:" not in content


def test_combine_uses_separator(tmp_path: Path) -> None:
    """カスタムセパレータが使用されること。"""
    input_dir = tmp_path / "md"
    input_dir.mkdir()
    (input_dir / "a.md").write_text("# A\n", encoding="utf-8")
    (input_dir / "b.md").write_text("# B\n", encoding="utf-8")

    output_file = tmp_path / "combined.md"
    config = CombineConfig(
        input_dir=input_dir,
        output_file=output_file,
        separator="\n===\n",
        add_source_header=False,
    )
    combine(config)

    content = output_file.read_text(encoding="utf-8")
    assert "\n===\n" in content


def test_combine_empty_directory(tmp_path: Path) -> None:
    """Markdown ファイルがない場合は空ファイルを生成すること。"""
    input_dir = tmp_path / "empty"
    input_dir.mkdir()

    output_file = tmp_path / "combined.md"
    config = CombineConfig(input_dir=input_dir, output_file=output_file)
    result = combine(config)

    assert result == output_file
    assert output_file.read_text(encoding="utf-8") == ""


def test_combine_warns_on_large_output(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """500,000 語を超える場合に警告が出ること。"""
    input_dir = tmp_path / "md"
    input_dir.mkdir()

    # 大量テキスト生成
    large_text = ("word " * 100_000).strip() + "\n"
    for i in range(6):
        (input_dir / f"page{i}.md").write_text(large_text, encoding="utf-8")

    output_file = tmp_path / "combined.md"
    config = CombineConfig(
        input_dir=input_dir,
        output_file=output_file,
        add_source_header=False,
    )

    with caplog.at_level(logging.WARNING):
        combine(config)

    assert any("500000" in r.message for r in caplog.records)
