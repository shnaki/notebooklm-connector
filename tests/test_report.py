"""report モジュールのテスト。"""

import json
from pathlib import Path

import pytest

from notebooklm_connector.models import PipelineReport, StepResult
from notebooklm_connector.report import (
    _format_bytes,
    format_pipeline_summary,
    format_step_summary,
    read_report,
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


def test_read_report_roundtrip(tmp_path: Path) -> None:
    """write_report → read_report でラウンドトリップ検証。"""
    steps = [
        StepResult("クロール", 10, 1024, 5.0, "out/html"),
        StepResult("変換", 10, 512, 1.0, "out/md"),
    ]
    original = PipelineReport(steps=steps, total_elapsed_seconds=6.0)
    report_path = tmp_path / "report.json"

    write_report(original, report_path)
    restored = read_report(report_path)

    assert restored.total_elapsed_seconds == original.total_elapsed_seconds
    assert len(restored.steps) == len(original.steps)
    assert restored.steps[0].step_name == original.steps[0].step_name
    assert restored.steps[0].file_count == original.steps[0].file_count
    assert restored.crawl_failures == []
    assert restored.convert_failures == []


def test_read_report_with_failures(tmp_path: Path) -> None:
    """crawl_failures / convert_failures が正しく復元されること。"""
    steps = [StepResult("クロール", 1, 1024, 5.0, "out/html")]
    original = PipelineReport(
        steps=steps,
        total_elapsed_seconds=5.0,
        crawl_failures=["https://example.com/missing"],
        convert_failures=["output/html/page1.html"],
    )
    report_path = tmp_path / "report.json"

    write_report(original, report_path)
    restored = read_report(report_path)

    assert restored.crawl_failures == ["https://example.com/missing"]
    assert restored.convert_failures == ["output/html/page1.html"]


def test_read_report_file_not_found(tmp_path: Path) -> None:
    """存在しないファイルで OSError が発生すること。"""
    with pytest.raises(OSError):
        read_report(tmp_path / "nonexistent.json")


def test_read_report_invalid_json(tmp_path: Path) -> None:
    """不正 JSON で json.JSONDecodeError が発生すること。"""
    report_path = tmp_path / "report.json"
    report_path.write_text("not valid json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        read_report(report_path)


def test_read_report_missing_required_field(tmp_path: Path) -> None:
    """必須フィールドが欠落している場合に KeyError が発生すること。"""
    report_path = tmp_path / "report.json"
    data = {"steps": []}  # total_elapsed_seconds が欠落
    report_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(KeyError):
        read_report(report_path)


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


def test_write_report_with_command(tmp_path: Path) -> None:
    """command フィールドが正しくシリアライズされること。"""
    steps = [StepResult("クロール", 1, 1024, 5.0, "out/html")]
    report = PipelineReport(
        steps=steps,
        total_elapsed_seconds=5.0,
        command=["notebooklm-connector", "crawl", "https://example.com/", "-o", "out"],
    )
    report_path = tmp_path / "report.json"

    write_report(report, report_path)

    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["command"] == [
        "notebooklm-connector",
        "crawl",
        "https://example.com/",
        "-o",
        "out",
    ]


def test_read_report_with_command(tmp_path: Path) -> None:
    """command フィールドが正しく復元されること。"""
    steps = [StepResult("クロール", 1, 1024, 5.0, "out/html")]
    original = PipelineReport(
        steps=steps,
        total_elapsed_seconds=5.0,
        command=[
            "notebooklm-connector",
            "pipeline",
            "https://example.com/",
            "-o",
            "out",
        ],
    )
    report_path = tmp_path / "report.json"

    write_report(original, report_path)
    restored = read_report(report_path)

    assert restored.command == original.command


def test_read_report_command_defaults_empty(tmp_path: Path) -> None:
    """旧フォーマット（command なし）でも読み込めること。"""
    data = {
        "steps": [
            {
                "step_name": "クロール",
                "file_count": 1,
                "total_bytes": 1024,
                "elapsed_seconds": 5.0,
                "output_path": "out/html",
            }
        ],
        "total_elapsed_seconds": 5.0,
    }
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(data), encoding="utf-8")

    restored = read_report(report_path)

    assert restored.command == []


def test_write_report_with_output_word_counts(tmp_path: Path) -> None:
    """output_word_counts が正しくシリアライズされること。"""
    steps = [
        StepResult(
            "結合",
            2,
            1024,
            0.5,
            "out/combined.md",
            output_word_counts={
                "out/combined-001.md": 498000,
                "out/combined-002.md": 321000,
            },
        ),
    ]
    report = PipelineReport(steps=steps, total_elapsed_seconds=0.5)
    report_path = tmp_path / "report.json"

    write_report(report, report_path)

    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["steps"][0]["output_word_counts"] == {
        "out/combined-001.md": 498000,
        "out/combined-002.md": 321000,
    }


def test_read_report_with_output_word_counts(tmp_path: Path) -> None:
    """output_word_counts が正しく復元されること。"""
    steps = [
        StepResult(
            "結合",
            2,
            1024,
            0.5,
            "out/combined.md",
            output_word_counts={
                "out/combined-001.md": 498000,
                "out/combined-002.md": 321000,
            },
        ),
    ]
    original = PipelineReport(steps=steps, total_elapsed_seconds=0.5)
    report_path = tmp_path / "report.json"

    write_report(original, report_path)
    restored = read_report(report_path)

    assert restored.steps[0].output_word_counts == {
        "out/combined-001.md": 498000,
        "out/combined-002.md": 321000,
    }


def test_read_report_output_word_counts_defaults_empty(tmp_path: Path) -> None:
    """旧フォーマット（output_word_counts なし）でも読み込めること。"""
    data = {
        "steps": [
            {
                "step_name": "結合",
                "file_count": 1,
                "total_bytes": 1024,
                "elapsed_seconds": 0.5,
                "output_path": "out/combined.md",
            }
        ],
        "total_elapsed_seconds": 0.5,
    }
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(data), encoding="utf-8")

    restored = read_report(report_path)

    assert restored.steps[0].output_word_counts == {}
