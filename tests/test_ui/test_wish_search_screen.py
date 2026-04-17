"""WishSearchScreen._on_search のロジック統合テスト

Tk を起動せず __new__ + mock でインスタンスを生成し、
雇用形態フィルターと結果並び順を検証する。
DB アクセスは _on_search 内で発生しないため実 DB 不要。
"""

from __future__ import annotations

from unittest import mock

from src.ui.screens.wish_search_screen import WishSearchScreen

# ── ファクトリ ────────────────────────────────────────────────────────────────


def _make_screen() -> WishSearchScreen:
    """WishSearchScreen を Tk なしで生成する。"""
    screen = WishSearchScreen.__new__(WishSearchScreen)
    screen._period_id = 1
    screen._period = {"id": 1, "name": "test", "start_date": "2026-10-01", "end_date": "2026-10-31"}
    screen._staff_map = {}
    screen._wish_shifts = []
    screen._edited_by_staff = {}
    screen._submission_map = {}

    # StringVar の代わりに get() を持つ mock
    screen._date_var = mock.Mock()
    screen._date_var.get.return_value = "2026-10-05"
    screen._start_var = mock.Mock()
    screen._start_var.get.return_value = ""  # 時間帯フィルターなし
    screen._end_var = mock.Mock()
    screen._end_var.get.return_value = ""
    screen._emp_var = mock.Mock()
    screen._emp_var.get.return_value = "全員"
    screen._confirmed_var = mock.Mock()
    screen._confirmed_var.get.return_value = "全員"

    # Treeview mock
    screen._tree = mock.Mock()
    screen._tree.get_children.return_value = []
    screen._count_lbl = mock.Mock()
    return screen


def _staff(staff_id: int, name: str, emp_type: str) -> dict:
    return {"id": staff_id, "name": name, "employment_type": emp_type}


def _wish(staff_id: int, work_date: str, start: float, end: float, sub_id: int = 1) -> dict:
    return {
        "staff_id": staff_id,
        "work_date": work_date,
        "start_time": start,
        "end_time": end,
        "submission_id": sub_id,
    }


def _inserted_names(screen: WishSearchScreen) -> list[str]:
    """Treeview に insert された行のスタッフ名一覧を返す。"""
    return [call.kwargs["values"][0] for call in screen._tree.insert.call_args_list]


# ── 雇用形態フィルター ────────────────────────────────────────────────────────


class TestEmploymentTypeFilter:
    def test_employee_filter_shows_only_employee(self):
        """社員フィルター: employee のみヒット、part_time は除外される。"""
        screen = _make_screen()
        screen._date_var.get.return_value = "2026-10-05"
        screen._emp_var.get.return_value = "社員"

        pt = _staff(1, "バイト太郎", "part_time")
        em = _staff(2, "社員花子", "employee")
        screen._staff_map = {1: pt, 2: em}
        screen._wish_shifts = [
            _wish(1, "2026-10-05", 9.0, 17.0),
            _wish(2, "2026-10-05", 9.0, 17.0),
        ]

        screen._on_search()

        names = _inserted_names(screen)
        assert "社員花子" in names
        assert "バイト太郎" not in names

    def test_part_time_filter_shows_only_part_time(self):
        """バイトフィルター: part_time のみヒット、employee は除外される。"""
        screen = _make_screen()
        screen._date_var.get.return_value = "2026-10-05"
        screen._emp_var.get.return_value = "バイト"

        pt = _staff(1, "バイト太郎", "part_time")
        em = _staff(2, "社員花子", "employee")
        screen._staff_map = {1: pt, 2: em}
        screen._wish_shifts = [
            _wish(1, "2026-10-05", 9.0, 17.0),
            _wish(2, "2026-10-05", 9.0, 17.0),
        ]

        screen._on_search()

        names = _inserted_names(screen)
        assert "バイト太郎" in names
        assert "社員花子" not in names

    def test_all_filter_shows_both_types(self):
        """全員フィルター: part_time / employee どちらも表示される。"""
        screen = _make_screen()
        screen._date_var.get.return_value = "2026-10-05"
        screen._emp_var.get.return_value = "全員"

        screen._staff_map = {
            1: _staff(1, "バイト太郎", "part_time"),
            2: _staff(2, "社員花子", "employee"),
        }
        screen._wish_shifts = [
            _wish(1, "2026-10-05", 9.0, 17.0),
            _wish(2, "2026-10-05", 9.0, 17.0),
        ]

        screen._on_search()

        names = _inserted_names(screen)
        assert "バイト太郎" in names
        assert "社員花子" in names

    def test_employee_type_string_is_not_full_time(self):
        """社員の DB 値が "employee" であること（"full_time" ではない）の回帰テスト。

        "full_time" にマップしていた場合、employee は常に0件になるバグを防ぐ。
        """
        from src.ui.screens.wish_search_screen import _EMP_TYPE_MAP

        assert _EMP_TYPE_MAP["社員"] == "employee", '社員フィルターは "employee" にマップすること（DB スキーマ準拠）'


