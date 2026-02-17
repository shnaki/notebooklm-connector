"""CLI エントリポイント。

crawl / convert / combine / pipeline の 4 サブコマンドを提供する。
"""

import argparse
import logging
import sys
import time
from pathlib import Path

from notebooklm_connector.combiner import combine
from notebooklm_connector.converter import convert_directory, convert_zip
from notebooklm_connector.crawler import crawl
from notebooklm_connector.models import (
    CombineConfig,
    ConvertConfig,
    CrawlConfig,
    PipelineReport,
    StepResult,
)
from notebooklm_connector.report import format_step_summary, write_report

logger = logging.getLogger(__name__)


def _make_step_result(
    step_name: str,
    files: list[Path],
    elapsed: float,
    output_path: str,
) -> StepResult:
    """ファイルリストと経過時間から StepResult を生成する。

    Args:
        step_name: ステップ名。
        files: 出力ファイルのリスト。
        elapsed: 経過時間（秒）。
        output_path: 出力先パス文字列。

    Returns:
        StepResult インスタンス。
    """
    total_bytes = sum(f.stat().st_size for f in files if f.exists())
    return StepResult(
        step_name=step_name,
        file_count=len(files),
        total_bytes=total_bytes,
        elapsed_seconds=round(elapsed, 1),
        output_path=output_path,
    )


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
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="処理レポートを JSON ファイルに出力する",
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


def _run_crawl(args: argparse.Namespace) -> StepResult:
    """crawl サブコマンドを実行する。"""
    config = CrawlConfig(
        start_url=args.url,
        output_dir=args.output,
        max_pages=args.max_pages,
        delay_seconds=args.delay,
    )
    start = time.monotonic()
    files = crawl(config)
    elapsed = time.monotonic() - start
    result = _make_step_result("クロール", files, elapsed, str(args.output))
    print(format_step_summary(result))
    return result


def _run_convert(args: argparse.Namespace) -> StepResult:
    """convert サブコマンドを実行する。"""
    start = time.monotonic()
    if args.zip:
        files = convert_zip(args.input, args.output)
    else:
        config = ConvertConfig(input_dir=args.input, output_dir=args.output)
        files = convert_directory(config)
    elapsed = time.monotonic() - start
    result = _make_step_result("変換", files, elapsed, str(args.output))
    print(format_step_summary(result))
    return result


def _run_combine(args: argparse.Namespace) -> StepResult:
    """combine サブコマンドを実行する。"""
    config = CombineConfig(input_dir=args.input, output_file=args.output)
    start = time.monotonic()
    outputs = combine(config)
    elapsed = time.monotonic() - start
    result = _make_step_result("結合", outputs, elapsed, str(args.output))
    print(format_step_summary(result))
    return result


def _run_pipeline(args: argparse.Namespace) -> PipelineReport:
    """pipeline サブコマンドを実行する。"""
    base_dir: Path = args.output
    html_dir = base_dir / "html"
    md_dir = base_dir / "md"
    combined_file = base_dir / "combined.md"

    pipeline_start = time.monotonic()
    steps: list[StepResult] = []

    # Step 1: Crawl
    print("=== Step 1/3: クロール ===")
    crawl_config = CrawlConfig(
        start_url=args.url,
        output_dir=html_dir,
        max_pages=args.max_pages,
        delay_seconds=args.delay,
    )
    start = time.monotonic()
    crawled = crawl(crawl_config)
    elapsed = time.monotonic() - start
    step = _make_step_result("クロール", crawled, elapsed, str(html_dir))
    print(format_step_summary(step))
    steps.append(step)

    # Step 2: Convert
    print("=== Step 2/3: 変換 ===")
    convert_config = ConvertConfig(input_dir=html_dir, output_dir=md_dir)
    start = time.monotonic()
    converted = convert_directory(convert_config)
    elapsed = time.monotonic() - start
    step = _make_step_result("変換", converted, elapsed, str(md_dir))
    print(format_step_summary(step))
    steps.append(step)

    # Step 3: Combine
    print("=== Step 3/3: 結合 ===")
    combine_config = CombineConfig(input_dir=md_dir, output_file=combined_file)
    start = time.monotonic()
    outputs = combine(combine_config)
    elapsed = time.monotonic() - start
    step = _make_step_result("結合", outputs, elapsed, str(combined_file))
    print(format_step_summary(step))
    steps.append(step)

    # Summary
    total_elapsed = time.monotonic() - pipeline_start
    report = PipelineReport(steps=steps, total_elapsed_seconds=round(total_elapsed, 1))
    print("=== 完了 ===")
    print(f"合計: {report.total_elapsed_seconds:.1f} 秒, {len(report.steps)} ステップ")
    return report


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

    commands: dict[str, object] = {
        "crawl": _run_crawl,
        "convert": _run_convert,
        "combine": _run_combine,
        "pipeline": _run_pipeline,
    }
    result = commands[args.command](args)  # type: ignore[operator]

    if args.report is not None:
        if isinstance(result, StepResult):
            report = PipelineReport(
                steps=[result],
                total_elapsed_seconds=result.elapsed_seconds,
            )
        elif isinstance(result, PipelineReport):
            report = result
        else:
            return
        write_report(report, args.report)
        print(f"レポートを保存しました: {args.report}")
