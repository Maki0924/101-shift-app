"""PeriodDashboardScreen のロジック統合テスト

Tk を起動せず __new__ + mock でインスタンスを生成し、
フォーム自動生成ボタンの有効/無効・失敗時の状態復元・
既存 form_url ありでの確認ダイアログを検証する。
"""

from __future__ import annotations

from unittest import mock

import pytest

import src.db.connection as conn_module
from src.db.connection import close_connection, init_connection
from src.db.init_db import init_db
from src.db.repositories import period_repo
from src.sheets.sync import SyncResult
from src.ui.app import AppWarning
from src.ui.screens.period_dashboard import PeriodDashboardScreen


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(conn_module, "_DB_FILE", db_file)
    monkeypatch.setattr(conn_module, "_connection", None)
    init_connection()
    init_db()
    yield
    close_connection()
    monkeypatch.setattr(conn_module, "_connection", None)


# ── ファクトリ ────────────────────────────────────────────────────────────────


def _make_screen(status: str = "editing", creds: bool = True, form_url: str | None = None) -> PeriodDashboardScreen:
    """PeriodDashboardScreen を Tk なしで生成する。"""
    p = period_repo.create("テスト期間", "2026-10-21", "2026-11-20", "2026-11-10")
    period_repo.update_status(p["id"], status)
    if form_url:
        period_repo.update_form_info(p["id"], form_url, None)

    screen = PeriodDashboardScreen.__new__(PeriodDashboardScreen)
    screen._period_id = p["id"]
    screen._period = period_repo.get_by_id(p["id"])

    screen._form_btn = mock.Mock()
    screen._sync_btn = mock.Mock()
    screen._edit_period_btn = mock.Mock()
    screen._start_edit_btn = mock.Mock()
    screen._archive_btn = mock.Mock()
    screen._unarchive_btn = mock.Mock()
    screen._title_label = mock.Mock()
    screen._info_label = mock.Mock()
    screen._progress_label = mock.Mock()
    screen._warn_btn = mock.Mock()
    screen._form_url_entry = mock.Mock()
    screen._spreadsheet_id_entry = mock.Mock()

    screen.app = mock.Mock()
    screen.app.creds_available = creds
    screen.app.warnings = []
    return screen


# ── ボタン有効/無効 ──────────────────────────────────────────────────────────


class TestFormButtonState:
    def test_enabled_when_editing_with_creds(self):
        """editing + credentials あり → ボタン有効。"""
        screen = _make_screen(status="editing", creds=True)
        screen._update_buttons("editing")
        screen._form_btn.configure.assert_called_with(state="normal")

    def test_enabled_when_collecting_with_creds(self):
        """collecting + credentials あり → ボタン有効。"""
        screen = _make_screen(status="collecting", creds=True)
        screen._update_buttons("collecting")
        screen._form_btn.configure.assert_called_with(state="normal")

    def test_disabled_when_archived(self):
        """archived → credentials があっても disabled。"""
        screen = _make_screen(status="archived", creds=True)
        screen._update_buttons("archived")
        screen._form_btn.configure.assert_called_with(state="disabled")

    def test_disabled_without_creds(self):
        """credentials なし → editing でも disabled。"""
        screen = _make_screen(status="editing", creds=False)
        screen._update_buttons("editing")
        screen._form_btn.configure.assert_called_with(state="disabled")


# ── 失敗時のボタン状態復元 ───────────────────────────────────────────────────


class TestFormErrorRecovery:
    def test_on_form_error_calls_load(self):
        """失敗時は _load() を呼んで期間の現ステータスから状態を再設定する。"""
        screen = _make_screen(status="editing", creds=True)
        screen.winfo_exists = mock.Mock(return_value=True)

        with mock.patch.object(screen, "_load") as mock_load, mock.patch("src.ui.screens.period_dashboard.show_error"):
            screen._on_form_error("API error")

        mock_load.assert_called_once()

    def test_on_form_error_archived_does_not_re_enable(self):
        """処理中に archived に変わった場合、_load() 経由でボタンが disabled のままになる。"""
        screen = _make_screen(status="editing", creds=True)
        screen.winfo_exists = mock.Mock(return_value=True)

        # _load() 内で _update_buttons("archived") が呼ばれる状況を再現
        def fake_load():
            screen._update_buttons("archived")

        with (
            mock.patch.object(screen, "_load", side_effect=fake_load),
            mock.patch("src.ui.screens.period_dashboard.show_error"),
        ):
            screen._on_form_error("API error")

        # archived なので disabled になるはず
        screen._form_btn.configure.assert_called_with(state="disabled")


