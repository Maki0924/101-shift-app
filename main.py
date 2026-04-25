"""シフト管理アプリ エントリーポイント

起動順序 (§18-2):
1. ロガー初期化
2. ロック取得
3. DBバックアップ
4. DB接続・初期化・マイグレーション
5. credentials確認
6. Tkinter起動 → スタート画面表示
7. バックグラウンドで自動同期
"""

import sys
import threading

from src.db.connection import close_connection, init_connection
from src.db.init_db import init_db
from src.db.migrations.migration_runner import run_migrations
from src.db.repositories import period_repo, settings_repo, staff_repo
from src.sheets import auth, client
from src.sheets.sync import sync_period
from src.ui.app import App, AppWarning
from src.ui.screens.start_screen import StartScreen
from src.utils.backup import backup_on_startup
from src.utils.credentials_checker import check as check_credentials
from src.utils.lock import LockError, acquire_lock, release_lock
from src.utils.logger import get_logger, setup_logger
from src.utils.paths import APP_DIR


def _run_auto_sync(app) -> None:
    """起動時自動同期をバックグラウンドで実行する。"""
    logger = get_logger()
    app.post_to_ui(lambda: app.status_bar.set_sync_message("自動同期中…"))
    try:
        app_settings = settings_repo.get()
        creds_filename = (
            app_settings["credentials_filename"]
            if app_settings and app_settings.get("credentials_filename")
            else "credentials.json"
        )
        creds = auth.load_credentials(APP_DIR / creds_filename)
        if creds is None:
            logger.info("Auto sync skipped: credentials unavailable")
            app.post_to_ui(lambda: app.status_bar.set_sync_message(""))
            return

        sheets_svc = client.build_sheets(creds)
        targets = period_repo.get_by_status("collecting") + period_repo.get_by_status("editing")
        target_ids = {period["id"] for period in targets}
        all_staff = staff_repo.get_all()
        staff_map = {staff["name"]: staff["id"] for staff in all_staff if staff.get("is_active")}

        total_added = 0
        total_warnings = 0
        new_warnings: list[AppWarning] = []
        for period in targets:
            if app.is_shutting_down():
                logger.info("Auto sync aborted during shutdown")
                return
            result = sync_period(period, sheets_svc, staff_map)
            total_added += result.added
            total_warnings += len(result.warnings)
            for warning in result.warnings:
                new_warnings.append(AppWarning(period_id=period["id"], message=warning, kind="sync"))

        summary = f"自動同期完了: {total_added}件追加"
        if total_warnings:
            summary += f"、{total_warnings}件警告"
        logger.info("Auto sync completed: added=%d warnings=%d", total_added, total_warnings)

        def _apply_sync_results() -> None:
            if app.is_shutting_down():
                return
            app.warnings = [w for w in app.warnings if not (w.period_id in target_ids and w.kind == "sync")]
            app.warnings.extend(new_warnings)
            app.status_bar.set_timed_sync_message(summary)
            app.refresh_current_screen_data()

        app.post_to_ui(_apply_sync_results)
    except Exception as e:
        logger.error("Auto sync failed: %s", e, exc_info=True)
        message = f"自動同期に失敗しました: {e}"
        app.post_to_ui(lambda: None if app.is_shutting_down() else app.status_bar.set_timed_sync_message(message))


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
        auto_sync_thread = threading.Thread(target=_run_auto_sync, args=(app,))
        auto_sync_thread.start()

        app.mainloop()

    except Exception as e:
        logger.error("Fatal error during startup: %s", e, exc_info=True)
        raise
    finally:
        auto_sync_thread = locals().get("auto_sync_thread")
        if auto_sync_thread is not None and auto_sync_thread.is_alive():
            auto_sync_thread.join()
        close_connection()
        release_lock()


if __name__ == "__main__":
    main()
