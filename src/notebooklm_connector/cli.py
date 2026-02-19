"""CLI エントリポイント。

crawl / convert / combine / pipeline の 4 サブコマンドを提供する。
"""

import argparse
import logging
import sys
import time
from collections.abc import Callable
from pathlib import Path

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
from notebooklm_connector.report import (
    build_step_result,
    format_step_summary,
    read_report,
    write_report,
)

logger = logging.getLogger(__name__)
CommandResult = StepResult | PipelineReport | tuple[StepResult, list[str]]
CommandHandler = Callable[[argparse.Namespace], CommandResult]


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
    config = _build_crawl_config(args.url, args.output, args)
    files, skipped, downloaded, failed_urls = _run_crawl_job(
        config, args.retry_from_report
    )
    result = build_step_result(
        "クロール",
        files,
        str(args.output),
        skipped_count=skipped,
        downloaded_count=downloaded,
        failure_count=len(failed_urls),
    )
    print(format_step_summary(result))
    return result, failed_urls


def _run_convert(args: argparse.Namespace) -> tuple[StepResult, list[str]]:
    """convert サブコマンドを実行する。"""
    config = _build_convert_config(args.input, args.output, args.max_workers)
    files, failed_files = _run_convert_job(
        config=config,
        retry_report_path=args.retry_from_report,
        zip_input=args.input if args.zip else None,
    )
    result = build_step_result(
        "変換",
        files,
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
    result = build_step_result(
        "結合",
        outputs,
        str(args.output),
        elapsed_seconds=elapsed,
        output_word_counts=word_counts,
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

    crawl_config = _build_crawl_config(args.url, html_dir, args)
    convert_config = _build_convert_config(html_dir, md_dir, args.max_workers)
    combine_config = CombineConfig(input_dir=md_dir, output_file=combined_file)

    crawl_failed: list[str] = []
    convert_failed: list[str] = []

    if retry_report_path is not None:
        prev_report = read_report(retry_report_path)

        # Step 1: Crawl (リトライ)
        print("=== Step 1/3: クロール (リトライ) ===")
        (
            crawl_step,
            crawled,
            crawl_failed,
        ) = _run_pipeline_crawl_step(
            crawl_config,
            html_dir,
            retry_urls=prev_report.crawl_failures,
        )
        steps.append(crawl_step)

        # Step 2: Convert (リトライ: 前回変換失敗 + 新規クロール分)
        print("=== Step 2/3: 変換 (リトライ) ===")
        convert_targets = prev_report.convert_failures + [p.as_posix() for p in crawled]
        (
            convert_step,
            convert_failed,
        ) = _run_pipeline_convert_step(
            convert_config,
            md_dir,
            retry_targets=convert_targets,
        )
        steps.append(convert_step)

    else:
        # Step 1: Crawl
        print("=== Step 1/3: クロール ===")
        crawl_step, _crawled, crawl_failed = _run_pipeline_crawl_step(
            crawl_config,
            html_dir,
        )
        steps.append(crawl_step)

        # Step 2: Convert
        print("=== Step 2/3: 変換 ===")
        convert_step, convert_failed = _run_pipeline_convert_step(
            convert_config, md_dir
        )
        steps.append(convert_step)

    # Step 3: Combine
    print("=== Step 3/3: 結合 ===")
    start = time.monotonic()
    outputs, word_counts = combine(combine_config)
    elapsed = time.monotonic() - start
    step = build_step_result(
        "結合",
        outputs,
        str(combined_file),
        elapsed_seconds=elapsed,
        output_word_counts=word_counts,
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


def _build_crawl_config(
    start_url: str, output_dir: Path, args: argparse.Namespace
) -> CrawlConfig:
    """CLI 引数から CrawlConfig を構築する。"""
    return CrawlConfig(
        start_url=start_url,
        output_dir=output_dir,
        max_pages=args.max_pages,
        delay_seconds=args.delay,
        max_concurrency=args.max_concurrency,
    )


def _build_convert_config(
    input_dir: Path,
    output_dir: Path,
    max_workers: int | None,
) -> ConvertConfig:
    """CLI 引数から ConvertConfig を構築する。"""
    return ConvertConfig(
        input_dir=input_dir,
        output_dir=output_dir,
        max_workers=max_workers,
    )


def _run_crawl_job(
    config: CrawlConfig,
    retry_report_path: Path | None = None,
) -> tuple[list[Path], int, int, list[str]]:
    """クロール処理を実行し、結果タプルを返す。"""
    if retry_report_path is None:
        files, skipped, downloaded, failed_urls = crawl(config)
    else:
        prev_report = read_report(retry_report_path)
        files, skipped, downloaded, failed_urls = crawl_urls(
            prev_report.crawl_failures, config
        )
    return files, skipped, downloaded, failed_urls


def _run_convert_job(
    config: ConvertConfig,
    retry_report_path: Path | None = None,
    zip_input: Path | None = None,
) -> tuple[list[Path], list[str]]:
    """変換処理を実行し、成功ファイルと失敗一覧を返す。"""
    if retry_report_path is not None:
        prev_report = read_report(retry_report_path)
        return convert_failed_files(prev_report.convert_failures, config)
    if zip_input is not None:
        return convert_zip(zip_input, config.output_dir, config=config)
    return convert_directory(config)


def _run_pipeline_crawl_step(
    crawl_config: CrawlConfig,
    output_dir: Path,
    retry_urls: list[str] | None = None,
) -> tuple[StepResult, list[Path], list[str]]:
    """pipeline 用の crawl ステップを実行する。"""
    start = time.monotonic()
    if retry_urls is None:
        crawled, crawl_skipped, crawl_downloaded, crawl_failed = crawl(crawl_config)
    else:
        crawled, crawl_skipped, crawl_downloaded, crawl_failed = crawl_urls(
            retry_urls, crawl_config
        )
    step = build_step_result(
        "クロール",
        crawled,
        str(output_dir),
        elapsed_seconds=time.monotonic() - start,
        skipped_count=crawl_skipped,
        downloaded_count=crawl_downloaded,
        failure_count=len(crawl_failed),
    )
    print(format_step_summary(step))
    return step, crawled, crawl_failed


def _run_pipeline_convert_step(
    convert_config: ConvertConfig,
    output_dir: Path,
    retry_targets: list[str] | None = None,
) -> tuple[StepResult, list[str]]:
    """pipeline 用の convert ステップを実行する。"""
    start = time.monotonic()
    if retry_targets is None:
        converted, convert_failed = convert_directory(convert_config)
    else:
        converted, convert_failed = convert_failed_files(retry_targets, convert_config)
    step = build_step_result(
        "変換",
        converted,
        str(output_dir),
        elapsed_seconds=time.monotonic() - start,
        failure_count=len(convert_failed),
    )
    print(format_step_summary(step))
    return step, convert_failed


def _build_report(
    result: CommandResult,
    command_name: str,
    command: str,
) -> PipelineReport:
    """コマンド実行結果から PipelineReport を構築する。"""
    if isinstance(result, tuple):
        step_result, failures = result
        crawl_failures: list[str] = failures if command_name == "crawl" else []
        convert_failures: list[str] = failures if command_name == "convert" else []
        return PipelineReport(
            steps=[step_result],
            total_elapsed_seconds=step_result.elapsed_seconds,
            crawl_failures=crawl_failures,
            convert_failures=convert_failures,
            command=command,
        )

    if isinstance(result, StepResult):
        return PipelineReport(
            steps=[result],
            total_elapsed_seconds=result.elapsed_seconds,
            command=command,
        )

    result.command = command
    return result


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

    commands: dict[str, CommandHandler] = {
        "crawl": _run_crawl,
        "convert": _run_convert,
        "combine": _run_combine,
        "pipeline": _run_pipeline,
    }
    command_handler = commands.get(args.command)
    if command_handler is None:
        parser.error(f"Unknown command: {args.command}")
    result = command_handler(args)

    if args.report is not None:
        report = _build_report(result, args.command, command)
        write_report(report, args.report)
        print(f"レポートを保存しました: {args.report}")
