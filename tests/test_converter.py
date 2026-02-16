"""converter モジュールのテスト。"""

import zipfile
from pathlib import Path

from notebooklm_connector.converter import (
    convert_directory,
    convert_html_to_markdown,
    convert_zip,
)
from notebooklm_connector.models import ConvertConfig


def test_convert_extracts_main_content(sample_html: str) -> None:
    """<main> タグの中身のみが抽出されること。"""
    result = convert_html_to_markdown(sample_html)
    assert "Hello World" in result
    assert "test" in result
    assert "Item 1" in result


def test_convert_strips_nav_footer(sample_html: str) -> None:
    """nav, footer, header, aside が除去されること。"""
    result = convert_html_to_markdown(sample_html)
    assert "Nav Link" not in result
    assert "Footer content" not in result
    assert "Sidebar content" not in result
    assert "Site Header" not in result


def test_convert_strips_script_style(sample_html: str) -> None:
    """script, style タグが除去されること。"""
    result = convert_html_to_markdown(sample_html)
    assert "console.log" not in result
    assert "color: red" not in result


def test_convert_excludes_images(sample_html_with_images: str) -> None:
    """画像が Markdown 出力から除外されること。"""
    result = convert_html_to_markdown(sample_html_with_images)
    assert "photo.png" not in result
    assert "![" not in result
    assert "Before image" in result
    assert "After image" in result


def test_convert_no_main_tag(sample_html_no_main: str) -> None:
    """<main> タグがない場合もコンテンツが変換されること。"""
    result = convert_html_to_markdown(sample_html_no_main)
    assert "Page Title" in result
    assert "Body content here" in result


def test_convert_strips_nav_from_no_main(
    sample_html_no_main: str,
) -> None:
    """<main> がなくても nav/footer が除去されること。"""
    result = convert_html_to_markdown(sample_html_no_main)
    assert "Home" not in result
    assert "Footer" not in result


def test_convert_normalizes_whitespace() -> None:
    """連続空行が正規化されること。"""
    html = "<main><p>A</p>\n\n\n\n\n<p>B</p></main>"
    result = convert_html_to_markdown(html)
    assert "\n\n\n" not in result


def test_convert_heading_style() -> None:
    """ATX スタイルの見出しが生成されること。"""
    html = "<main><h1>Title</h1><h2>Sub</h2></main>"
    result = convert_html_to_markdown(html)
    assert result.startswith("# Title") or "# Title" in result
    assert "## Sub" in result


def test_convert_directory_creates_md_files(tmp_path: Path) -> None:
    """ディレクトリ変換で .md ファイルが生成されること。"""
    input_dir = tmp_path / "html"
    output_dir = tmp_path / "md"
    input_dir.mkdir()

    (input_dir / "page1.html").write_text(
        "<main><h1>Page 1</h1></main>", encoding="utf-8"
    )
    (input_dir / "page2.html").write_text(
        "<main><h1>Page 2</h1></main>", encoding="utf-8"
    )

    config = ConvertConfig(input_dir=input_dir, output_dir=output_dir)
    result = convert_directory(config)

    assert len(result) == 2
    assert (output_dir / "page1.md").exists()
    assert (output_dir / "page2.md").exists()
    assert "Page 1" in (output_dir / "page1.md").read_text(encoding="utf-8")


def test_convert_directory_empty(tmp_path: Path) -> None:
    """HTML ファイルがない場合は空リストを返すこと。"""
    input_dir = tmp_path / "empty"
    output_dir = tmp_path / "out"
    input_dir.mkdir()

    config = ConvertConfig(input_dir=input_dir, output_dir=output_dir)
    result = convert_directory(config)

    assert result == []


def test_convert_zip_creates_md_files(tmp_path: Path) -> None:
    """ZIP 内の HTML がすべて変換されること。"""
    zip_path = tmp_path / "docs.zip"
    output_dir = tmp_path / "md"

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("index.html", "<main><h1>Index</h1></main>")
        zf.writestr(
            "guide/start.html",
            "<main><h1>Getting Started</h1></main>",
        )

    result = convert_zip(zip_path, output_dir)

    assert len(result) == 2
    contents = [p.read_text(encoding="utf-8") for p in result]
    all_text = "\n".join(contents)
    assert "Index" in all_text
    assert "Getting Started" in all_text


def test_convert_zip_skips_macosx(tmp_path: Path) -> None:
    """__MACOSX ディレクトリのファイルがスキップされること。"""
    zip_path = tmp_path / "docs.zip"
    output_dir = tmp_path / "md"

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("page.html", "<main><h1>Page</h1></main>")
        zf.writestr("__MACOSX/page.html", "<main><h1>Ghost</h1></main>")

    result = convert_zip(zip_path, output_dir)

    assert len(result) == 1
    assert "Ghost" not in result[0].read_text(encoding="utf-8")


def test_convert_custom_strip_classes() -> None:
    """カスタム strip_classes が適用されること。"""
    html = '<main><div class="my-ad">Ad</div><p>Content</p></main>'
    config = ConvertConfig(
        input_dir=Path("."),
        output_dir=Path("."),
        strip_classes=["my-ad"],
    )
    result = convert_html_to_markdown(html, config)
    assert "Ad" not in result
    assert "Content" in result
