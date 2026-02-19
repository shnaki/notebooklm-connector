"""処理結果サマリーのフォーマットとレポートファイル出力。"""

import dataclasses
import json
from pathlib import Path

from notebooklm_connector.models import PipelineReport, StepResult


def build_step_result(
    step_name: str,
    files: list[Path],
    output_path: str,
    elapsed_seconds: float | None = None,
    skipped_count: int = 0,
    downloaded_count: int = 0,
    failure_count: int = 0,
    output_word_counts: dict[str, int] | None = None,
) -> StepResult:
    """ファイル群から StepResult を構築する。

    Args:
        step_name: ステップ名。
        files: 出力ファイル一覧。
        output_path: 出力先パス文字列。
        elapsed_seconds: 経過時間（秒）。None の場合は 0.0。
        skipped_count: キャッシュヒット数。
        downloaded_count: ダウンロード数。
        failure_count: 失敗件数。
        output_word_counts: 結合出力ファイルごとの語数。

    Returns:
        集計済み StepResult。
    """
    total_bytes = sum(path.stat().st_size for path in files if path.exists())
    elapsed = 0.0 if elapsed_seconds is None else elapsed_seconds
    return StepResult(
        step_name=step_name,
        file_count=len(files),
        total_bytes=total_bytes,
        elapsed_seconds=round(elapsed, 1),
        output_path=output_path.replace("\\", "/"),
        skipped_count=skipped_count,
        downloaded_count=downloaded_count,
        failure_count=failure_count,
        output_word_counts={} if output_word_counts is None else output_word_counts,
    )


def _format_bytes(size: int) -> str:
    """バイト数を人間が読みやすい形式に変換する。

    Args:
        size: バイト数。

    Returns:
        フォーマットされた文字列（例: "2.3 MB"）。
    """
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / (1024 * 1024 * 1024):.1f} GB"


def format_step_summary(result: StepResult) -> str:
    """ステップ結果を1行サマリー文字列にフォーマットする。

    Args:
        result: ステップの処理結果。

    Returns:
        サマリー文字列（例: "クロール: 15 ファイル (2.3 MB), 45.2 秒 → output/html"）。
    """
    size_str = _format_bytes(result.total_bytes)
    return (
        f"{result.step_name}: {result.file_count} ファイル"
        f" ({size_str}), {result.elapsed_seconds:.1f} 秒"
        f" → {result.output_path}"
    )


def format_pipeline_summary(report: PipelineReport) -> str:
    """パイプライン全体のサマリー文字列を生成する。

    Args:
        report: パイプラインの処理レポート。

    Returns:
        全ステップのサマリーと合計行を含む文字列。
    """
    lines: list[str] = []
    for step in report.steps:
        lines.append(format_step_summary(step))
    lines.append(
        f"合計: {report.total_elapsed_seconds:.1f} 秒, {len(report.steps)} ステップ"
    )
    return "\n".join(lines)


def read_report(path: Path) -> PipelineReport:
    """JSON ファイルからレポートを読み込む。

    Args:
        path: 読み込むレポートファイルのパス。

    Returns:
        PipelineReport インスタンス。

    Raises:
        OSError: ファイルの読み取りに失敗した場合。
        json.JSONDecodeError: JSON のパースに失敗した場合。
        KeyError: 必須フィールドが存在しない場合。
    """
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    steps = [StepResult(**s) for s in data["steps"]]
    return PipelineReport(
        steps=steps,
        total_elapsed_seconds=data["total_elapsed_seconds"],
        crawl_failures=data.get("crawl_failures", []),
        convert_failures=data.get("convert_failures", []),
        command=data.get("command", ""),
    )


def write_report(report: PipelineReport, path: Path) -> None:
    """レポートをJSONファイルに出力する。

    Args:
        report: パイプラインの処理レポート。
        path: 出力先ファイルパス。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = dataclasses.asdict(report)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
