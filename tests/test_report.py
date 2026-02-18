"""report モジュールのテスト。"""

import json
from pathlib import Path

from notebooklm_connector.models import PipelineReport, StepResult
from notebooklm_connector.report import (
    _format_bytes,
    format_pipeline_summary,
    format_step_summary,
    write_report,
)


def test_format_bytes_b() -> None:
    """バイト単位の表示。"""
    assert _format_bytes(0) == "0 B"
    assert _format_bytes(512) == "512 B"
    assert _format_bytes(1023) == "1023 B"


def test_format_bytes_kb() -> None:
    """KB 単位の表示。"""
    assert _format_bytes(1024) == "1.0 KB"
    assert _format_bytes(2560) == "2.5 KB"


def test_format_bytes_mb() -> None:
    """MB 単位の表示。"""
    assert _format_bytes(1024 * 1024) == "1.0 MB"
    assert _format_bytes(int(2.3 * 1024 * 1024)) == "2.3 MB"


def test_format_bytes_gb() -> None:
    """GB 単位の表示。"""
    assert _format_bytes(1024 * 1024 * 1024) == "1.0 GB"
    assert _format_bytes(int(1.5 * 1024 * 1024 * 1024)) == "1.5 GB"


def test_format_step_summary() -> None:
    """ステップサマリーの内容検証。"""
    result = StepResult(
        step_name="クロール",
        file_count=15,
        total_bytes=int(2.3 * 1024 * 1024),
        elapsed_seconds=45.2,
        output_path="output/html",
    )
    summary = format_step_summary(result)
    assert "クロール" in summary
    assert "15 ファイル" in summary
    assert "2.3 MB" in summary
    assert "45.2 秒" in summary
    assert "output/html" in summary


def test_format_pipeline_summary() -> None:
    """パイプラインサマリーの内容検証。"""
    steps = [
        StepResult("クロール", 15, 2 * 1024 * 1024, 45.2, "output/html"),
        StepResult("変換", 15, 300 * 1024, 2.2, "output/md"),
        StepResult("結合", 1, 290 * 1024, 0.3, "output/combined.md"),
    ]
    report = PipelineReport(steps=steps, total_elapsed_seconds=47.7)
    summary = format_pipeline_summary(report)

    assert "クロール" in summary
    assert "変換" in summary
    assert "結合" in summary
    assert "47.7 秒" in summary
    assert "3 ステップ" in summary


def test_write_report(tmp_path: Path) -> None:
    """JSON レポート出力の構造・値検証。"""
    steps = [
        StepResult("クロール", 10, 1024, 5.0, "out/html"),
        StepResult("変換", 10, 512, 1.0, "out/md"),
    ]
    report = PipelineReport(steps=steps, total_elapsed_seconds=6.0)
    report_path = tmp_path / "sub" / "report.json"

    write_report(report, report_path)

    assert report_path.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["total_elapsed_seconds"] == 6.0
    assert len(data["steps"]) == 2
    assert data["steps"][0]["step_name"] == "クロール"
    assert data["steps"][0]["file_count"] == 10
    assert data["steps"][0]["total_bytes"] == 1024
    assert data["steps"][1]["step_name"] == "変換"
    assert data["steps"][0]["skipped_count"] == 0
    assert data["crawl_failures"] == []
    assert data["convert_failures"] == []


def test_write_report_with_failures(tmp_path: Path) -> None:
    """失敗リストが正しくシリアライズされること。"""
    steps = [
        StepResult(
            "クロール",
            1,
            1024,
            5.0,
            "out/html",
            skipped_count=0,
            downloaded_count=1,
            failure_count=1,
        ),
    ]
    report = PipelineReport(
        steps=steps,
        total_elapsed_seconds=5.0,
        crawl_failures=["https://example.com/missing"],
        convert_failures=["output/html/page1.html"],
    )
    report_path = tmp_path / "report.json"

    write_report(report, report_path)

    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["crawl_failures"] == ["https://example.com/missing"]
    assert data["convert_failures"] == ["output/html/page1.html"]
    assert data["steps"][0]["skipped_count"] == 0
    assert data["steps"][0]["downloaded_count"] == 1
    assert data["steps"][0]["failure_count"] == 1
