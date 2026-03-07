# シフト管理アプリ

Googleフォームで収集したスタッフの希望シフトを元に、店長がシフトを編集・管理・印刷するためのローカルアプリ。

## 対応環境

- 開発: Mac / Windows
- 配布: Windows向け単体exe
- Python: 3.11

## セットアップ

```bash
# uv がインストール済みであること
uv sync
```

## 実行

```bash
uv run python main.py
```

## テスト

```bash
uv run pytest tests/ -v
```

## リント

```bash
uv run ruff check .
uv run ruff format .
```

## Google Sheets 連携

1. GCPでサービスアカウントを作成
2. `credentials.json` をアプリ実行フォルダに配置
3. 対象スプレッドシートをサービスアカウントのメールアドレスに共有

`credentials.json` がなくてもアプリ本体は起動可能（Sheets同期機能のみ無効化）。

## ドキュメント

- [要件定義書](docs/requirements.md)
- [詳細実装仕様](docs/detailed_spec.md)
