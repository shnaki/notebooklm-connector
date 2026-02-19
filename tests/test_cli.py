"""cli モジュールのテスト。"""

import json
from pathlib import Path
from unittest.mock import patch

import httpx

from notebooklm_connector.cli import main
from notebooklm_connector.models import PipelineReport, StepResult
from notebooklm_connector.report import write_report


def _mock_handler(request: httpx.Request) -> httpx.Response:
    """テスト用モック HTTP ハンドラ。"""
    return httpx.Response(
        200,
        text="<html><body><main><h1>Mock Page</h1></main></body></html>",
        headers={"content-type": "text/html; charset=utf-8"},
    )


def test_cli_crawl(tmp_path: Path) -> None:
    """crawl サブコマンドが動作すること。"""
    output_dir = tmp_path / "html"
    mock_client = httpx.Client(transport=httpx.MockTransport(_mock_handler))

    with patch(
        "notebooklm_connector.crawler.httpx.Client",
        return_value=mock_client,
    ):
        main(
            [
                "crawl",
                "https://example.com/docs/",
                "-o",
                str(output_dir),
                "--max-pages",
                "1",
                "--delay",
                "0",
            ]
        )

    assert output_dir.exists()
    html_files = list(output_dir.glob("*.html"))
    assert len(html_files) >= 1


def test_cli_convert(tmp_path: Path) -> None:
    """convert サブコマンドが動作すること。"""
    input_dir = tmp_path / "html"
    output_dir = tmp_path / "md"
    input_dir.mkdir()
    (input_dir / "page.html").write_text("<main><h1>Test</h1></main>", encoding="utf-8")

    main(["convert", str(input_dir), "-o", str(output_dir)])

    md_files = list(output_dir.glob("*.md"))
    assert len(md_files) == 1


def test_cli_combine(tmp_path: Path) -> None:
    """combine サブコマンドが動作すること。"""
    input_dir = tmp_path / "md"
    input_dir.mkdir()
    (input_dir / "page.md").write_text("# Test\n", encoding="utf-8")

    output_file = tmp_path / "combined.md"
    main(["combine", str(input_dir), "-o", str(output_file)])

    assert output_file.exists()
    assert "Test" in output_file.read_text(encoding="utf-8")


def test_cli_pipeline(tmp_path: Path) -> None:
    """pipeline サブコマンドが動作すること。"""
    output_dir = tmp_path / "output"
    mock_client = httpx.Client(transport=httpx.MockTransport(_mock_handler))

    with patch(
        "notebooklm_connector.crawler.httpx.Client",
        return_value=mock_client,
    ):
        main(
            [
                "pipeline",
                "https://example.com/docs/",
                "-o",
                str(output_dir),
                "--max-pages",
                "1",
                "--delay",
                "0",
            ]
        )

    assert (output_dir / "html").exists()
    assert (output_dir / "md").exists()
    assert (output_dir / "combined.md").exists()


def test_cli_convert_zip(tmp_path: Path) -> None:
    """convert --zip が動作すること。"""
    import zipfile

    zip_path = tmp_path / "docs.zip"
    output_dir = tmp_path / "md"

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("page.html", "<main><h1>From ZIP</h1></main>")

    main(
        [
            "convert",
            str(zip_path),
            "-o",
            str(output_dir),
            "--zip",
        ]
    )

    md_files = list(output_dir.glob("*.md"))
    assert len(md_files) == 1


