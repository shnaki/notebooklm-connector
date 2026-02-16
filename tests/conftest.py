"""共有テストフィクスチャ。"""

import pytest

SAMPLE_HTML = """\
<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
  <nav><a href="/other">Nav Link</a></nav>
  <header><h1>Site Header</h1></header>
  <main>
    <article>
      <h1>Hello World</h1>
      <p>This is a <strong>test</strong> paragraph.</p>
      <ul>
        <li>Item 1</li>
        <li>Item 2</li>
      </ul>
    </article>
  </main>
  <aside class="sidebar">Sidebar content</aside>
  <footer>Footer content</footer>
  <script>console.log("js")</script>
  <style>body { color: red; }</style>
</body>
</html>
"""

SAMPLE_HTML_NO_MAIN = """\
<!DOCTYPE html>
<html>
<head><title>No Main</title></head>
<body>
  <nav><a href="/">Home</a></nav>
  <div>
    <h1>Page Title</h1>
    <p>Body content here.</p>
  </div>
  <footer>Footer</footer>
</body>
</html>
"""

SAMPLE_HTML_WITH_IMAGES = """\
<!DOCTYPE html>
<html>
<head><title>Images</title></head>
<body>
  <main>
    <h1>Image Test</h1>
    <p>Before image.</p>
    <img src="photo.png" alt="A photo">
    <p>After image.</p>
  </main>
</body>
</html>
"""

SAMPLE_HTML_WITH_LINKS = """\
<!DOCTYPE html>
<html>
<head><title>Links Page</title></head>
<body>
  <main>
    <h1>Links</h1>
    <a href="/page1">Page 1</a>
    <a href="/page2">Page 2</a>
    <a href="https://external.com/out">External</a>
    <a href="/page1#section">Page 1 anchor</a>
    <a href="mailto:test@example.com">Email</a>
  </main>
</body>
</html>
"""


@pytest.fixture
def sample_html() -> str:
    """標準的なテスト用 HTML。"""
    return SAMPLE_HTML


@pytest.fixture
def sample_html_no_main() -> str:
    """<main> タグを含まないテスト用 HTML。"""
    return SAMPLE_HTML_NO_MAIN


@pytest.fixture
def sample_html_with_images() -> str:
    """画像を含むテスト用 HTML。"""
    return SAMPLE_HTML_WITH_IMAGES


@pytest.fixture
def sample_html_with_links() -> str:
    """リンクを含むテスト用 HTML。"""
    return SAMPLE_HTML_WITH_LINKS
