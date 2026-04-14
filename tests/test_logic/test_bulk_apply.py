"""bulk_apply のユニットテスト"""

import pytest

import src.db.connection as conn_module
from src.db.connection import close_connection, init_connection
from src.db.init_db import init_db
from src.db.repositories import edited_shift_repo, period_repo, staff_repo, submission_repo, wish_shift_repo
from src.logic.bulk_apply import bulk_apply


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


def _set_wish_shifts(period_id, staff_id, wishes):
    """wishes = [{"work_date": ..., "start_time": ..., "end_time": ...}]"""
    sub = submission_repo.create(
        period_id,
        staff_id,
        "山田",
        f"key_{period_id}_{staff_id}",
        "2026-10-01 10:00:00",
        None,
        None,
        None,
    )
    shifts_with_sub = [{"submission_id": sub["id"], **w} for w in wishes]
    wish_shift_repo.rebuild_bulk(period_id, staff_id, shifts_with_sub)


def _upsert_edited(period_id, staff_id, date, start, end):
    edited_shift_repo.upsert(period_id, staff_id, date, start, end)


class TestBulkApplyAll:
    def test_all_mode_writes_wish_to_edited(self):
        p = _make_period()
        s = _make_staff()
        _set_wish_shifts(
            p["id"],
            s["id"],
            [
                {"work_date": "2026-10-21", "start_time": 9.0, "end_time": 17.0},
                {"work_date": "2026-10-22", "start_time": 10.0, "end_time": 18.0},
            ],
        )

        result = bulk_apply(p["id"], s["id"], mode="all")

        dates = {r["work_date"] for r in result}
        assert "2026-10-21" in dates
        assert "2026-10-22" in dates
        rec21 = next(r for r in result if r["work_date"] == "2026-10-21")
        assert rec21["start_time"] == 9.0
        assert rec21["end_time"] == 17.0

    def test_all_mode_overwrites_existing_edited(self):
        p = _make_period()
        s = _make_staff()
        _upsert_edited(p["id"], s["id"], "2026-10-21", 8.0, 16.0)
        _set_wish_shifts(
            p["id"],
            s["id"],
            [
                {"work_date": "2026-10-21", "start_time": 9.0, "end_time": 17.0},
            ],
        )

        result = bulk_apply(p["id"], s["id"], mode="all")

        rec = next(r for r in result if r["work_date"] == "2026-10-21")
        assert rec["start_time"] == 9.0  # wish が上書き


class TestBulkApplyEmptyOnly:
    def test_empty_only_fills_missing_dates(self):
        p = _make_period()
        s = _make_staff()
        _upsert_edited(p["id"], s["id"], "2026-10-21", 8.0, 16.0)
        _set_wish_shifts(
            p["id"],
            s["id"],
            [
                {"work_date": "2026-10-21", "start_time": 9.0, "end_time": 17.0},
                {"work_date": "2026-10-22", "start_time": 10.0, "end_time": 18.0},
            ],
        )

        result = bulk_apply(p["id"], s["id"], mode="empty_only")

        rec21 = next(r for r in result if r["work_date"] == "2026-10-21")
        assert rec21["start_time"] == 8.0  # 既存を維持

        rec22 = next((r for r in result if r["work_date"] == "2026-10-22"), None)
        assert rec22 is not None
        assert rec22["start_time"] == 10.0  # 未編集に反映

    def test_empty_only_skips_all_when_all_dates_filled(self):
        p = _make_period()
        s = _make_staff()
        _upsert_edited(p["id"], s["id"], "2026-10-21", 8.0, 16.0)
        _set_wish_shifts(
            p["id"],
            s["id"],
            [
                {"work_date": "2026-10-21", "start_time": 9.0, "end_time": 17.0},
            ],
        )

        result = bulk_apply(p["id"], s["id"], mode="empty_only")

        rec = next(r for r in result if r["work_date"] == "2026-10-21")
        assert rec["start_time"] == 8.0  # 変更なし


class TestBulkApplyEdgeCases:
    def test_empty_wish_shifts_returns_existing_edited(self):
        p = _make_period()
        s = _make_staff()
        _upsert_edited(p["id"], s["id"], "2026-10-21", 8.0, 16.0)
        # wish_shifts は登録しない

        result = bulk_apply(p["id"], s["id"], mode="all")

        assert len(result) == 1
        assert result[0]["start_time"] == 8.0  # 既存が変化しない

    def test_empty_wish_and_no_edited_returns_empty(self):
        p = _make_period()
        s = _make_staff()

        result = bulk_apply(p["id"], s["id"], mode="all")

        assert result == []

    def test_invalid_mode_raises_value_error(self):
        p = _make_period()
        s = _make_staff()

        with pytest.raises(ValueError, match="mode は"):
            bulk_apply(p["id"], s["id"], mode="invalid")
