"""複数の Markdown ファイルを 1 ファイルに結合するモジュール。"""

import logging
from pathlib import Path

from notebooklm_connector.models import CombineConfig

logger = logging.getLogger(__name__)

_WORD_COUNT_WARNING_THRESHOLD = 500_000


def _split_sections(
    sections: list[str],
    separator: str,
    threshold: int,
) -> list[str]:
    """セクションを語数閾値に基づいてチャンクに分割する。

    Args:
        sections: 結合対象のセクション一覧。
        separator: セクション間のセパレータ。
        threshold: 1チャンクあたりの語数上限。

    Returns:
        分割されたチャンクのリスト。
    """
    chunks: list[str] = []
    current_sections: list[str] = []
    current_word_count = 0

    for section in sections:
        section_words = len(section.split())
        sep_words = len(separator.split()) if current_sections else 0
        new_count = current_word_count + sep_words + section_words

        if current_sections and new_count > threshold:
            chunk = separator.join(current_sections) + "\n"
            chunks.append(chunk)
            current_sections = [section]
            current_word_count = section_words
        else:
            current_sections.append(section)
            current_word_count = new_count

    if current_sections:
        chunk = separator.join(current_sections) + "\n"
        chunks.append(chunk)

    return chunks


def combine(config: CombineConfig) -> tuple[list[Path], dict[str, int]]:
    """Markdown ファイルをアルファベット順でソートし 1 ファイルに結合する。

    語数が閾値を超える場合はファイルを自動分割する。

    Args:
        config: 結合設定。

    Returns:
        生成された結合ファイルのパスのリストと、各ファイルの語句数の辞書のタプル。
    """
    md_files = sorted(
        config.input_dir.rglob("*.md"),
        key=lambda p: p.relative_to(config.input_dir),
    )

    if not md_files:
        logger.warning("Markdown ファイルが見つかりません: %s", config.input_dir)
        config.output_file.parent.mkdir(parents=True, exist_ok=True)
        config.output_file.write_text("", encoding="utf-8")
        return [config.output_file], {config.output_file.as_posix(): 0}

    sections: list[str] = []
    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8").strip()
        if config.add_source_header:
            relative = md_file.relative_to(config.input_dir)
            header = f"Source: {relative.as_posix()}"
            sections.append(f"{header}\n\n{content}")
        else:
            sections.append(content)

    combined = config.separator.join(sections) + "\n"
    word_count = len(combined.split())

    config.output_file.parent.mkdir(parents=True, exist_ok=True)

    if word_count <= _WORD_COUNT_WARNING_THRESHOLD:
        config.output_file.write_text(combined, encoding="utf-8")
        logger.info(
            "%d ファイルを結合しました: %s (%d 語)",
            len(md_files),
            config.output_file,
            word_count,
        )
        return [config.output_file], {config.output_file.as_posix(): word_count}

    # 閾値超過: セクション単位で分割
    chunks = _split_sections(sections, config.separator, _WORD_COUNT_WARNING_THRESHOLD)
    stem = config.output_file.stem
    suffix = config.output_file.suffix
    parent = config.output_file.parent

    output_files: list[Path] = []
    word_counts: dict[str, int] = {}
    for i, chunk in enumerate(chunks, start=1):
        path = parent / f"{stem}-{i:03d}{suffix}"
        path.write_text(chunk, encoding="utf-8")
        output_files.append(path)
        word_counts[path.as_posix()] = len(chunk.split())

    logger.info(
        "%d ファイルを %d 個に分割しました (%d 語)",
        len(md_files),
        len(output_files),
        word_count,
    )
    return output_files, word_counts
