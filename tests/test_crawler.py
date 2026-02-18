"""crawler モジュールのテスト。"""

from pathlib import Path

import httpx

from notebooklm_connector.crawler import (
    _derive_url_prefix,
    _discover_links,
    _url_to_filename,
    crawl,
)
from notebooklm_connector.models import CrawlConfig

# --- ヘルパー ---

PAGES: dict[str, str] = {
    "https://example.com/docs/": (
        "<html><body>"
        '<a href="/docs/page1">Page 1</a>'
        '<a href="/docs/page2">Page 2</a>'
        '<a href="https://other.com/">External</a>'
        "</body></html>"
    ),
    "https://example.com/docs/page1": (
        '<html><body><h1>Page 1</h1><a href="/docs/">Home</a></body></html>'
    ),
    "https://example.com/docs/page2": (
        '<html><body><h1>Page 2</h1><a href="/docs/page1">Page 1</a></body></html>'
    ),
}


def _mock_handler(request: httpx.Request) -> httpx.Response:
    """テスト用のモック HTTP ハンドラ。"""
    url = str(request.url)
    if url in PAGES:
        return httpx.Response(
            200,
            text=PAGES[url],
            headers={"content-type": "text/html; charset=utf-8"},
        )
    return httpx.Response(404, text="Not Found")


def _make_mock_client() -> httpx.Client:
    """テスト用の httpx.Client を生成する。"""
    return httpx.Client(transport=httpx.MockTransport(_mock_handler))


# --- _derive_url_prefix ---


def test_derive_url_prefix_with_trailing_slash() -> None:
    """末尾スラッシュのある URL からの prefix 導出。"""
    result = _derive_url_prefix("https://example.com/docs/")
    assert result == "https://example.com/docs/"


def test_derive_url_prefix_without_trailing_slash() -> None:
    """末尾スラッシュなしの URL からの prefix 導出。"""
    result = _derive_url_prefix("https://example.com/docs/intro")
    assert result == "https://example.com/docs/"


def test_derive_url_prefix_root() -> None:
    """ルート URL からの prefix 導出。"""
    result = _derive_url_prefix("https://example.com/")
    assert result == "https://example.com/"


# --- _url_to_filename ---


def test_url_to_filename_index() -> None:
    """ベース URL がそのまま index.html になること。"""
    result = _url_to_filename(
        "https://example.com/docs/",
        "https://example.com/docs/",
    )
    assert result == "index.html"


def test_url_to_filename_subpage() -> None:
    """サブページが適切なファイル名に変換されること。"""
    result = _url_to_filename(
        "https://example.com/docs/guide/start",
        "https://example.com/docs/",
    )
    assert result == "docs_guide_start.html"


def test_url_to_filename_already_html() -> None:
    """.html 拡張子を持つ URL が二重にならないこと。"""
    result = _url_to_filename(
        "https://example.com/docs/page.html",
        "https://example.com/docs/",
    )
    assert result.endswith(".html")
    assert not result.endswith(".html.html")


# --- _discover_links ---


def test_discover_links_filters_by_prefix() -> None:
    """prefix に一致するリンクのみが返されること。"""
    html = (
        '<a href="/docs/page1">In scope</a>'
        '<a href="/other/page">Out of scope</a>'
        '<a href="https://external.com/">External</a>'
    )
    result = _discover_links(
        html,
        "https://example.com/docs/",
        "https://example.com/docs/",
    )
    assert len(result) == 1
    assert result[0] == "https://example.com/docs/page1"


def test_discover_links_strips_fragment() -> None:
    """フラグメント (#) が除去されること。"""
    html = '<a href="/docs/page1#section">Link</a>'
    result = _discover_links(
        html,
        "https://example.com/docs/",
        "https://example.com/docs/",
    )
    assert result[0] == "https://example.com/docs/page1"


