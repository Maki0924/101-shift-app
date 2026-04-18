"""DB基盤テスト: 初期化・foreign_keys・スキーマ・マイグレーション・起動フロー"""

import sqlite3
from unittest import mock

import pytest

from src.db import connection as conn_module
from src.db.connection import close_connection, get_connection, init_connection, transaction
from src.db.init_db import init_db
from src.db.migrations.migration_runner import CURRENT_SCHEMA_VERSION, MigrationError, run_migrations
from src.sheets.sync import SyncResult


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """各テストで独立したインメモリ相当のDB（tmp_path）を使用する。"""
    db_file = tmp_path / "test_shift_app.db"
    monkeypatch.setattr(conn_module, "_DB_FILE", db_file)
    monkeypatch.setattr(conn_module, "_connection", None)

    yield

    close_connection()
    monkeypatch.setattr(conn_module, "_connection", None)


class TestConnection:
    def test_init_connection_creates_db_file(self, tmp_path):
        conn = init_connection()
        assert conn is not None

    def test_foreign_keys_enabled(self):
        conn = init_connection()
        row = conn.execute("PRAGMA foreign_keys").fetchone()
        assert row[0] == 1

    def test_row_factory_is_sqlite_row(self):
        conn = init_connection()
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.execute("INSERT INTO t VALUES (42)")
        row = conn.execute("SELECT x FROM t").fetchone()
        assert row["x"] == 42

    def test_get_connection_raises_before_init(self, monkeypatch):
        monkeypatch.setattr(conn_module, "_connection", None)
        with pytest.raises(RuntimeError):
            get_connection()

    def test_transaction_commit(self):
        init_connection()
        get_connection().execute("CREATE TABLE t (x INTEGER)")
        with transaction() as txn:
            txn.execute("INSERT INTO t VALUES (1)")
        row = get_connection().execute("SELECT x FROM t").fetchone()
        assert row["x"] == 1

    def test_transaction_rollback_on_error(self):
        init_connection()
        get_connection().execute("CREATE TABLE t (x INTEGER)")
        with pytest.raises(ValueError):
            with transaction() as txn:
                txn.execute("INSERT INTO t VALUES (99)")
                raise ValueError("intentional error")
        count = get_connection().execute("SELECT COUNT(*) FROM t").fetchone()[0]
        assert count == 0


class TestInitDb:
    def test_all_tables_created(self):
        init_connection()
        init_db()
        conn = get_connection()
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        expected = {
            "periods",
            "staff",
            "submissions",
            "submission_day_entries",
            "wish_shifts",
            "edited_shifts",
            "manager_memos",
            "cell_marks",
            "custom_day_rules",
            "app_settings",
            "period_print_settings",
        }
        assert expected.issubset(tables)

    def test_app_settings_default_row(self):
        init_connection()
        init_db()
        row = get_connection().execute("SELECT * FROM app_settings WHERE id = 1").fetchone()
        assert row is not None
        assert row["schema_version"] == 2
        assert row["day_shift_start"] == 8
        assert row["night_shift_end"] == 22
        assert row["print_font_size"] == 9

    def test_init_db_idempotent(self):
        """2回呼んでもエラーにならない（CREATE IF NOT EXISTS）"""
        init_connection()
        init_db()
        init_db()
        count = get_connection().execute("SELECT COUNT(*) FROM app_settings").fetchone()[0]
        assert count == 1

    def test_app_settings_id_constraint(self):
        """id=1 以外は挿入できない"""
        init_connection()
        init_db()
        with pytest.raises(sqlite3.IntegrityError):
            get_connection().execute(
                "INSERT INTO app_settings (id, schema_version, day_shift_start, day_shift_end, "
                "night_shift_start, night_shift_end, overlap_hours_threshold, "
                "saturday_bonus, sunday_bonus, holiday_bonus, "
                "weekday_day_min_staff, weekday_night_min_staff, "
                "weekend_day_min_staff, weekend_night_min_staff, "
                "print_font_size, created_at, updated_at) "
                "VALUES (2, 1, 8, 17, 17, 22, 2, 100, 100, 100, 2, 2, 5, 3, 9, '2026-01-01', '2026-01-01')"
            )


class TestForeignKeys:
    def test_foreign_key_violation_rejected(self):
        """存在しない period_id への挿入は拒否される"""
        init_connection()
        init_db()
        with pytest.raises(sqlite3.IntegrityError):
            with transaction() as txn:
                txn.execute(
                    "INSERT INTO period_print_settings (period_id, created_at, updated_at) "
                    "VALUES (9999, '2026-01-01', '2026-01-01')"
                )


class TestMigrationRunner:
    def test_no_migration_needed(self):
        """schema_version が最新なら何もしない"""
        init_connection()
        init_db()
        run_migrations()  # エラーにならない

    def test_schema_version_too_new_raises(self):
        """DBのバージョンがアプリより新しい場合はエラー"""
        init_connection()
        init_db()
        get_connection().execute(
            "UPDATE app_settings SET schema_version = ? WHERE id = 1",
            (CURRENT_SCHEMA_VERSION + 1,),
        )
        get_connection().commit()
        with pytest.raises(MigrationError, match="新しいです"):
            run_migrations()

    def test_missing_migration_script_raises(self, monkeypatch):
        """マイグレーションスクリプトが未登録の場合はエラー"""
        import src.db.migrations.migration_runner as runner

        monkeypatch.setattr(runner, "_MIGRATION_SCRIPTS", {})
        monkeypatch.setattr(runner, "CURRENT_SCHEMA_VERSION", CURRENT_SCHEMA_VERSION + 1)

        init_connection()
        init_db()
        with pytest.raises(MigrationError, match="見つかりません"):
            run_migrations()


