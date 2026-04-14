"""ShiftEditScreen._apply_undo_redo の統合テスト

Tk を起動せず ShiftEditScreen.__new__ でインスタンスを生成し、
DB は実 SQLite を使って _apply_undo_redo の DB 操作を検証する。
"""

from unittest import mock

import pytest

import src.db.connection as conn_module
from src.db.connection import close_connection, init_connection
from src.db.init_db import init_db
from src.db.repositories import edited_shift_repo, period_repo, staff_repo
from src.logic.undo_redo import UndoEntry
from src.ui.screens.shift_edit_screen import ShiftEditScreen


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


def _make_period():
    return period_repo.create("10月度", "2026-10-21", "2026-11-20", "2026-11-10")


def _make_staff():
    return staff_repo.create("山田太郎", "part_time", 1000)


def _make_screen(period_id: int) -> ShiftEditScreen:
    """ShiftEditScreen を Tk なしで生成し、UI 依存をモックで埋める。"""
    screen = ShiftEditScreen.__new__(ShiftEditScreen)
    screen._period_id = period_id
    screen._grid = mock.Mock()
    screen._grid.selected_cell = None
    screen.set_save_status = mock.Mock()
    screen._on_cell_select = mock.Mock()
    screen._reload_grid = mock.Mock()
    return screen


# ── shift 種別 ────────────────────────────────────────────────────────────────


class TestApplyUndoRedoShift:
    def test_undo_restores_previous_value(self):
        p = _make_period()
        s = _make_staff()
        before = edited_shift_repo.upsert(p["id"], s["id"], "2026-10-21", 9.0, 17.0)
        after = edited_shift_repo.upsert(p["id"], s["id"], "2026-10-21", 10.0, 18.0)

        screen = _make_screen(p["id"])
        entry = UndoEntry("shift", s["id"], p["id"], "2026-10-21", before, after)
        screen._apply_undo_redo(entry, forward=False)

        rec = edited_shift_repo.get_one(p["id"], s["id"], "2026-10-21")
        assert rec["start_time"] == 9.0

    def test_redo_applies_new_value(self):
        p = _make_period()
        s = _make_staff()
        before = edited_shift_repo.upsert(p["id"], s["id"], "2026-10-21", 9.0, 17.0)
        after = edited_shift_repo.upsert(p["id"], s["id"], "2026-10-21", 10.0, 18.0)

        screen = _make_screen(p["id"])
        entry = UndoEntry("shift", s["id"], p["id"], "2026-10-21", before, after)
        screen._apply_undo_redo(entry, forward=True)

        rec = edited_shift_repo.get_one(p["id"], s["id"], "2026-10-21")
        assert rec["start_time"] == 10.0

    def test_undo_to_none_deletes_record(self):
        """before=None の Undo はレコードを削除する（勤務なし NULL/NULL ではない）。"""
        p = _make_period()
        s = _make_staff()
        after = edited_shift_repo.upsert(p["id"], s["id"], "2026-10-21", 9.0, 17.0)

        screen = _make_screen(p["id"])
        entry = UndoEntry("shift", s["id"], p["id"], "2026-10-21", None, after)
        screen._apply_undo_redo(entry, forward=False)

        rec = edited_shift_repo.get_one(p["id"], s["id"], "2026-10-21")
        assert rec is None  # 完全削除 = 未編集状態


# ── bulk 種別 ─────────────────────────────────────────────────────────────────


class TestApplyUndoRedoBulk:
    def test_undo_with_empty_before_removes_all_records(self):
        """before=[] の Undo で一括反映で増えた全レコードが削除される（回帰テスト）。"""
        p = _make_period()
        s = _make_staff()
        edited_shift_repo.upsert(p["id"], s["id"], "2026-10-21", 9.0, 17.0)
        edited_shift_repo.upsert(p["id"], s["id"], "2026-10-22", 10.0, 18.0)
        after_shifts = edited_shift_repo.get_by_period_and_staff(p["id"], s["id"])

        screen = _make_screen(p["id"])
        entry = UndoEntry("bulk", s["id"], p["id"], None, [], after_shifts)
        screen._apply_undo_redo(entry, forward=False)

        remaining = edited_shift_repo.get_by_period_and_staff(p["id"], s["id"])
        assert remaining == []
        screen._reload_grid.assert_called_once()

    def test_redo_restores_bulk_records(self):
        """Redo で after のレコードが再挿入される。"""
        p = _make_period()
        s = _make_staff()
        after_shifts = [
            {"work_date": "2026-10-21", "start_time": 9.0, "end_time": 17.0},
            {"work_date": "2026-10-22", "start_time": 10.0, "end_time": 18.0},
        ]

        screen = _make_screen(p["id"])
        entry = UndoEntry("bulk", s["id"], p["id"], None, [], after_shifts)
        screen._apply_undo_redo(entry, forward=True)

        remaining = edited_shift_repo.get_by_period_and_staff(p["id"], s["id"])
        assert len(remaining) == 2
        dates = {r["work_date"] for r in remaining}
        assert dates == {"2026-10-21", "2026-10-22"}

    def test_undo_partial_before_keeps_only_before_records(self):
        """before に1件だけあった場合、Undo 後もその1件だけ残る。"""
        p = _make_period()
        s = _make_staff()
        edited_shift_repo.upsert(p["id"], s["id"], "2026-10-21", 8.0, 16.0)
        before_shifts = edited_shift_repo.get_by_period_and_staff(p["id"], s["id"])
        # 一括反映で 10/22 が追加された想定
        edited_shift_repo.upsert(p["id"], s["id"], "2026-10-22", 10.0, 18.0)
        after_shifts = edited_shift_repo.get_by_period_and_staff(p["id"], s["id"])

        screen = _make_screen(p["id"])
        entry = UndoEntry("bulk", s["id"], p["id"], None, before_shifts, after_shifts)
        screen._apply_undo_redo(entry, forward=False)

        remaining = edited_shift_repo.get_by_period_and_staff(p["id"], s["id"])
        assert len(remaining) == 1
        assert remaining[0]["work_date"] == "2026-10-21"
