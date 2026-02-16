"""パイプライン各ステージの設定データクラス。"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CrawlConfig:
    """Web クローラの設定。"""

    start_url: str
    output_dir: Path
    max_pages: int = 100
    delay_seconds: float = 1.0
    url_prefix: str = ""


@dataclass
class ConvertConfig:
    """HTML→Markdown 変換の設定。"""

    input_dir: Path
    output_dir: Path
    strip_tags: list[str] = field(
        default_factory=lambda: [
            "nav",
            "footer",
            "header",
            "aside",
            "script",
            "style",
            "noscript",
            "iframe",
        ]
    )
    strip_classes: list[str] = field(
        default_factory=lambda: [
            "sidebar",
            "navigation",
            "nav",
            "menu",
            "toc",
            "breadcrumb",
        ]
    )


@dataclass
class CombineConfig:
    """Markdown 結合の設定。"""

    input_dir: Path
    output_file: Path
    separator: str = "\n\n---\n\n"
    add_source_header: bool = True
