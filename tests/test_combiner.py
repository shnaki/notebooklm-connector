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

    assert result == [output_file]
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
    assert "Source: page.md" in content


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
    assert "Source:" not in content


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

    assert result == [output_file]
    assert output_file.read_text(encoding="utf-8") == ""


def test_combine_warns_on_large_output(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """500,000 語を超える場合にファイルが分割されること。"""
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

    with caplog.at_level(logging.INFO):
        result = combine(config)

    assert len(result) > 1
    assert any("分割" in r.message for r in caplog.records)


def test_combine_recursive(tmp_path: Path) -> None:
    """サブディレクトリ内の .md も結合されること。"""
    input_dir = tmp_path / "md"
    sub_dir = input_dir / "guide"
    sub_dir.mkdir(parents=True)

    (input_dir / "index.md").write_text("# Index\n", encoding="utf-8")
    (sub_dir / "start.md").write_text("# Start\n", encoding="utf-8")

    output_file = tmp_path / "combined.md"
    config = CombineConfig(
        input_dir=input_dir,
        output_file=output_file,
        add_source_header=False,
    )
    combine(config)

    content = output_file.read_text(encoding="utf-8")
    assert "# Index" in content
    assert "# Start" in content


def test_combine_source_header_relative_path(tmp_path: Path) -> None:
    """ソースヘッダーに相対パスが含まれること。"""
    input_dir = tmp_path / "md"
    sub_dir = input_dir / "guide"
    sub_dir.mkdir(parents=True)

    (sub_dir / "start.md").write_text("# Start\n", encoding="utf-8")

    output_file = tmp_path / "combined.md"
    config = CombineConfig(input_dir=input_dir, output_file=output_file)
    combine(config)

    content = output_file.read_text(encoding="utf-8")
    assert "Source: guide/start.md" in content


def test_combine_splits_large_output(tmp_path: Path) -> None:
    """閾値超過時にファイルが分割されること。"""
    input_dir = tmp_path / "md"
    input_dir.mkdir()

    large_text = ("word " * 300_000).strip() + "\n"
    (input_dir / "a.md").write_text(large_text, encoding="utf-8")
    (input_dir / "b.md").write_text(large_text, encoding="utf-8")

    output_file = tmp_path / "combined.md"
    config = CombineConfig(
        input_dir=input_dir,
        output_file=output_file,
        add_source_header=False,
    )
    result = combine(config)

    assert len(result) == 2
    assert all(p.exists() for p in result)
    # 元のファイルは生成されない
    assert not output_file.exists()


def test_combine_split_file_naming(tmp_path: Path) -> None:
    """分割ファイルの命名が -001 形式であること。"""
    input_dir = tmp_path / "md"
    input_dir.mkdir()

    large_text = ("word " * 300_000).strip() + "\n"
    (input_dir / "a.md").write_text(large_text, encoding="utf-8")
    (input_dir / "b.md").write_text(large_text, encoding="utf-8")

    output_file = tmp_path / "combined.md"
    config = CombineConfig(
        input_dir=input_dir,
        output_file=output_file,
        add_source_header=False,
    )
    result = combine(config)

    assert result[0].name == "combined-001.md"
    assert result[1].name == "combined-002.md"


def test_combine_no_split_under_threshold(tmp_path: Path) -> None:
    """閾値以下では分割されないこと。"""
    input_dir = tmp_path / "md"
    input_dir.mkdir()

    small_text = ("word " * 100).strip() + "\n"
    (input_dir / "a.md").write_text(small_text, encoding="utf-8")
    (input_dir / "b.md").write_text(small_text, encoding="utf-8")

    output_file = tmp_path / "combined.md"
    config = CombineConfig(
        input_dir=input_dir,
        output_file=output_file,
        add_source_header=False,
    )
    result = combine(config)

    assert result == [output_file]
    assert output_file.exists()
