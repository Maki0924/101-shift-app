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

## 配布（Windows exe ビルド）

### ビルド手順

```bash
# 依存関係を揃える（PyInstaller も dev deps に含まれる）
uv sync

# exe をビルド
uv run pyinstaller build.spec
```

成功すると `dist/shift_app.exe` が生成される。

### 配布パッケージの構成

```
shift_app.exe          ← 単体実行ファイル
credentials.json       ← Google Sheets 連携用（任意・後から配置可）
```

`backup/` / `logs/` は初回起動時に自動生成されるため同梱不要。  
`credentials.json` がなくてもアプリ本体は起動可能。

### ショートカット設置手順（Windows）

1. `shift_app.exe` を任意のフォルダ（例: `C:\ShiftApp\`）にコピー
2. `shift_app.exe` を右クリック → 「ショートカットの作成」
3. 作成したショートカットをデスクトップや任意の場所に移動

> アプリはロックファイル・バックアップ・ログを **exe と同じフォルダ** に書き込む。  
> `C:\Program Files\` など書き込み権限のない場所には配置しないこと。

## ドキュメント

- [改善済み仕様書](docs/improvements.md)
- [実装コミット計画](docs/commit_plan.md)
- [画面ワイヤーフレーム](docs/wireframes.md)