# ── 結果並び順 ────────────────────────────────────────────────────────────────


class TestSortOrder:
    def test_sorted_by_wish_start_time_ascending(self):
        """希望開始時刻の早い順に並ぶ。"""
        screen = _make_screen()
        screen._date_var.get.return_value = "2026-10-05"

        # staff_map の挿入順がスタッフ表示順（A=0, B=1, C=2）
        a = _staff(1, "A", "part_time")
        b = _staff(2, "B", "part_time")
        c = _staff(3, "C", "part_time")
        screen._staff_map = {1: a, 2: b, 3: c}

        # 開始時刻: A=11:00, B=9:00, C=10:00 → 期待順 B, C, A
        screen._wish_shifts = [
            _wish(1, "2026-10-05", 11.0, 19.0),
            _wish(2, "2026-10-05", 9.0, 17.0),
            _wish(3, "2026-10-05", 10.0, 18.0),
        ]

        screen._on_search()

        names = _inserted_names(screen)
        assert names == ["B", "C", "A"]

    def test_same_start_time_uses_staff_display_order(self):
        """同じ開始時刻の場合はスタッフ表示順（staff_map の挿入順）で並ぶ。"""
        screen = _make_screen()
        screen._date_var.get.return_value = "2026-10-05"

        # staff_map: X=0, Y=1（挿入順がスタッフ表示順）
        x = _staff(10, "X", "part_time")
        y = _staff(20, "Y", "part_time")
        screen._staff_map = {10: x, 20: y}

        # 同じ開始時刻 → 表示順 X, Y が維持されること
        screen._wish_shifts = [
            _wish(20, "2026-10-05", 9.0, 17.0),  # Y を先に追加
            _wish(10, "2026-10-05", 9.0, 17.0),  # X を後に追加
        ]

        screen._on_search()

        names = _inserted_names(screen)
        assert names == ["X", "Y"]

    def test_different_date_not_included(self):
        """検索日と異なる日付の希望シフトは結果に含まれない。"""
        screen = _make_screen()
        screen._date_var.get.return_value = "2026-10-05"

        st = _staff(1, "山田", "part_time")
        screen._staff_map = {1: st}
        # 異なる日付の希望シフト
        screen._wish_shifts = [_wish(1, "2026-10-06", 9.0, 17.0)]

        screen._on_search()

        assert _inserted_names(screen) == []


# ── 時間帯重複フィルター ──────────────────────────────────────────────────────


class TestTimeOverlapFilter:
    def test_overlapping_wish_included(self):
        """検索時間帯と重複する希望シフトは結果に含まれる。"""
        screen = _make_screen()
        screen._date_var.get.return_value = "2026-10-05"
        screen._start_var.get.return_value = "10:00"
        screen._end_var.get.return_value = "14:00"

        st = _staff(1, "重複あり", "part_time")
        screen._staff_map = {1: st}
        # 9:00-13:00: 検索 10:00-14:00 と 3時間重複
        screen._wish_shifts = [_wish(1, "2026-10-05", 9.0, 13.0)]

        screen._on_search()

        assert "重複あり" in _inserted_names(screen)

    def test_non_overlapping_wish_excluded(self):
        """検索時間帯と重複しない希望シフトは除外される。"""
        screen = _make_screen()
        screen._date_var.get.return_value = "2026-10-05"
        screen._start_var.get.return_value = "15:00"
        screen._end_var.get.return_value = "20:00"

        st = _staff(1, "重複なし", "part_time")
        screen._staff_map = {1: st}
        # 9:00-13:00: 検索 15:00-20:00 と重複なし
        screen._wish_shifts = [_wish(1, "2026-10-05", 9.0, 13.0)]

        screen._on_search()

        assert _inserted_names(screen) == []
