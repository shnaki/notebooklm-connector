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
    max_concurrency: int = 5


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
    max_workers: int | None = None
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


@dataclass
class StepResult:
    """個別ステップの処理結果。"""

    step_name: str
    file_count: int
    total_bytes: int
    elapsed_seconds: float
    output_path: str
    skipped_count: int = 0
    downloaded_count: int = 0
    failure_count: int = 0
    output_word_counts: dict[str, int] = field(default_factory=lambda: {})


@dataclass
class PipelineReport:
    """パイプライン全体の処理レポート。"""

    steps: list[StepResult]
    total_elapsed_seconds: float
    crawl_failures: list[str] = field(default_factory=lambda: [])
    convert_failures: list[str] = field(default_factory=lambda: [])
    command: list[str] = field(default_factory=lambda: [])
