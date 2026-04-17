"""PrintScreen のロジック統合テスト

Tk を起動せず __new__ + mock でインスタンスを生成し、
_compute_and_draw（日付範囲）と _on_print（設定保存）の挙動を検証する。
"""

from __future__ import annotations

from unittest import mock

import pytest

import src.db.connection as conn_module
from src.db.connection import close_connection, init_connection
from src.db.init_db import init_db
from src.db.repositories import period_repo, print_settings_repo, staff_repo
from src.logic.print_layout import Page, PageLayout
from src.ui.screens.print_screen import PrintScreen


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


def _make_period(status: str = "editing") -> dict:
    p = period_repo.create("10月度", "2026-10-21", "2026-11-20", "2026-11-10")
    period_repo.update_status(p["id"], status)
    return period_repo.get_by_id(p["id"])


def _make_staff() -> dict:
    return staff_repo.create("山田", "part_time", 1000)


def _make_screen(period: dict, from_str: str, to_str: str) -> PrintScreen:
    """PrintScreen を Tk なしで生成する。"""
    screen = PrintScreen.__new__(PrintScreen)
    screen._period_id = period["id"]
    screen._period = period
    screen._staff_list = []
    screen._edited = {}
    screen._marks = {}
    screen._rules = []
    screen._layout = None
    screen._current_page = 0

    # StringVar の代わりに get() を持つ mock
    screen._from_var = mock.Mock()
    screen._from_var.get.return_value = from_str
    screen._to_var = mock.Mock()
    screen._to_var.get.return_value = to_str
    screen._font_size_var = mock.Mock()
    screen._font_size_var.get.return_value = "10"

    # Tk ウィジェットをすべて mock
    screen._canvas = mock.Mock()
    screen._prev_btn = mock.Mock()
    screen._next_btn = mock.Mock()
    screen._page_lbl = mock.Mock()
    screen._print_btn = mock.Mock()
    return screen


def _one_page_layout(dates: list[str], staff: list[dict]) -> PageLayout:
    """テスト用の最小 PageLayout。"""
    page = Page(dates=dates, staff=staff, col_w_mm=12.0, row_h_mm=6.0, font_size=10)
    return PageLayout(pages=[page])


# ── 印刷範囲が期間外でも列が出ること ──────────────────────────────────────────


class TestDateRangeNotClamped:
    def test_before_period_start_included(self):
        """印刷開始日が期間開始日より前でも、その日付が列として含まれる。"""
        p = _make_period()
        st = _make_staff()
        # 期間は 10/21〜11/20 だが、印刷範囲を 10/01〜10/31 に設定
        screen = _make_screen(p, "2026-10-01", "2026-10-31")
        screen._staff_list = [st]

        screen._compute_and_draw()

        all_dates = [d for page in screen._layout.pages for d in page.dates]
        assert "2026-10-01" in all_dates  # 期間開始(10/21)より前
        assert "2026-10-20" in all_dates  # 期間開始の前日
        assert "2026-10-21" in all_dates  # 期間内

    def test_after_period_end_included(self):
        """印刷終了日が期間終了日より後でも、その日付が列として含まれる。"""
        p = _make_period()
        st = _make_staff()
        # 11/21〜11/25 は期間終了(11/20)より後
        screen = _make_screen(p, "2026-11-15", "2026-11-25")
        screen._staff_list = [st]

        screen._compute_and_draw()

        all_dates = [d for page in screen._layout.pages for d in page.dates]
        assert "2026-11-20" in all_dates  # 期間内（最終日）
        assert "2026-11-21" in all_dates  # 期間終了翌日
        assert "2026-11-25" in all_dates  # 期間終了後

    def test_exact_range_no_extras(self):
        """指定した from/to の日付だけが列になる（余計な列はない）。"""
        p = _make_period()
        st = _make_staff()
        screen = _make_screen(p, "2026-10-05", "2026-10-07")
        screen._staff_list = [st]

        screen._compute_and_draw()

        all_dates = [d for page in screen._layout.pages for d in page.dates]
        assert all_dates == ["2026-10-05", "2026-10-06", "2026-10-07"]

    def test_full_out_of_period_range_generates_layout(self):
        """期間と全く重複しない日付範囲でもレイアウトが生成される。"""
        p = _make_period()
        st = _make_staff()
        # 期間: 10/21〜11/20、印刷範囲: 10/01〜10/10（完全に期間外）
        screen = _make_screen(p, "2026-10-01", "2026-10-10")
        screen._staff_list = [st]

        screen._compute_and_draw()

        assert screen._layout is not None
        assert screen._layout.page_count >= 1
        all_dates = [d for page in screen._layout.pages for d in page.dates]
        assert len(all_dates) == 10


# ── archived で設定保存しないこと ─────────────────────────────────────────────


class TestPrintSettingsSave:
    def test_archived_does_not_save_settings(self):
        """archived 期間は印刷後に print_settings_repo.upsert を呼ばない。"""
        p = _make_period(status="archived")
        st = _make_staff()
        screen = _make_screen(p, p["start_date"], p["end_date"])
        screen._staff_list = [st]
        screen._layout = _one_page_layout([p["start_date"]], [st])

        with mock.patch("src.logic.printer.print_shift"):
            screen._on_print()

        # DB に保存されていないこと
        assert print_settings_repo.get_by_period(p["id"]) is None

    def test_editing_saves_from_to_after_print(self):
        """editing 期間は印刷後に from/to が DB に保存される。"""
        p = _make_period(status="editing")
        st = _make_staff()
        screen = _make_screen(p, "2026-10-21", "2026-11-20")
        screen._staff_list = [st]
        screen._layout = _one_page_layout(["2026-10-21"], [st])

        with mock.patch("src.logic.printer.print_shift"):
            screen._on_print()

        saved = print_settings_repo.get_by_period(p["id"])
        assert saved is not None
        assert saved["print_from_date"] == "2026-10-21"
        assert saved["print_to_date"] == "2026-11-20"

    def test_archived_does_not_save_even_with_out_of_period_range(self):
        """archived × 期間外範囲でも保存されない（複合条件の回帰テスト）。"""
        p = _make_period(status="archived")
        st = _make_staff()
        # 期間外の日付を指定
        screen = _make_screen(p, "2026-10-01", "2026-12-31")
        screen._staff_list = [st]
        screen._layout = _one_page_layout(["2026-10-01"], [st])

        with mock.patch("src.logic.printer.print_shift"):
            screen._on_print()

        assert print_settings_repo.get_by_period(p["id"]) is None
