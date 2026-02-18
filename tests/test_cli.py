"""cli モジュールのテスト。"""

import json
from pathlib import Path
from unittest.mock import patch

import httpx

from notebooklm_connector.cli import main


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
