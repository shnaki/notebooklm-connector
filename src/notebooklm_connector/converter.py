"""HTML→Markdown 変換モジュール。

HTML ファイルをクリーニングし、NotebookLM に適した Markdown に変換する。
ZIP アーカイブからの変換もサポート。
"""

import logging
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
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


def _collect_conversion_results(
    source_labels: list[str],
    results: list[Path | None],
) -> tuple[list[Path], list[str]]:
    """並列変換結果から成功パスと失敗ラベルを集計する。"""
    output_paths = [path for path in results if path is not None]
    failed_sources = [
        source_labels[index] for index, path in enumerate(results) if path is None
    ]
    return output_paths, failed_sources


def _convert_single_file(html_file: Path, config: ConvertConfig) -> Path | None:
    """単一の HTML ファイルを Markdown に変換する。

    Args:
        html_file: 入力 HTML ファイルのパス。
        config: 変換設定。

    Returns:
        生成された Markdown ファイルのパス。失敗時は None。
    """
    relative = html_file.relative_to(config.input_dir)
    logger.info("変換中: %s", relative)
    try:
        html_content = html_file.read_text(encoding="utf-8")
        markdown = convert_html_to_markdown(html_content, config)
        output_path = config.output_dir / relative.with_suffix(".md")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        return output_path
    except (OSError, PermissionError, UnicodeDecodeError):
        logger.exception("変換失敗: %s", relative)
        return None


def _convert_files_in_parallel(
    html_files: list[Path],
    config: ConvertConfig,
) -> tuple[list[Path], list[str]]:
    """HTML ファイル群を並列変換し、成功パスと失敗パスを返す。"""
    with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
        results = list(
            executor.map(_convert_single_file, html_files, [config] * len(html_files))
        )
    labels = [path.as_posix() for path in html_files]
    return _collect_conversion_results(labels, results)


def convert_directory(config: ConvertConfig) -> tuple[list[Path], list[str]]:
    """ディレクトリ内の全 HTML ファイルを Markdown に変換する。

    Args:
        config: 変換設定。

    Returns:
        (生成された Markdown ファイルのパスリスト, 失敗したファイルパスのリスト)。
    """
    config.output_dir.mkdir(parents=True, exist_ok=True)

    html_files = sorted(
        [*config.input_dir.rglob("*.html"), *config.input_dir.rglob("*.htm")]
    )
    if not html_files:
        logger.warning("HTML ファイルが見つかりません: %s", config.input_dir)
        return [], []

    output_paths, failed_files = _convert_files_in_parallel(html_files, config)
    logger.info("%d ファイルを変換しました", len(output_paths))
    return output_paths, failed_files


def convert_failed_files(
    file_paths: list[str],
    config: ConvertConfig,
) -> tuple[list[Path], list[str]]:
    """指定したファイルパスのみを Markdown に変換する。

    report.json の convert_failures に記録された絶対パス (posix 形式) を
    受け取り、再変換する。存在しないファイルは失敗リストに追加してスキップする。

    Args:
        file_paths: 変換対象の HTML ファイルパス (絶対パス posix 形式) のリスト。
        config: 変換設定。input_dir が基底ディレクトリとして使用される。

    Returns:
        (生成された Markdown ファイルのパスリスト, 失敗したファイルパスのリスト)。
    """
    config.output_dir.mkdir(parents=True, exist_ok=True)

    html_files: list[Path] = []
    pre_failed: list[str] = []
    for posix_path in file_paths:
        p = Path(posix_path)
        if not p.exists():
            logger.warning("ファイルが存在しません: %s", posix_path)
            pre_failed.append(posix_path)
        else:
            html_files.append(p)

    if not html_files:
        return [], pre_failed

    output_paths, convert_failed = _convert_files_in_parallel(html_files, config)

    logger.info("%d ファイルを再変換しました", len(output_paths))
    return output_paths, pre_failed + convert_failed


def _convert_html_content(args: tuple[str, str, Path, ConvertConfig]) -> Path | None:
    """HTML コンテンツ文字列を Markdown に変換してファイルに書き出す。

    Args:
        args: (エントリ名, HTML コンテンツ, 出力ディレクトリ, 変換設定) のタプル。

    Returns:
        生成された Markdown ファイルのパス。失敗時は None。
    """
    name, html_content, output_dir, config = args
    logger.info("ZIP から変換中: %s", name)
    try:
        markdown = convert_html_to_markdown(html_content, config)
        output_path = output_dir / Path(name).with_suffix(".md")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        return output_path
    except (OSError, PermissionError, UnicodeDecodeError):
        logger.exception("ZIP 変換失敗: %s", name)
        return None


def convert_zip(
    zip_path: Path,
    output_dir: Path,
    config: ConvertConfig | None = None,
) -> tuple[list[Path], list[str]]:
    """ZIP アーカイブ内の HTML ファイルを Markdown に変換する。

    Args:
        zip_path: ZIP ファイルのパス。
        output_dir: Markdown 出力先ディレクトリ。
        config: 変換設定。None の場合はデフォルト設定を使用。

    Returns:
        (生成された Markdown ファイルのパスリスト, 失敗したエントリ名のリスト)。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if config is None:
        config = ConvertConfig(input_dir=Path("."), output_dir=output_dir)

    # メインスレッドで ZIP から一括読み込み
    entries: list[tuple[str, str, Path, ConvertConfig]] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        html_names = sorted(
            name
            for name in zf.namelist()
            if name.endswith((".html", ".htm")) and not name.startswith("__MACOSX")
        )
        for name in html_names:
            html_content = zf.read(name).decode("utf-8")
            entries.append((name, html_content, output_dir, config))

    # 変換を並列実行
    with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
        results = list(executor.map(_convert_html_content, entries))

    output_paths, failed_entries = _collect_conversion_results(
        [entry[0] for entry in entries], results
    )

    logger.info("ZIP から %d ファイルを変換しました", len(output_paths))
    return output_paths, failed_entries
