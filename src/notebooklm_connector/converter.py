"""HTML→Markdown 変換モジュール。

HTML ファイルをクリーニングし、NotebookLM に適した Markdown に変換する。
ZIP アーカイブからの変換もサポート。
"""

import logging
import re
import zipfile
from pathlib import Path

from bs4 import BeautifulSoup, Tag
from markdownify import MarkdownConverter

from notebooklm_connector.models import ConvertConfig

logger = logging.getLogger(__name__)


class _NotebookLMConverter(MarkdownConverter):
    """画像を除外するカスタム MarkdownConverter。"""

    def convert_img(
        self,
        el: Tag,
        text: str,
        parent: Tag | None = None,
    ) -> str:
        """画像タグを空文字に変換して除外する。"""
        return ""

    # svg も除外
    def convert_svg(
        self,
        el: Tag,
        text: str,
        parent: Tag | None = None,
    ) -> str:
        """SVG 要素を空文字に変換して除外する。"""
        return ""


def _clean_html(html: str, config: ConvertConfig) -> str:
    """不要な HTML 要素を除去する。

    Args:
        html: 入力 HTML 文字列。
        config: 変換設定。

    Returns:
        クリーニング済み HTML 文字列。
    """
    soup = BeautifulSoup(html, "lxml")

    # <main>, <article>, role="main" があればその中身のみ使用
    main_content = (
        soup.find("main") or soup.find("article") or soup.find(attrs={"role": "main"})
    )
    if isinstance(main_content, Tag):
        # main の中身だけで新しい soup を作る
        soup = BeautifulSoup(str(main_content), "lxml")

    # 不要タグの除去
    for tag_name in config.strip_tags:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # SVG の除去
    for svg in soup.find_all("svg"):
        svg.decompose()

    # 不要クラスを持つ要素の除去
    for class_name in config.strip_classes:
        for el in soup.find_all(class_=re.compile(class_name, re.IGNORECASE)):
            el.decompose()

    # class/style 属性の除去
    for tag in soup.find_all(True):
        for attr in ["class", "style"]:
            if attr in tag.attrs:
                del tag.attrs[attr]

    return str(soup)


def _normalize_whitespace(text: str) -> str:
    """連続する空行を最大 2 行に正規化する。"""
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def convert_html_to_markdown(
    html: str,
    config: ConvertConfig | None = None,
) -> str:
    """単一の HTML 文字列を Markdown に変換する。

    Args:
        html: 入力 HTML 文字列。
        config: 変換設定。None の場合はデフォルト設定を使用。

    Returns:
        Markdown 文字列。
    """
    if config is None:
        config = ConvertConfig(input_dir=Path("."), output_dir=Path("."))

    cleaned = _clean_html(html, config)
    markdown = _NotebookLMConverter(
        heading_style="ATX",
        strip=["img"],
    ).convert(cleaned)
    return _normalize_whitespace(markdown)


def convert_directory(config: ConvertConfig) -> list[Path]:
    """ディレクトリ内の全 HTML ファイルを Markdown に変換する。

    Args:
        config: 変換設定。

    Returns:
        生成された Markdown ファイルのパスリスト。
    """
    config.output_dir.mkdir(parents=True, exist_ok=True)

    html_files = sorted(config.input_dir.glob("*.html"))
    if not html_files:
        logger.warning("HTML ファイルが見つかりません: %s", config.input_dir)
        return []

    output_paths: list[Path] = []
    for html_file in html_files:
        logger.info("変換中: %s", html_file.name)
        html_content = html_file.read_text(encoding="utf-8")
        markdown = convert_html_to_markdown(html_content, config)

        output_path = config.output_dir / html_file.with_suffix(".md").name
        output_path.write_text(markdown, encoding="utf-8")
        output_paths.append(output_path)

    logger.info("%d ファイルを変換しました", len(output_paths))
    return output_paths


def convert_zip(
    zip_path: Path,
    output_dir: Path,
    config: ConvertConfig | None = None,
) -> list[Path]:
    """ZIP アーカイブ内の HTML ファイルを Markdown に変換する。

    Args:
        zip_path: ZIP ファイルのパス。
        output_dir: Markdown 出力先ディレクトリ。
        config: 変換設定。None の場合はデフォルト設定を使用。

    Returns:
        生成された Markdown ファイルのパスリスト。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if config is None:
        config = ConvertConfig(input_dir=Path("."), output_dir=output_dir)

    output_paths: list[Path] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        html_names = sorted(
            name
            for name in zf.namelist()
            if name.endswith(".html") and not name.startswith("__MACOSX")
        )

        for name in html_names:
            logger.info("ZIP から変換中: %s", name)
            html_content = zf.read(name).decode("utf-8")
            markdown = convert_html_to_markdown(html_content, config)

            # ネストされたパスをフラットなファイル名にする
            flat_name = Path(name).stem.replace("/", "_").replace("\\", "_") + ".md"
            output_path = output_dir / flat_name
            output_path.write_text(markdown, encoding="utf-8")
            output_paths.append(output_path)

    logger.info("ZIP から %d ファイルを変換しました", len(output_paths))
    return output_paths
