"""CLI エントリポイント。

crawl / convert / combine / pipeline の 4 サブコマンドを提供する。
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any, cast

from notebooklm_connector.combiner import combine
from notebooklm_connector.converter import (
    convert_directory,
    convert_failed_files,
    convert_zip,
)
from notebooklm_connector.crawler import crawl, crawl_urls
from notebooklm_connector.models import (
    CombineConfig,
    ConvertConfig,
    CrawlConfig,
    PipelineReport,
    StepResult,
)
from notebooklm_connector.report import format_step_summary, read_report, write_report

logger = logging.getLogger(__name__)


def _make_step_result(
    step_name: str,
    files: list[Path],
    elapsed: float,
    output_path: str,
    skipped_count: int = 0,
    downloaded_count: int = 0,
    failure_count: int = 0,
    output_word_counts: dict[str, int] | None = None,
) -> StepResult:
    """ファイルリストと経過時間から StepResult を生成する。

    Args:
        step_name: ステップ名。
        files: 出力ファイルのリスト。
        elapsed: 経過時間（秒）。
        output_path: 出力先パス文字列。
        skipped_count: キャッシュヒット数。
        downloaded_count: ダウンロード数。
        failure_count: 失敗数。
        output_word_counts: 結合ステップの出力ファイル毎の語句数。

    Returns:
        StepResult インスタンス。
    """
    total_bytes = sum(f.stat().st_size for f in files if f.exists())
    return StepResult(
        step_name=step_name,
        file_count=len(files),
        total_bytes=total_bytes,
        elapsed_seconds=round(elapsed, 1),
        output_path=output_path.replace("\\", "/"),
        skipped_count=skipped_count,
        downloaded_count=downloaded_count,
        failure_count=failure_count,
        output_word_counts=output_word_counts if output_word_counts is not None else {},
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
    crawl_parser.add_argument(
        "--max-concurrency",
        type=int,
        default=5,
        help="並列クロール数 (デフォルト: 5)",
    )
    crawl_parser.add_argument(
        "--retry-from-report",
        type=Path,
        default=None,
        metavar="REPORT_JSON",
        help="前回実行のレポート JSON から crawl_failures のみ再クロールする",
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
    convert_parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="並列変換ワーカー数 (デフォルト: CPU コア数)",
    )
    convert_parser.add_argument(
        "--retry-from-report",
        type=Path,
        default=None,
        metavar="REPORT_JSON",
        help="前回実行のレポート JSON から convert_failures のみ再変換する",
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
    pipeline_parser.add_argument(
        "--max-concurrency",
        type=int,
        default=5,
        help="並列クロール数 (デフォルト: 5)",
    )
    pipeline_parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="並列変換ワーカー数 (デフォルト: CPU コア数)",
    )
    pipeline_parser.add_argument(
        "--retry-from-report",
        type=Path,
        default=None,
        metavar="REPORT_JSON",
        help="前回実行のレポート JSON から失敗分のみ再実行する",
    )

    return parser


def _run_crawl(args: argparse.Namespace) -> tuple[StepResult, list[str]]:
    """crawl サブコマンドを実行する。"""
    config = CrawlConfig(
        start_url=args.url,
        output_dir=args.output,
        max_pages=args.max_pages,
        delay_seconds=args.delay,
        max_concurrency=args.max_concurrency,
    )
    retry_report_path: Path | None = args.retry_from_report
    start = time.monotonic()
    if retry_report_path is not None:
        prev_report = read_report(retry_report_path)
        files, skipped, downloaded, failed_urls = crawl_urls(
            prev_report.crawl_failures, config
        )
    else:
        files, skipped, downloaded, failed_urls = crawl(config)
    elapsed = time.monotonic() - start
    result = _make_step_result(
        "クロール",
        files,
        elapsed,
        str(args.output),
        skipped_count=skipped,
        downloaded_count=downloaded,
        failure_count=len(failed_urls),
    )
    print(format_step_summary(result))
    return result, failed_urls


def _run_convert(args: argparse.Namespace) -> tuple[StepResult, list[str]]:
    """convert サブコマンドを実行する。"""
    retry_report_path: Path | None = args.retry_from_report
    start = time.monotonic()
    if retry_report_path is not None:
        prev_report = read_report(retry_report_path)
        config = ConvertConfig(
            input_dir=args.input,
            output_dir=args.output,
            max_workers=args.max_workers,
        )
        files, failed_files = convert_failed_files(prev_report.convert_failures, config)
    elif args.zip:
        config = ConvertConfig(
            input_dir=Path("."),
            output_dir=args.output,
            max_workers=args.max_workers,
        )
        files, failed_files = convert_zip(args.input, args.output, config=config)
    else:
        config = ConvertConfig(
            input_dir=args.input,
            output_dir=args.output,
            max_workers=args.max_workers,
        )
        files, failed_files = convert_directory(config)
    elapsed = time.monotonic() - start
    result = _make_step_result(
        "変換",
        files,
        elapsed,
        str(args.output),
        failure_count=len(failed_files),
    )
    print(format_step_summary(result))
    return result, failed_files


def _run_combine(args: argparse.Namespace) -> StepResult:
    """combine サブコマンドを実行する。"""
    config = CombineConfig(input_dir=args.input, output_file=args.output)
    start = time.monotonic()
    outputs, word_counts = combine(config)
    elapsed = time.monotonic() - start
    result = _make_step_result(
        "結合", outputs, elapsed, str(args.output), output_word_counts=word_counts
    )
    print(format_step_summary(result))
    return result


def _run_pipeline(args: argparse.Namespace) -> PipelineReport:
    """pipeline サブコマンドを実行する。"""
    base_dir: Path = args.output
    html_dir = base_dir / "html"
    md_dir = base_dir / "md"
    combined_file = base_dir / "combined.md"
    retry_report_path: Path | None = args.retry_from_report

    pipeline_start = time.monotonic()
    steps: list[StepResult] = []

    crawl_config = CrawlConfig(
        start_url=args.url,
        output_dir=html_dir,
        max_pages=args.max_pages,
        delay_seconds=args.delay,
        max_concurrency=args.max_concurrency,
    )
    convert_config = ConvertConfig(
        input_dir=html_dir,
        output_dir=md_dir,
        max_workers=args.max_workers,
    )
    combine_config = CombineConfig(input_dir=md_dir, output_file=combined_file)

    crawl_failed: list[str] = []
    convert_failed: list[str] = []

    if retry_report_path is not None:
        prev_report = read_report(retry_report_path)

        # Step 1: Crawl (リトライ)
        print("=== Step 1/3: クロール (リトライ) ===")
        start = time.monotonic()
        crawled, crawl_skipped, crawl_downloaded, crawl_failed = crawl_urls(
            prev_report.crawl_failures, crawl_config
        )
        elapsed = time.monotonic() - start
        step = _make_step_result(
            "クロール",
            crawled,
            elapsed,
            str(html_dir),
            skipped_count=crawl_skipped,
            downloaded_count=crawl_downloaded,
            failure_count=len(crawl_failed),
        )
        print(format_step_summary(step))
        steps.append(step)

        # Step 2: Convert (リトライ: 前回変換失敗 + 新規クロール分)
        print("=== Step 2/3: 変換 (リトライ) ===")
        convert_targets = prev_report.convert_failures + [p.as_posix() for p in crawled]
        start = time.monotonic()
        converted, convert_failed = convert_failed_files(
            convert_targets, convert_config
        )
        elapsed = time.monotonic() - start
        step = _make_step_result(
            "変換",
            converted,
            elapsed,
            str(md_dir),
            failure_count=len(convert_failed),
        )
        print(format_step_summary(step))
        steps.append(step)

    else:
        # Step 1: Crawl
        print("=== Step 1/3: クロール ===")
        start = time.monotonic()
        crawled, crawl_skipped, crawl_downloaded, crawl_failed = crawl(crawl_config)
        elapsed = time.monotonic() - start
        step = _make_step_result(
            "クロール",
            crawled,
            elapsed,
            str(html_dir),
            skipped_count=crawl_skipped,
            downloaded_count=crawl_downloaded,
            failure_count=len(crawl_failed),
        )
        print(format_step_summary(step))
        steps.append(step)

        # Step 2: Convert
        print("=== Step 2/3: 変換 ===")
        start = time.monotonic()
        converted, convert_failed = convert_directory(convert_config)
        elapsed = time.monotonic() - start
        step = _make_step_result(
            "変換",
            converted,
            elapsed,
            str(md_dir),
            failure_count=len(convert_failed),
        )
        print(format_step_summary(step))
        steps.append(step)

    # Step 3: Combine
    print("=== Step 3/3: 結合 ===")
    start = time.monotonic()
    outputs, word_counts = combine(combine_config)
    elapsed = time.monotonic() - start
    step = _make_step_result(
        "結合", outputs, elapsed, str(combined_file), output_word_counts=word_counts
    )
    print(format_step_summary(step))
    steps.append(step)

    # Summary
    total_elapsed = time.monotonic() - pipeline_start
    report = PipelineReport(
        steps=steps,
        total_elapsed_seconds=round(total_elapsed, 1),
        crawl_failures=crawl_failed,
        convert_failures=convert_failed,
    )
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
    raw_args = argv if argv is not None else sys.argv[1:]
    command = "notebooklm-connector " + " ".join(a.replace("\\", "/") for a in raw_args)

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
    result: Any = commands[args.command](args)  # type: ignore[operator]

    if args.report is not None:
        if isinstance(result, tuple):
            step_result, failures = cast(tuple[StepResult, list[str]], result)
            crawl_failures: list[str] = failures if args.command == "crawl" else []
            convert_failures: list[str] = failures if args.command == "convert" else []
            report = PipelineReport(
                steps=[step_result],
                total_elapsed_seconds=step_result.elapsed_seconds,
                crawl_failures=crawl_failures,
                convert_failures=convert_failures,
                command=command,
            )
        elif isinstance(result, StepResult):
            report = PipelineReport(
                steps=[result],
                total_elapsed_seconds=result.elapsed_seconds,
                command=command,
            )
        elif isinstance(result, PipelineReport):
            result.command = command
            report = result
        else:
            return
        write_report(report, args.report)
        print(f"レポートを保存しました: {args.report}")
