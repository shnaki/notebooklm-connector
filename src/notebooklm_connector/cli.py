"""CLI エントリポイント。

crawl / convert / combine / pipeline の 4 サブコマンドを提供する。
"""

import argparse
import logging
import sys
from pathlib import Path

from notebooklm_connector.combiner import combine
from notebooklm_connector.converter import convert_directory, convert_zip
from notebooklm_connector.crawler import crawl
from notebooklm_connector.models import CombineConfig, ConvertConfig, CrawlConfig

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    """CLI パーサーを構築する。"""
    parser = argparse.ArgumentParser(
        prog="notebooklm-connector",
        description=("Web サイトをクロールし NotebookLM 向け Markdown に変換する"),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="詳細ログを出力する",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- crawl ---
    crawl_parser = subparsers.add_parser(
        "crawl", help="Web サイトをクロールし HTML を保存する"
    )
    crawl_parser.add_argument("url", help="開始 URL")
    crawl_parser.add_argument(
        "-o",
        "--output",
        required=True,
        type=Path,
        help="HTML 出力ディレクトリ",
    )
    crawl_parser.add_argument(
        "--max-pages",
        type=int,
        default=100,
        help="最大ページ数 (デフォルト: 100)",
    )
    crawl_parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="リクエスト間隔 秒 (デフォルト: 1.0)",
    )

    # --- convert ---
    convert_parser = subparsers.add_parser(
        "convert", help="HTML を Markdown に変換する"
    )
    convert_parser.add_argument(
        "input", type=Path, help="HTML 入力ディレクトリまたは ZIP ファイルのパス"
    )
    convert_parser.add_argument(
        "-o",
        "--output",
        required=True,
        type=Path,
        help="Markdown 出力ディレクトリ",
    )
    convert_parser.add_argument(
        "--zip",
        action="store_true",
        default=False,
        help="入力を ZIP ファイルとして扱う",
    )

    # --- combine ---
    combine_parser = subparsers.add_parser(
        "combine", help="Markdown ファイルを 1 つに結合する"
    )
    combine_parser.add_argument("input", type=Path, help="Markdown 入力ディレクトリ")
    combine_parser.add_argument(
        "-o",
        "--output",
        required=True,
        type=Path,
        help="結合出力ファイル",
    )

    # --- pipeline ---
    pipeline_parser = subparsers.add_parser(
        "pipeline",
        help="crawl → convert → combine を一括実行する",
    )
    pipeline_parser.add_argument("url", help="開始 URL")
    pipeline_parser.add_argument(
        "-o",
        "--output",
        required=True,
        type=Path,
        help="出力ディレクトリ",
    )
    pipeline_parser.add_argument(
        "--max-pages",
        type=int,
        default=100,
        help="最大ページ数 (デフォルト: 100)",
    )
    pipeline_parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="リクエスト間隔 秒 (デフォルト: 1.0)",
    )

    return parser


def _run_crawl(args: argparse.Namespace) -> None:
    """crawl サブコマンドを実行する。"""
    config = CrawlConfig(
        start_url=args.url,
        output_dir=args.output,
        max_pages=args.max_pages,
        delay_seconds=args.delay,
    )
    files = crawl(config)
    print(f"{len(files)} ページを保存しました: {args.output}")


def _run_convert(args: argparse.Namespace) -> None:
    """convert サブコマンドを実行する。"""
    if args.zip:
        files = convert_zip(args.input, args.output)
    else:
        config = ConvertConfig(input_dir=args.input, output_dir=args.output)
        files = convert_directory(config)
    print(f"{len(files)} ファイルを変換しました: {args.output}")


def _run_combine(args: argparse.Namespace) -> None:
    """combine サブコマンドを実行する。"""
    config = CombineConfig(input_dir=args.input, output_file=args.output)
    outputs = combine(config)
    for output in outputs:
        print(f"結合ファイルを生成しました: {output}")


def _run_pipeline(args: argparse.Namespace) -> None:
    """pipeline サブコマンドを実行する。"""
    base_dir: Path = args.output
    html_dir = base_dir / "html"
    md_dir = base_dir / "md"
    combined_file = base_dir / "combined.md"

    # Step 1: Crawl
    print("=== Step 1/3: クロール ===")
    crawl_config = CrawlConfig(
        start_url=args.url,
        output_dir=html_dir,
        max_pages=args.max_pages,
        delay_seconds=args.delay,
    )
    crawled = crawl(crawl_config)
    print(f"{len(crawled)} ページを保存しました")

    # Step 2: Convert
    print("=== Step 2/3: 変換 ===")
    convert_config = ConvertConfig(input_dir=html_dir, output_dir=md_dir)
    converted = convert_directory(convert_config)
    print(f"{len(converted)} ファイルを変換しました")

    # Step 3: Combine
    print("=== Step 3/3: 結合 ===")
    combine_config = CombineConfig(input_dir=md_dir, output_file=combined_file)
    outputs = combine(combine_config)
    for output in outputs:
        print(f"結合ファイルを生成しました: {output}")


def main(argv: list[str] | None = None) -> None:
    """CLI のメインエントリポイント。

    Args:
        argv: コマンドライン引数。None の場合は sys.argv を使用。
    """
    parser = _build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s: %(message)s",
    )

    commands = {
        "crawl": _run_crawl,
        "convert": _run_convert,
        "combine": _run_combine,
        "pipeline": _run_pipeline,
    }
    commands[args.command](args)