def test_discover_links_skips_mailto() -> None:
    """mailto: リンクがスキップされること。"""
    html = '<a href="mailto:test@example.com">Email</a>'
    result = _discover_links(
        html,
        "https://example.com/docs/",
        "https://example.com/docs/",
    )
    assert result == []


def test_discover_links_deduplicates() -> None:
    """重複リンクが除去されること。"""
    html = '<a href="/docs/page1">Link 1</a><a href="/docs/page1">Link 2</a>'
    result = _discover_links(
        html,
        "https://example.com/docs/",
        "https://example.com/docs/",
    )
    assert len(result) == 1


# --- crawl ---


def test_crawl_saves_html_files(tmp_path: Path) -> None:
    """BFS でクロールし HTML ファイルが保存されること。"""
    config = CrawlConfig(
        start_url="https://example.com/docs/",
        output_dir=tmp_path / "html",
        max_pages=10,
        delay_seconds=0,
    )

    client = _make_mock_client()
    files, skipped, downloaded, failed = crawl(config, client=client)

    assert len(files) == 3
    assert all(f.exists() for f in files)
    assert all(f.suffix == ".html" for f in files)


def test_crawl_respects_max_pages(tmp_path: Path) -> None:
    """max_pages の制限が守られること。"""
    config = CrawlConfig(
        start_url="https://example.com/docs/",
        output_dir=tmp_path / "html",
        max_pages=1,
        delay_seconds=0,
    )

    client = _make_mock_client()
    files, skipped, downloaded, failed = crawl(config, client=client)

    assert len(files) == 1


def test_crawl_does_not_visit_external(tmp_path: Path) -> None:
    """外部リンクを辿らないこと。"""
    config = CrawlConfig(
        start_url="https://example.com/docs/",
        output_dir=tmp_path / "html",
        max_pages=100,
        delay_seconds=0,
    )

    client = _make_mock_client()
    files, skipped, downloaded, failed = crawl(config, client=client)

    all_content = ""
    for f in files:
        all_content += f.read_text(encoding="utf-8")

    # 外部リンクの内容が含まれないこと
    # (外部リンクへのアンカーはあってもクロールされていない)
    assert len(files) == 3  # docs/, page1, page2 のみ


