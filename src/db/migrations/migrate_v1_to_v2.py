"""マイグレーション v1 → v2

変更内容:
  - app_settings に credentials_filename カラムを追加
    （デフォルト: 'credentials.json'）
"""


def run(conn) -> None:
    conn.execute(
        "ALTER TABLE app_settings ADD COLUMN"
        " credentials_filename TEXT NOT NULL DEFAULT 'credentials.json'"
    )