class TestStartupFlow:
    """main() の起動フローが init_db / run_migrations を実際に呼ぶことを確認する。"""

    def test_main_calls_init_db_and_migration(self, tmp_path, monkeypatch):
        """main() を通じて DB が初期化され app_settings が投入されることを確認する。"""
        import src.db.connection as conn_mod
        import src.utils.backup as backup_mod
        import src.utils.lock as lock_mod

        db_file = tmp_path / "startup_test.db"
        monkeypatch.setattr(conn_mod, "_DB_FILE", db_file)
        monkeypatch.setattr(conn_mod, "_connection", None)

        # ロックファイルをtmp_pathに向ける
        lock_file = tmp_path / "shift_app.lock"
        monkeypatch.setattr(lock_mod, "_LOCK_FILE", lock_file)

        # バックアップのDB参照先を同じtmp_pathに向ける
        monkeypatch.setattr(backup_mod, "_DB_FILE", db_file)
        monkeypatch.setattr(backup_mod, "_BACKUP_DIR", tmp_path / "backup")

        # Tkinter / UI 部分をモックアウト（UI起動はこのテストのスコープ外）
        import main as main_mod

        dummy_app = mock.MagicMock()
        with (
            mock.patch("main.App", return_value=dummy_app),
            mock.patch("main.threading.Thread"),
            mock.patch("main.check_credentials", return_value=mock.MagicMock(available=False)),
        ):
            main_mod.main()

        # main() 完了後に DB が存在し、app_settings が投入されていることを確認
        import sqlite3

        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT schema_version FROM app_settings WHERE id = 1").fetchone()
        conn.close()

        assert row is not None
        assert row["schema_version"] == CURRENT_SCHEMA_VERSION

        # グローバル接続状態をクリーンアップ
        monkeypatch.setattr(conn_mod, "_connection", None)

    def test_auto_sync_syncs_active_periods(self, monkeypatch):
        """自動同期は collecting / editing の全期間を処理し、同期警告を置き換える。"""
        import main as main_mod

        app = mock.MagicMock()
        app.warnings = [
            main_mod.AppWarning(period_id=1, message="古い同期警告", kind="sync"),
            main_mod.AppWarning(period_id=1, message="別種別警告", kind="form_update"),
        ]

        collecting = {"id": 1, "name": "募集中"}
        editing = {"id": 2, "name": "編集中"}

        posted = []
        app.post_to_ui.side_effect = posted.append

        monkeypatch.setattr(
            main_mod.settings_repo,
            "get",
            lambda: {"credentials_filename": "credentials.json"},
        )
        monkeypatch.setattr(main_mod.auth, "load_credentials", lambda _: object())
        monkeypatch.setattr(main_mod.client, "build_sheets", lambda _: object())
        monkeypatch.setattr(
            main_mod.period_repo,
            "get_by_status",
            lambda status: [collecting] if status == "collecting" else ([editing] if status == "editing" else []),
        )
        monkeypatch.setattr(
            main_mod.staff_repo,
            "get_all",
            lambda: [{"id": 10, "name": "山田", "is_active": 1}],
        )

        def fake_sync_period(period, _svc, staff_map):
            assert staff_map == {"山田": 10}
            if period["id"] == 1:
                return SyncResult(period_id=1, added=2, warnings=["警告A"])
            return SyncResult(period_id=2, added=1, warnings=[])

        monkeypatch.setattr(main_mod, "sync_period", fake_sync_period)

        main_mod._run_auto_sync(app)

        assert [w.kind for w in app.warnings] == ["form_update", "sync"]
        assert app.warnings[1].message == "警告A"
        assert len(posted) == 2

        for callback in posted:
            callback()

        app.status_bar.set_sync_message.assert_called_once_with("自動同期中…")
        app.status_bar.set_timed_sync_message.assert_called_once_with("自動同期完了: 3件追加、1件警告")

    def test_auto_sync_skips_when_credentials_unavailable(self, monkeypatch):
        """credentials がない場合、自動同期は失敗扱いにせず静かにスキップする。"""
        import main as main_mod

        app = mock.MagicMock()
        app.warnings = []
        posted = []
        app.post_to_ui.side_effect = posted.append

        monkeypatch.setattr(
            main_mod.settings_repo,
            "get",
            lambda: {"credentials_filename": "credentials.json"},
        )
        monkeypatch.setattr(main_mod.auth, "load_credentials", lambda _: None)

        main_mod._run_auto_sync(app)

        assert len(posted) == 2
        for callback in posted:
            callback()

        app.status_bar.set_sync_message.assert_any_call("自動同期中…")
        app.status_bar.set_sync_message.assert_any_call("")
