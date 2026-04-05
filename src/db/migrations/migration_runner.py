"""マイグレーションランナー

schema_version を確認し、未適用のマイグレーションスクリプトを順次実行する。
失敗時はロールバックしてエラーを送出する。

v1時点ではマイグレーションスクリプト不要（ランナーと仕組みのみ実装）。
"""

import importlib
from typing import Protocol

from src.db.connection import get_connection, transaction
from src.utils.logger import get_logger

CURRENT_SCHEMA_VERSION = 1

# マイグレーションスクリプトのマッピング: {from_version: module_path}
# v1 → v2 以降のマイグレーションはここに追加する
# 例: 1: "src.db.migrations.migrate_v1_to_v2"
_MIGRATION_SCRIPTS: dict[int, str] = {}


class MigrationScript(Protocol):
    def run(self, conn: object) -> None: ...


class MigrationError(Exception):
    pass


def run_migrations() -> None:
    """現在の schema_version を確認し、必要なマイグレーションを順次実行する。"""
    logger = get_logger()
    conn = get_connection()

    row = conn.execute("SELECT schema_version FROM app_settings WHERE id = 1").fetchone()
    if row is None:
        raise MigrationError("app_settings レコードが見つかりません。DB初期化が完了していない可能性があります。")

    current_version: int = row["schema_version"]
    logger.info("schema_version: %d (target: %d)", current_version, CURRENT_SCHEMA_VERSION)

    if current_version == CURRENT_SCHEMA_VERSION:
        return

    if current_version > CURRENT_SCHEMA_VERSION:
        raise MigrationError(
            f"DBのschema_version ({current_version}) がアプリのバージョン ({CURRENT_SCHEMA_VERSION}) より新しいです。"
            "古いバージョンのアプリは使用できません。"
        )

    version = current_version
    while version < CURRENT_SCHEMA_VERSION:
        module_path = _MIGRATION_SCRIPTS.get(version)
        if module_path is None:
            raise MigrationError(f"v{version} → v{version + 1} のマイグレーションスクリプトが見つかりません。")

        logger.info("Running migration: v%d -> v%d (%s)", version, version + 1, module_path)
        try:
            module = importlib.import_module(module_path)
            script: MigrationScript = module
            with transaction() as txn:
                script.run(txn)
                sql = (
                    "UPDATE app_settings SET schema_version = ?, "
                    "updated_at = datetime('now', 'localtime') WHERE id = 1"
                )
                txn.execute(sql, (version + 1,))
        except Exception as e:
            logger.error("Migration v%d -> v%d failed: %s", version, version + 1, e, exc_info=True)
            raise MigrationError(f"マイグレーション v{version} → v{version + 1} に失敗しました: {e}") from e

        version += 1
        logger.info("Migration to v%d completed", version)