# ── 既存 form_url ありの確認ダイアログ ───────────────────────────────────────


class TestFormUrlOverwriteConfirm:
    def test_confirm_shown_when_form_url_exists(self):
        """既存 form_url がある場合、確認ダイアログが表示される。"""
        screen = _make_screen(form_url="https://forms.example.com/existing")

        with (
            mock.patch("src.ui.screens.period_dashboard.ask_confirm", return_value=False) as mock_confirm,
            mock.patch.object(screen, "winfo_exists", return_value=True),
        ):
            screen._on_create_form()

        mock_confirm.assert_called_once()

    def test_no_action_when_confirm_declined(self):
        """確認ダイアログで「いいえ」を選ぶとスレッドが起動されない。"""
        screen = _make_screen(form_url="https://forms.example.com/existing")

        with (
            mock.patch("src.ui.screens.period_dashboard.ask_confirm", return_value=False),
            mock.patch("threading.Thread") as mock_thread,
            mock.patch.object(screen, "winfo_exists", return_value=True),
        ):
            screen._on_create_form()

        mock_thread.assert_not_called()

    def test_no_confirm_when_no_form_url(self):
        """form_url がない場合は確認ダイアログなしで直接スレッド起動。"""
        screen = _make_screen(form_url=None)
        screen._period["form_url"] = None

        with (
            mock.patch("src.ui.screens.period_dashboard.ask_confirm") as mock_confirm,
            mock.patch("threading.Thread") as mock_thread,
        ):
            mock_thread.return_value = mock.Mock()
            screen._on_create_form()

        mock_confirm.assert_not_called()
        mock_thread.assert_called_once()


# ── 同期警告の種別管理 ────────────────────────────────────────────────────────


def _run_sync_worker(screen: PeriodDashboardScreen, sync_result: SyncResult) -> None:
    """_sync_worker を外部依存をすべてモックして実行するヘルパー。"""
    pid = screen._period_id
    with (
        mock.patch(
            "src.ui.screens.period_dashboard.settings_repo.get",
            return_value={"credentials_filename": "creds.json"},
        ),
        mock.patch("src.ui.screens.period_dashboard.auth.load_credentials", return_value=mock.Mock()),
        mock.patch("src.ui.screens.period_dashboard.client.build_sheets", return_value=mock.Mock()),
        mock.patch(
            "src.ui.screens.period_dashboard.period_repo.get_by_status",
            side_effect=lambda s: [period_repo.get_by_id(pid)] if s == "collecting" else [],
        ),
        mock.patch("src.ui.screens.period_dashboard.staff_repo.get_all", return_value=[]),
        mock.patch("src.ui.screens.period_dashboard.sync_period", return_value=sync_result),
    ):
        screen._sync_worker()


class TestSyncWarningKind:
    def test_resync_replaces_sync_warnings_only(self):
        """再同期で同期由来の警告だけが新しい内容に置き換わる。"""
        screen = _make_screen(status="collecting")
        pid = screen._period_id

        # 同種別の旧警告とフォーム更新失敗警告を事前に積む
        screen.app.warnings = [
            AppWarning(period_id=pid, message="古い同期警告", kind="sync"),
            AppWarning(period_id=pid, message="フォームプルダウン更新失敗: 旧エラー", kind="form_update"),
        ]

        result = SyncResult(period_id=pid, added=0, warnings=["新しい同期警告"])
        _run_sync_worker(screen, result)

        sync_warnings = [w for w in screen.app.warnings if w.kind == "sync"]
        assert len(sync_warnings) == 1
        assert sync_warnings[0].message == "新しい同期警告"

    def test_form_update_warning_survives_sync(self):
        """フォーム更新失敗警告は手動同期後も消えない。"""
        screen = _make_screen(status="collecting")
        pid = screen._period_id

        screen.app.warnings = [
            AppWarning(period_id=pid, message="フォームプルダウン更新失敗: permission denied", kind="form_update"),
        ]

        # sync_period が警告なしで完了してもフォーム警告は残る
        result = SyncResult(period_id=pid, added=2, warnings=[])
        _run_sync_worker(screen, result)

        assert any(w.kind == "form_update" for w in screen.app.warnings)
        assert not any(w.kind == "sync" for w in screen.app.warnings)


class TestRefreshAfterDataChange:
    def test_refresh_after_data_change_calls_load_when_alive(self):
        screen = _make_screen()
        screen.winfo_exists = mock.Mock(return_value=True)

        with mock.patch.object(screen, "_load") as mock_load:
            screen.refresh_after_data_change()

        mock_load.assert_called_once()