def test_cli_pipeline_with_report(tmp_path: Path) -> None:
    """--report オプション付きパイプラインで JSON レポートが生成されること。"""
    output_dir = tmp_path / "output"
    report_path = tmp_path / "report.json"
    mock_client = httpx.Client(transport=httpx.MockTransport(_mock_handler))

    with patch(
        "notebooklm_connector.crawler.httpx.Client",
        return_value=mock_client,
    ):
        main(
            [
                "--report",
                str(report_path),
                "pipeline",
                "https://example.com/docs/",
                "-o",
                str(output_dir),
                "--max-pages",
                "1",
                "--delay",
                "0",
            ]
        )

    assert report_path.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert len(data["steps"]) == 3
    assert data["steps"][0]["step_name"] == "クロール"
    assert data["steps"][1]["step_name"] == "変換"
    assert data["steps"][2]["step_name"] == "結合"
    assert data["total_elapsed_seconds"] >= 0
    assert data["crawl_failures"] == []
    assert data["convert_failures"] == []
    assert data["steps"][0]["skipped_count"] == 0
    assert data["steps"][0]["downloaded_count"] == 1
    assert "/" in data["steps"][0]["output_path"]


def test_cli_crawl_with_report(tmp_path: Path) -> None:
    """crawl + --report で JSON に crawl_failures キーが含まれること。"""
    output_dir = tmp_path / "html"
    report_path = tmp_path / "report.json"
    mock_client = httpx.Client(transport=httpx.MockTransport(_mock_handler))

    with patch(
        "notebooklm_connector.crawler.httpx.Client",
        return_value=mock_client,
    ):
        main(
            [
                "--report",
                str(report_path),
                "crawl",
                "https://example.com/docs/",
                "-o",
                str(output_dir),
                "--max-pages",
                "1",
                "--delay",
                "0",
            ]
        )

    assert report_path.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert "crawl_failures" in data
    assert data["crawl_failures"] == []


def test_cli_crawl_retry_from_report(tmp_path: Path) -> None:
    """crawl --retry-from-report で失敗 URL が再クロールされること。"""
    prev_report = PipelineReport(
        steps=[StepResult("クロール", 1, 1024, 5.0, "out/html")],
        total_elapsed_seconds=5.0,
        crawl_failures=["https://example.com/docs/"],
    )
    report_path = tmp_path / "report.json"
    write_report(prev_report, report_path)

    output_dir = tmp_path / "html"
    mock_client = httpx.Client(transport=httpx.MockTransport(_mock_handler))

    with patch("notebooklm_connector.crawler.httpx.Client", return_value=mock_client):
        main(
            [
                "crawl",
                "https://example.com/docs/",
                "-o",
                str(output_dir),
                "--delay",
                "0",
                "--retry-from-report",
                str(report_path),
            ]
        )

    html_files = list(output_dir.glob("*.html"))
    assert len(html_files) >= 1


def test_cli_convert_retry_from_report(tmp_path: Path) -> None:
    """convert --retry-from-report で失敗ファイルが再変換されること。"""
    input_dir = tmp_path / "html"
    output_dir = tmp_path / "md"
    input_dir.mkdir()

    html_file = input_dir / "page.html"
    html_file.write_text("<main><h1>Retry Page</h1></main>", encoding="utf-8")

    prev_report = PipelineReport(
        steps=[StepResult("変換", 0, 0, 1.0, "out/md")],
        total_elapsed_seconds=1.0,
        convert_failures=[html_file.as_posix()],
    )
    report_path = tmp_path / "report.json"
    write_report(prev_report, report_path)

    main(
        [
            "convert",
            str(input_dir),
            "-o",
            str(output_dir),
            "--retry-from-report",
            str(report_path),
        ]
    )

    md_files = list(output_dir.glob("*.md"))
    assert len(md_files) == 1
    assert "Retry Page" in md_files[0].read_text(encoding="utf-8")


