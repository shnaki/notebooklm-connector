"""複数の Markdown ファイルを 1 ファイルに結合するモジュール。"""

import logging
from pathlib import Path

from notebooklm_connector.models import CombineConfig

logger = logging.getLogger(__name__)

_WORD_COUNT_WARNING_THRESHOLD = 500_000


def combine(config: CombineConfig) -> Path:
    """Markdown ファイルをアルファベット順でソートし 1 ファイルに結合する。

    Args:
        config: 結合設定。

    Returns:
        生成された結合ファイルのパス。
    """
    md_files = sorted(
        config.input_dir.rglob("*.md"),
        key=lambda p: p.relative_to(config.input_dir),
    )

    if not md_files:
        logger.warning("Markdown ファイルが見つかりません: %s", config.input_dir)
        config.output_file.parent.mkdir(parents=True, exist_ok=True)
        config.output_file.write_text("", encoding="utf-8")
        return config.output_file

    sections: list[str] = []
    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8").strip()
        if config.add_source_header:
            relative = md_file.relative_to(config.input_dir)
            header = f"<!-- Source: {relative.as_posix()} -->"
            sections.append(f"{header}\n\n{content}")
        else:
            sections.append(content)

    combined = config.separator.join(sections) + "\n"

    # 語数チェック
    word_count = len(combined.split())
    if word_count > _WORD_COUNT_WARNING_THRESHOLD:
        logger.warning(
            "結合ファイルが %d 語を超えています (%d 語)。"
            "NotebookLM の制限を超える可能性があります。",
            _WORD_COUNT_WARNING_THRESHOLD,
            word_count,
        )

    config.output_file.parent.mkdir(parents=True, exist_ok=True)
    config.output_file.write_text(combined, encoding="utf-8")
    logger.info(
        "%d ファイルを結合しました: %s (%d 語)",
        len(md_files),
        config.output_file,
        word_count,
    )
    return config.output_file
