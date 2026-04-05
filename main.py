"""シフト管理アプリ エントリーポイント

起動順序 (§18-2):
1. ロガー初期化
2. ロック取得
3. DBバックアップ
4. DB接続・初期化・マイグレーション
5. credentials確認
6. Tkinter起動 → スタート画面表示
7. バックグラウンドで自動同期（stub: no-op）
"""

import sys
import threading

from src.db.connection import close_connection, init_connection
from src.db.init_db import init_db
from src.db.migrations.migration_runner import run_migrations
from src.ui.app import App
from src.ui.screens.start_screen import StartScreen
from src.utils.backup import backup_on_startup
from src.utils.credentials_checker import check as check_credentials
from src.utils.lock import LockError, acquire_lock, release_lock
from src.utils.logger import get_logger, setup_logger


def _run_auto_sync(app) -> None:
    """起動時自動同期（stub: no-op）。

    feature/google-api マージ後に実接続コードへ差し替える。
    UIをブロックしないようにバックグラウンドスレッドで実行する。

    NOTE: 実接続に差し替える際、SyncResult をUIに渡す処理も含め
    すべてのUI操作を app.after(0, ...) 経由で実行すること。
    バックグラウンドスレッドから直接 Tkinter ウィジェットを操作すると
    スレッド安全性の問題が発生する。
    """
    app.after(0, lambda: app.status_bar.set_sync_message("自動同期中…"))
    # TODO: 実接続に差し替える（collecting / editing 期間を順次同期）
    # NOTE: stub では after(0, ...) が連続キューされるため「自動同期中…」は視覚的に表示されない。
    # 実接続時は同期処理完了コールバック内で after(0, ...) を呼ぶこと。
    app.after(0, lambda: app.status_bar.set_sync_message(""))


def main() -> None:
    setup_logger()
    logger = get_logger()
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

        # スキーマ初期化・マイグレーション
        init_db()
        run_migrations()

        logger.info("shift-app initialized successfully")

        # credentials 確認
        status = check_credentials()

        # Tkinter 起動
        app = App(creds_available=status.available)
        app.show_screen(StartScreen)

        # スタート画面表示後にバックグラウンドで自動同期
        threading.Thread(target=_run_auto_sync, args=(app,), daemon=True).start()

        app.mainloop()

    except Exception as e:
        logger.error("Fatal error during startup: %s", e, exc_info=True)
        raise
    finally:
        close_connection()
        release_lock()


if __name__ == "__main__":
    main()