def test_cli_pipeline_retry_from_report(tmp_path: Path) -> None:
    """pipeline --retry-from-report で失敗分が再実行されること。"""
    base_dir = tmp_path / "output"
    html_dir = base_dir / "html"
    md_dir = base_dir / "md"
    html_dir.mkdir(parents=True)
    md_dir.mkdir(parents=True)

    html_file = html_dir / "page.html"
    html_file.write_text("<main><h1>Retry</h1></main>", encoding="utf-8")

    prev_report = PipelineReport(
        steps=[
            StepResult("クロール", 1, 1024, 5.0, str(html_dir)),
            StepResult("変換", 0, 0, 1.0, str(md_dir)),
        ],
        total_elapsed_seconds=6.0,
        crawl_failures=[],
        convert_failures=[html_file.as_posix()],
    )
    report_path = tmp_path / "report.json"
    write_report(prev_report, report_path)

    mock_client = httpx.Client(transport=httpx.MockTransport(_mock_handler))

    with patch("notebooklm_connector.crawler.httpx.Client", return_value=mock_client):
        main(
            [
                "pipeline",
                "https://example.com/docs/",
                "-o",
                str(base_dir),
                "--delay",
                "0",
                "--retry-from-report",
                str(report_path),
            ]
        )

    assert (base_dir / "combined.md").exists()
    combined = (base_dir / "combined.md").read_text(encoding="utf-8")
    assert "Retry" in combined


def test_cli_crawl_retry_empty_failures(tmp_path: Path) -> None:
    """crawl_failures が空のレポートで正常終了すること。"""
    prev_report = PipelineReport(
        steps=[StepResult("クロール", 1, 1024, 5.0, "out/html")],
        total_elapsed_seconds=5.0,
        crawl_failures=[],
    )
    report_path = tmp_path / "report.json"
    write_report(prev_report, report_path)

    output_dir = tmp_path / "html"
    main(
        [
            "crawl",
            "https://example.com/docs/",
            "-o",
            str(output_dir),
            "--delay",
            "0",
            "--retry-from-report",
            str(report_path),
        ]
    )

    html_files = list(output_dir.glob("*.html")) if output_dir.exists() else []
    assert html_files == []


def test_cli_convert_with_report(tmp_path: Path) -> None:
    """convert + --report で JSON に convert_failures キーが含まれること。"""
    input_dir = tmp_path / "html"
    output_dir = tmp_path / "md"
    input_dir.mkdir()
    (input_dir / "page.html").write_text("<main><h1>Test</h1></main>", encoding="utf-8")

    report_path = tmp_path / "report.json"
    main(
        [
            "--report",
            str(report_path),
            "convert",
            str(input_dir),
            "-o",
            str(output_dir),
        ]
    )

    assert report_path.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert "convert_failures" in data
    assert data["convert_failures"] == []


def test_cli_pipeline_report_has_command(tmp_path: Path) -> None:
    """pipeline + --report で JSON に command が含まれること。"""
    output_dir = tmp_path / "output"
    report_path = tmp_path / "report.json"
    mock_client = httpx.Client(transport=httpx.MockTransport(_mock_handler))

    argv = [
        "--report",
        str(report_path),
        "pipeline",
        "https://example.com/docs/",
        "-o",
        str(output_dir),
        "--max-pages",
        "1",
        "--delay",
        "0",
    ]
    with patch(
        "notebooklm_connector.crawler.httpx.Client",
        return_value=mock_client,
    ):
        main(argv)

    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert "command" in data
    assert data["command"].startswith("notebooklm-connector")
    assert "pipeline" in data["command"]
    assert "https://example.com/docs/" in data["command"]


def test_cli_combine_report_has_word_counts(tmp_path: Path) -> None:
    """combine + --report で JSON に output_word_counts が含まれること。"""
    input_dir = tmp_path / "md"
    input_dir.mkdir()
    (input_dir / "page.md").write_text("word " * 100, encoding="utf-8")

    output_file = tmp_path / "combined.md"
    report_path = tmp_path / "report.json"
    main(
        [
            "--report",
            str(report_path),
            "combine",
            str(input_dir),
            "-o",
            str(output_file),
        ]
    )

    data = json.loads(report_path.read_text(encoding="utf-8"))
    combine_step = data["steps"][0]
    assert "output_word_counts" in combine_step
    assert len(combine_step["output_word_counts"]) == 1
    word_count = next(iter(combine_step["output_word_counts"].values()))
    assert word_count > 0