def test_crawl_handles_404(tmp_path: Path) -> None:
    """404 ページをスキップして続行すること。"""

    def handler_with_404(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://example.com/docs/":
            return httpx.Response(
                200,
                text='<a href="/docs/missing">Missing</a>',
                headers={"content-type": "text/html"},
            )
        return httpx.Response(404, text="Not Found")

    config = CrawlConfig(
        start_url="https://example.com/docs/",
        output_dir=tmp_path / "html",
        max_pages=10,
        delay_seconds=0,
    )

    client = httpx.Client(transport=httpx.MockTransport(handler_with_404))
    files, skipped, downloaded, failed = crawl(config, client=client)

    # 開始ページのみ保存される
    assert len(files) == 1
    assert len(failed) == 1


def test_crawl_custom_prefix(tmp_path: Path) -> None:
    """カスタム url_prefix が使用されること。"""
    config = CrawlConfig(
        start_url="https://example.com/docs/",
        output_dir=tmp_path / "html",
        max_pages=10,
        delay_seconds=0,
        url_prefix="https://example.com/docs/page1",
    )

    client = _make_mock_client()
    files, skipped, downloaded, failed = crawl(config, client=client)

    # start_url 自体は prefix 外だが最初にアクセスされる
    # page1 のみが prefix に一致
    assert len(files) >= 1


def test_crawl_uses_cache(tmp_path: Path) -> None:
    """出力ディレクトリに既存 HTML があれば HTTP リクエストをスキップすること。"""
    output_dir = tmp_path / "html"
    output_dir.mkdir()

    # キャッシュファイルを事前に配置（リンクなし）
    cached_html = "<html><body><h1>Cached</h1></body></html>"
    (output_dir / "index.html").write_text(cached_html, encoding="utf-8")

    config = CrawlConfig(
        start_url="https://example.com/docs/",
        output_dir=output_dir,
        max_pages=10,
        delay_seconds=0,
    )

    # HTTP リクエストが来たら失敗させる
    def fail_handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"HTTP リクエストが発生すべきでない: {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(fail_handler))
    files, skipped, downloaded, failed = crawl(config, client=client)

    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8") == cached_html
    assert skipped == 1
    assert downloaded == 0


def test_crawl_concurrent_multiple_pages(tmp_path: Path) -> None:
    """max_concurrency=3 で全ページが正しく取得されること。"""
    config = CrawlConfig(
        start_url="https://example.com/docs/",
        output_dir=tmp_path / "html",
        max_pages=10,
        delay_seconds=0,
        max_concurrency=3,
    )

    client = _make_mock_client()
    files, skipped, downloaded, failed = crawl(config, client=client)

    assert len(files) == 3
    assert all(f.exists() for f in files)
    filenames = {f.name for f in files}
    assert "index.html" in filenames
    assert "docs_page1.html" in filenames
    assert "docs_page2.html" in filenames


def test_crawl_max_concurrency_one(tmp_path: Path) -> None:
    """max_concurrency=1 でシーケンシャルと同等の結果になること。"""
    config = CrawlConfig(
        start_url="https://example.com/docs/",
        output_dir=tmp_path / "html",
        max_pages=10,
        delay_seconds=0,
        max_concurrency=1,
    )

    client = _make_mock_client()
    files, skipped, downloaded, failed = crawl(config, client=client)

    assert len(files) == 3
    assert all(f.exists() for f in files)


def test_crawl_cache_discovers_links(tmp_path: Path) -> None:
    """キャッシュされたページからもリンクが探索され新しいページがクロールされること。"""
    output_dir = tmp_path / "html"
    output_dir.mkdir()

    # キャッシュファイルにリンクを含める
    cached_html = '<html><body><a href="/docs/page1">Page 1</a></body></html>'
    (output_dir / "index.html").write_text(cached_html, encoding="utf-8")

    config = CrawlConfig(
        start_url="https://example.com/docs/",
        output_dir=output_dir,
        max_pages=10,
        delay_seconds=0,
    )

    client = _make_mock_client()
    files, skipped, downloaded, failed = crawl(config, client=client)

    # index.html はキャッシュ、page1 は HTTP で取得
    assert len(files) == 2
    filenames = {f.name for f in files}
    assert "index.html" in filenames
    assert "docs_page1.html" in filenames


def test_crawl_tracks_downloaded_count(tmp_path: Path) -> None:
    """ダウンロード件数が正確に追跡されること。"""
    config = CrawlConfig(
        start_url="https://example.com/docs/",
        output_dir=tmp_path / "html",
        max_pages=10,
        delay_seconds=0,
    )

    client = _make_mock_client()
    files, skipped, downloaded, failed = crawl(config, client=client)

    assert downloaded == len(files)
    assert skipped == 0
    assert failed == []


def test_crawl_non_html_not_in_failures(tmp_path: Path) -> None:
    """非 HTML レスポンスが failed リストに含まれないこと。"""

    def handler_with_non_html(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://example.com/docs/":
            return httpx.Response(
                200,
                text='<a href="/docs/file.pdf">PDF</a>',
                headers={"content-type": "text/html"},
            )
        # PDF として返す (非 HTML)
        return httpx.Response(
            200,
            content=b"%PDF-1.4",
            headers={"content-type": "application/pdf"},
        )

    config = CrawlConfig(
        start_url="https://example.com/docs/",
        output_dir=tmp_path / "html",
        max_pages=10,
        delay_seconds=0,
    )

    client = httpx.Client(transport=httpx.MockTransport(handler_with_non_html))
    files, skipped, downloaded, failed = crawl(config, client=client)

    # 非 HTML は failed に含まれない
    assert failed == []
    # 開始ページのみ保存
    assert len(files) == 1
