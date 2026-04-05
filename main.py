"""シフト管理アプリ エントリーポイント

起動順序:
1. ロガー初期化
2. ロック取得
3. DBバックアップ
4. DB接続・初期化
"""

import sys

from src.utils.logger import setup_logger
from src.utils.lock import LockError, acquire_lock, release_lock
from src.utils.backup import backup_on_startup
from src.db.connection import init_connection, close_connection


def main() -> None:
    logger = setup_logger()
    logger.info("shift-app starting")

    # ロック取得
    try:
        acquire_lock()
    except LockError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    try:
        # DBバックアップ
        backup_on_startup()

        # DB接続
        init_connection()

        logger.info("shift-app initialized successfully")

        # TODO: コミット2でスキーマ初期化を追加
        # TODO: コミット12でTkinter起動を追加

    except Exception as e:
        logger.error("Fatal error during startup: %s", e, exc_info=True)
        raise
    finally:
        close_connection()
        release_lock()


if __name__ == "__main__":
    main()
