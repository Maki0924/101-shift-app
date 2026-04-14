"""ダイアログの保存失敗時クローズ制御テスト

- on_save が False を返した場合はダイアログを閉じない
- on_save が True を返した場合はダイアログを閉じる
"""

from unittest import mock

from src.ui.screens.settings_screen import _CustomDayDialog
from src.ui.screens.staff_screen import _StaffDialog


class _FakeEntry:
    """Tkinter Entry の最小スタブ。"""

    def __init__(self, value: str = "") -> None:
        self._value = value

    def get(self) -> str:
        return self._value

    def focus_set(self) -> None:
        pass

    def configure(self, **_kwargs) -> None:
        pass


class _FakeVar:
    def __init__(self, value="") -> None:
        self._value = value

    def get(self):
        return self._value

    def set(self, v) -> None:
        self._value = v


def _make_staff_dialog(on_save):
    """_StaffDialog を Tk 初期化なしで生成する。"""
    dlg = _StaffDialog.__new__(_StaffDialog)
    dlg._staff = None
    dlg._on_save = on_save
    dlg._name_var = _FakeVar("田中 太郎")
    dlg._type_var = _FakeVar("バイト")
    dlg._wage_var = _FakeVar("1000")
    dlg._sort_var = _FakeVar("0")
    dlg.destroy = mock.Mock()
    return dlg


def _make_custom_dialog(on_save):
    """_CustomDayDialog を Tk 初期化なしで生成する。"""
    dlg = _CustomDayDialog.__new__(_CustomDayDialog)
    dlg._rule = None
    dlg._on_save = on_save
    dlg._date_var = _FakeVar("2026-05-05")
    dlg._holiday_var = _FakeVar(False)
    dlg._exclude_var = _FakeVar(False)
    dlg._bonus_var = _FakeVar("")
    dlg._note_var = _FakeVar("")
    dlg.destroy = mock.Mock()
    return dlg


class TestStaffDialogCloseControl:
    def test_dialog_stays_open_on_save_failure(self):
        """on_save が False を返した場合、ダイアログを閉じない。"""
        on_save = mock.Mock(return_value=False)
        dlg = _make_staff_dialog(on_save)

        with mock.patch("src.ui.screens.staff_screen.staff_repo.get_by_name", return_value=None):
            dlg._on_ok()

        on_save.assert_called_once()
        dlg.destroy.assert_not_called()

    def test_dialog_closes_on_save_success(self):
        """on_save が True を返した場合、ダイアログを閉じる。"""
        on_save = mock.Mock(return_value=True)
        dlg = _make_staff_dialog(on_save)

        with mock.patch("src.ui.screens.staff_screen.staff_repo.get_by_name", return_value=None):
            dlg._on_ok()

        on_save.assert_called_once()
        dlg.destroy.assert_called_once()


class TestCustomDayDialogCloseControl:
    def test_dialog_stays_open_on_save_failure(self):
        """on_save が False を返した場合、ダイアログを閉じない。"""
        on_save = mock.Mock(return_value=False)
        dlg = _make_custom_dialog(on_save)

        dlg._on_ok()

        on_save.assert_called_once()
        dlg.destroy.assert_not_called()

    def test_dialog_closes_on_save_success(self):
        """on_save が True を返した場合、ダイアログを閉じる。"""
        on_save = mock.Mock(return_value=True)
        dlg = _make_custom_dialog(on_save)

        dlg._on_ok()

        on_save.assert_called_once()
        dlg.destroy.assert_called_once()
