# notebooklm-connector

Webサイトのドキュメントをクロールし、[NotebookLM](https://notebooklm.google.com/) に最適化されたMarkdownファイルに変換するCLIツールです。

## 主な機能

- **クロール**: BFSアルゴリズムによるWebサイトのHTMLダウンロード（キャッシュによる効率的な追加クロール対応）
- **変換**: HTMLからMarkdownへの変換（画像等の不要要素を除去）
- **結合**: 複数のMarkdownファイルを1つに結合（500,000語超で自動分割）
- **パイプライン**: 上記3ステップを一括実行

## インストール

```bash
uv sync
```

## 使い方

### パイプライン（一括実行）

```bash
uv run notebooklm-connector pipeline https://example.com/docs -o output/
```

`output/html/`、`output/md/`、`output/combined.md` が生成されます。語数が500,000語を超える場合は `combined-001.md`、
`combined-002.md` のように自動分割されます。

`--max-pages` に達した場合でも、再実行すればキャッシュ済みページをスキップして未取得のページから追加クロールを継続できます。

### 個別実行

```bash
# Webサイトをクロールしてhtmlを保存
# 出力ディレクトリに既存HTMLがあればキャッシュとして再利用し、HTTPリクエストをスキップします
uv run notebooklm-connector crawl https://example.com/docs -o html/ --max-pages 50 --delay 1.0

# HTMLをMarkdownに変換
uv run notebooklm-connector convert html/ -o md/

# ZIPファイルからも変換可能
uv run notebooklm-connector convert archive.zip -o md/ --zip

# Markdownファイルを1つに結合（500,000語超で自動分割）
uv run notebooklm-connector combine md/ -o combined.md
```

## 開発

### セットアップ

1. [uv](https://github.com/astral-sh/uv) をインストールします。
2. 依存関係をインストールします。

```bash
uv sync
```

3. pre-commit フックをインストールします。

```bash
uv run pre-commit install
```

### 開発用ツール

- **Lint/Format**: Ruff
    - `uv run --frozen ruff check .` (Lint)
    - `uv run --frozen ruff format .` (Format)
- **型チェック**: Pyright
    - `uv run --frozen pyright`
- **テスト**: pytest
    - `uv run --frozen pytest`
