"""StaffScreen._form_update_worker のロジックテスト

Tk を起動せず __new__ + mock でインスタンスを生成し、
フォームプルダウン更新の warnings 管理と shutdown 安全性を検証する。
"""

from __future__ import annotations

from unittest import mock

from src.ui.app import AppWarning
from src.ui.screens.staff_screen import StaffScreen


def _make_screen() -> StaffScreen:
    """StaffScreen を Tk なしで生成する。"""
    screen = StaffScreen.__new__(StaffScreen)
    screen.app = mock.Mock()
    screen.app.warnings = []
    screen.app.is_shutting_down.return_value = False
    return screen


def _run_form_update_worker(screen: StaffScreen, failures: list[dict] | None = None) -> None:
    """_form_update_worker を外部依存をすべてモックして実行するヘルパー。

    完了後、post_to_ui に積まれたコールバックを UI スレッド相当で実行する。
    """
    if failures is None:
        failures = []

    with (
        mock.patch(
            "src.ui.screens.staff_screen.settings_repo.get",
            return_value={"credentials_filename": "creds.json"},
        ),
        mock.patch("src.ui.screens.staff_screen.auth.load_credentials", return_value=mock.Mock()),
        mock.patch("src.ui.screens.staff_screen.client.build_forms", return_value=mock.Mock()),
        mock.patch("src.ui.screens.staff_screen.staff_repo.get_all", return_value=[]),
        mock.patch("src.ui.screens.staff_screen.form_updater_mod.update_all", return_value=failures),
    ):
        screen._form_update_worker()

    if screen.app.post_to_ui.called:
        cb = screen.app.post_to_ui.call_args[0][0]
        cb()


class TestFormUpdateWorkerWarnings:
    def test_no_failures_clears_old_form_update_warnings(self):
        """全フォーム更新成功時、古い form_update 警告がクリアされること。"""
        screen = _make_screen()
        screen.app.warnings = [
            AppWarning(period_id=1, message="フォームプルダウン更新失敗: 旧エラー", kind="form_update"),
            AppWarning(period_id=2, message="フォームプルダウン更新失敗: 別エラー", kind="form_update"),
        ]

        _run_form_update_worker(screen, failures=[])

        assert not any(w.kind == "form_update" for w in screen.app.warnings)

    def test_failures_replace_old_form_update_warnings(self):
        """失敗があった場合、古い form_update 警告が最新の失敗内容に置き換わること。"""
        screen = _make_screen()
        screen.app.warnings = [
            AppWarning(period_id=1, message="フォームプルダウン更新失敗: 旧エラー", kind="form_update"),
        ]

        failures = [{"period_id": 2, "error": "新しいエラー"}]
        _run_form_update_worker(screen, failures=failures)

        form_warnings = [w for w in screen.app.warnings if w.kind == "form_update"]
        assert len(form_warnings) == 1
        assert form_warnings[0].period_id == 2
        assert "新しいエラー" in form_warnings[0].message

    def test_other_kind_warnings_survive(self):
        """form_update 以外の警告は form_update_worker 実行後も消えないこと。"""
        screen = _make_screen()
        screen.app.warnings = [
            AppWarning(period_id=1, message="同期警告", kind="sync"),
            AppWarning(period_id=1, message="フォームプルダウン更新失敗: 旧エラー", kind="form_update"),
        ]

        _run_form_update_worker(screen, failures=[])

        assert any(w.kind == "sync" for w in screen.app.warnings)
        assert not any(w.kind == "form_update" for w in screen.app.warnings)

    def test_repeated_updates_do_not_accumulate(self):
        """スタッフ更新を複数回行っても form_update 警告が蓄積しないこと。"""
        screen = _make_screen()
        failures = [{"period_id": 1, "error": "エラー"}]

        _run_form_update_worker(screen, failures=failures)
        _run_form_update_worker(screen, failures=failures)

        form_warnings = [w for w in screen.app.warnings if w.kind == "form_update"]
        assert len(form_warnings) == 1


class TestFormUpdateWorkerShutdown:
    def test_no_op_when_shutdown_at_start(self):
        """shutdown 中に呼ばれたとき、warnings が変わらないこと。"""
        screen = _make_screen()
        screen.app.warnings = [
            AppWarning(period_id=1, message="既存警告", kind="form_update"),
        ]
        screen.app.is_shutting_down.return_value = True

        _run_form_update_worker(screen, failures=[{"period_id": 2, "error": "エラー"}])

        assert len(screen.app.warnings) == 1
        assert screen.app.warnings[0].message == "既存警告"

    def test_warnings_unchanged_when_shutdown_before_apply(self):
        """ワーカー完了後のコールバック実行時に shutdown 中なら warnings が変わらないこと。"""
        screen = _make_screen()
        original = [AppWarning(period_id=1, message="既存警告", kind="form_update")]
        screen.app.warnings = list(original)

        failures = [{"period_id": 2, "error": "エラー"}]
        with (
            mock.patch(
                "src.ui.screens.staff_screen.settings_repo.get",
                return_value={"credentials_filename": "creds.json"},
            ),
            mock.patch("src.ui.screens.staff_screen.auth.load_credentials", return_value=mock.Mock()),
            mock.patch("src.ui.screens.staff_screen.client.build_forms", return_value=mock.Mock()),
            mock.patch("src.ui.screens.staff_screen.staff_repo.get_all", return_value=[]),
            mock.patch("src.ui.screens.staff_screen.form_updater_mod.update_all", return_value=failures),
        ):
            screen._form_update_worker()

        screen.app.is_shutting_down.return_value = True
        if screen.app.post_to_ui.called:
            cb = screen.app.post_to_ui.call_args[0][0]
            cb()

        assert screen.app.warnings == original

    def test_exception_path_no_ui_update_when_shutdown(self):
        """例外発生時のコールバックも shutdown 中なら status_bar を触らないこと。"""
        screen = _make_screen()

        with (
            mock.patch(
                "src.ui.screens.staff_screen.settings_repo.get",
                return_value={"credentials_filename": "creds.json"},
            ),
            mock.patch(
                "src.ui.screens.staff_screen.auth.load_credentials",
                side_effect=RuntimeError("auth error"),
            ),
        ):
            screen._form_update_worker()

        screen.app.is_shutting_down.return_value = True
        if screen.app.post_to_ui.called:
            cb = screen.app.post_to_ui.call_args[0][0]
            cb()

        screen.app.status_bar.set_timed_sync_message.assert_not_called()
