"""Web クロールモジュール。

BFS でリンクを辿り、HTML ファイルをローカルに保存する。
"""

import logging
import re
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from notebooklm_connector.models import CrawlConfig

logger = logging.getLogger(__name__)


def _derive_url_prefix(start_url: str) -> str:
    """start_url からクロール範囲の URL prefix を導出する。

    Args:
        start_url: 開始 URL。

    Returns:
        URL prefix 文字列。
    """
    parsed = urlparse(start_url)
    # パスの最後のセグメントを除いた部分を prefix とする
    path = parsed.path
    if path and not path.endswith("/"):
        path = path.rsplit("/", 1)[0] + "/"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def _url_to_filename(url: str, base_url: str) -> str:
    """URL からファイル名を生成する。

    Args:
        url: 対象 URL。
        base_url: ベース URL。

    Returns:
        安全なファイル名文字列。
    """
    parsed = urlparse(url)
    path = parsed.path.strip("/")

    if not path or path == urlparse(base_url).path.strip("/"):
        return "index.html"

    # パスからファイル名を生成
    filename = re.sub(r"[^\w\-./]", "_", path)
    filename = filename.replace("/", "_")

    if not filename.endswith(".html"):
        filename += ".html"

    return filename


def _discover_links(
    html: str,
    base_url: str,
    url_prefix: str,
) -> list[str]:
    """HTML からリンクを抽出し、スコープ内の URL のみ返す。

    Args:
        html: HTML 文字列。
        base_url: 現在のページの URL。
        url_prefix: クロール範囲の URL prefix。

    Returns:
        スコープ内の絶対 URL リスト。
    """
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []

    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])

        # mailto:, javascript:, # のみはスキップ
        if href.startswith(("mailto:", "javascript:", "tel:")):
            continue

        absolute = urljoin(base_url, href)

        # フラグメントを除去
        absolute = absolute.split("#")[0]

        # クエリパラメータも除去 (ドキュメントサイトでは不要)
        absolute = absolute.split("?")[0]

        # スコープチェック
        if absolute.startswith(url_prefix) and absolute not in links:
            links.append(absolute)

    return links


def _fetch_and_save(
    url: str,
    config: CrawlConfig,
    url_prefix: str,
    client: httpx.Client,
) -> tuple[Path | None, list[str]]:
    """単一 URL のフェッチ・保存・リンク探索をワーカースレッドで実行する。

    キャッシュヒット時は sleep しない（HTTP リクエストなし）。
    フェッチ後に delay_seconds だけ sleep してレート制限する。

    Args:
        url: 取得する URL。
        config: クロール設定。
        url_prefix: クロール範囲の URL prefix。
        client: httpx.Client インスタンス。

    Returns:
        (保存されたファイルパス or None, 発見されたリンクのリスト)。
    """
    filename = _url_to_filename(url, config.start_url)
    filepath = config.output_dir / filename

    # キャッシュチェック: ファイルが存在すれば HTTP リクエストをスキップ
    if filepath.exists():
        logger.info("キャッシュ使用: %s", url)
        html = filepath.read_text(encoding="utf-8")
        new_links = _discover_links(html, url, url_prefix)
        return filepath, new_links

    logger.info("クロール中: %s", url)

    try:
        response = client.get(url)
        response.raise_for_status()
    except httpx.HTTPError:
        logger.exception("取得失敗: %s", url)
        return None, []

    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type:
        logger.debug("スキップ (非 HTML): %s", url)
        return None, []

    html = response.text

    # ファイル保存
    filepath.write_text(html, encoding="utf-8")

    # リンク探索
    new_links = _discover_links(html, url, url_prefix)

    # レート制限（キャッシュヒットではないので sleep）
    if config.delay_seconds > 0:
        time.sleep(config.delay_seconds)

    return filepath, new_links


def crawl(config: CrawlConfig, client: httpx.Client | None = None) -> list[Path]:
    """BFS で Web サイトをクロールし HTML ファイルを保存する。

    Args:
        config: クロール設定。
        client: httpx.Client インスタンス。None の場合は新規作成。

    Returns:
        保存された HTML ファイルのパスリスト。
    """
    config.output_dir.mkdir(parents=True, exist_ok=True)

    url_prefix = config.url_prefix or _derive_url_prefix(config.start_url)
    logger.info("クロール開始: %s (prefix: %s)", config.start_url, url_prefix)

    visited: set[str] = set()
    pending_urls: list[str] = [config.start_url]
    saved_files: list[Path] = []
    lock = threading.Lock()

    should_close = client is None
    if client is None:
        client = httpx.Client(
            follow_redirects=True,
            timeout=30.0,
            headers={
                "User-Agent": ("Mozilla/5.0 (compatible; NotebookLM-Connector/0.1)"),
            },
        )

    try:
        with ThreadPoolExecutor(max_workers=config.max_concurrency) as executor:
            futures: set[Future[tuple[Path | None, list[str]]]] = set()

            def _submit_pending() -> None:
                """pending_urls から未訪問 URL を submit する。"""
                while pending_urls and len(visited) < config.max_pages:
                    url = pending_urls.pop(0)
                    if url in visited:
                        continue
                    visited.add(url)
                    future = executor.submit(
                        _fetch_and_save, url, config, url_prefix, client
                    )
                    futures.add(future)

            _submit_pending()

            while futures:
                done, futures = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    filepath, new_links = future.result()
                    with lock:
                        if filepath is not None:
                            saved_files.append(filepath)
                        for link in new_links:
                            if link not in visited:
                                pending_urls.append(link)
                    _submit_pending()
    finally:
        if should_close:
            client.close()

    logger.info("クロール完了: %d ページを保存しました", len(saved_files))
    return saved_files
