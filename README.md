# notebooklm-conector

Add your description here.

## 開発環境のセットアップ

このプロジェクトでは `uv` を使用して依存関係を管理しています。

### 準備

1. [uv](https://github.com/astral-sh/uv) をインストールします。
2. 以下のコマンドを実行して仮想環境を作成し、依存関係をインストールします。

```bash
uv sync
```

### 開発用ツール

- **Lint/Format**: Ruff
  - `uv run ruff check` (Lint)
  - `uv run ruff format` (Format)
- **型チェック**: mypy
  - `uv run mypy src`
- **テスト**: pytest
  - `uv run pytest`
- **Gitフック**: pre-commit
  - `uv run pre-commit install` でインストール
