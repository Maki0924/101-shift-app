"""リポジトリ層テスト（periods / staff / app_settings）"""

import pytest

from src.db import connection as conn_module
from src.db.connection import close_connection, init_connection
from src.db.init_db import init_db
from src.db.repositories import period_repo, settings_repo, staff_repo


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


# ── period_repo ───────────────────────────────────────────────────────────────

class TestPeriodRepo:
    def test_create_and_get(self):
        p = period_repo.create("10月度", "2026-10-21", "2026-11-20", "2026-11-10")
        assert p["name"] == "10月度"
        assert p["status"] == "collecting"
        assert period_repo.get_by_id(p["id"]) is not None

    def test_get_all_returns_all(self):
        period_repo.create("A", "2026-10-21", "2026-11-20", "2026-11-10")
        period_repo.create("B", "2026-11-21", "2026-12-20", "2026-12-10")
        assert len(period_repo.get_all()) == 2

    def test_update(self):
        p = period_repo.create("旧名", "2026-10-21", "2026-11-20", "2026-11-10")
        updated = period_repo.update(p["id"], "新名", "2026-10-21", "2026-11-20", "2026-11-10")
        assert updated["name"] == "新名"

    def test_update_status(self):
        p = period_repo.create("A", "2026-10-21", "2026-11-20", "2026-11-10")
        updated = period_repo.update_status(p["id"], "editing")
        assert updated["status"] == "editing"

    def test_get_by_status(self):
        p1 = period_repo.create("A", "2026-10-21", "2026-11-20", "2026-11-10")
        p2 = period_repo.create("B", "2026-11-21", "2026-12-20", "2026-12-10")
        period_repo.update_status(p2["id"], "archived")
        collecting = period_repo.get_by_status("collecting")
        assert len(collecting) == 1
        assert collecting[0]["id"] == p1["id"]

    def test_delete(self):
        p = period_repo.create("A", "2026-10-21", "2026-11-20", "2026-11-10")
        period_repo.delete(p["id"])
        assert period_repo.get_by_id(p["id"]) is None

    def test_update_form_info(self):
        p = period_repo.create("A", "2026-10-21", "2026-11-20", "2026-11-10")
        updated = period_repo.update_form_info(p["id"], "https://forms.example.com", "sheet123")
        assert updated["form_url"] == "https://forms.example.com"
        assert updated["spreadsheet_id"] == "sheet123"

    def test_get_by_id_not_found(self):
        assert period_repo.get_by_id(9999) is None


class TestPeriodOverlap:
    def test_no_overlap(self):
        period_repo.create("A", "2026-10-21", "2026-11-20", "2026-11-10")
        assert not period_repo.has_overlap("2026-11-21", "2026-12-20")

    def test_overlap_detected(self):
        period_repo.create("A", "2026-10-21", "2026-11-20", "2026-11-10")
        assert period_repo.has_overlap("2026-11-01", "2026-12-01")

    def test_boundary_inclusive(self):
        """境界日（end_date と start_date が同日）は重複とみなす。"""
        period_repo.create("A", "2026-10-21", "2026-11-20", "2026-11-10")
        assert period_repo.has_overlap("2026-11-20", "2026-12-20")

    def test_exclude_self_on_edit(self):
        """編集時に自己IDを除外すると重複しない。"""
        p = period_repo.create("A", "2026-10-21", "2026-11-20", "2026-11-10")
        assert not period_repo.has_overlap("2026-10-21", "2026-11-20", exclude_id=p["id"])

    def test_contained_overlap(self):
        """既存期間に完全に含まれる範囲も重複とみなす。"""
        period_repo.create("A", "2026-10-01", "2026-10-31", "2026-10-10")
        assert period_repo.has_overlap("2026-10-10", "2026-10-20")


# ── staff_repo ────────────────────────────────────────────────────────────────

class TestStaffRepo:
    def test_create_and_get(self):
        s = staff_repo.create("田中", "part_time", 1100)
        assert s["name"] == "田中"
        assert s["is_active"] == 1
        assert staff_repo.get_by_id(s["id"]) is not None

    def test_get_by_name(self):
        staff_repo.create("佐藤", "employee", 1200)
        s = staff_repo.get_by_name("佐藤")
        assert s is not None
        assert s["employment_type"] == "employee"

    def test_get_by_name_not_found(self):
        assert staff_repo.get_by_name("存在しない") is None

    def test_unique_name_constraint(self):
        import sqlite3
        staff_repo.create("山田", "part_time", 1000)
        with pytest.raises(sqlite3.IntegrityError):
            staff_repo.create("山田", "part_time", 1100)

    def test_update(self):
        s = staff_repo.create("田中", "part_time", 1000)
        updated = staff_repo.update(s["id"], "田中太郎", "employee", 1500, 5)
        assert updated["name"] == "田中太郎"
        assert updated["hourly_wage"] == 1500

    def test_set_active_false(self):
        s = staff_repo.create("田中", "part_time", 1000)
        updated = staff_repo.set_active(s["id"], False)
        assert updated["is_active"] == 0

    def test_get_active_excludes_inactive(self):
        s1 = staff_repo.create("有効", "part_time", 1000)
        s2 = staff_repo.create("無効", "part_time", 1000)
        staff_repo.set_active(s2["id"], False)
        active = staff_repo.get_active()
        ids = [s["id"] for s in active]
        assert s1["id"] in ids
        assert s2["id"] not in ids


class TestStaffSortOrder:
    def test_sort_order_asc(self):
        """sort_order 昇順で返る。"""
        staff_repo.create("C", "part_time", 1000, sort_order=3)
        staff_repo.create("A", "part_time", 1000, sort_order=1)
        staff_repo.create("B", "part_time", 1000, sort_order=2)
        names = [s["name"] for s in staff_repo.get_all()]
        assert names == ["A", "B", "C"]

    def test_active_before_inactive_same_sort_order(self):
        """同一 sort_order では有効スタッフが先。"""
        s_inactive = staff_repo.create("無効", "part_time", 1000, sort_order=0)
        staff_repo.set_active(s_inactive["id"], False)
        staff_repo.create("有効", "part_time", 1000, sort_order=0)
        names = [s["name"] for s in staff_repo.get_all()]
        assert names.index("有効") < names.index("無効")

    def test_part_time_before_employee_same_sort_order(self):
        """同一 sort_order・同一 is_active では part_time が先。"""
        staff_repo.create("社員", "employee", 2000, sort_order=0)
        staff_repo.create("バイト", "part_time", 1000, sort_order=0)
        names = [s["name"] for s in staff_repo.get_all()]
        assert names.index("バイト") < names.index("社員")

    def test_get_for_period_includes_inactive_with_data(self, tmp_path):
        """期間にデータがある無効スタッフは get_for_period に含まれる。"""
        from src.db.connection import transaction

        p = period_repo.create("A", "2026-10-21", "2026-11-20", "2026-11-10")
        s_active = staff_repo.create("有効", "part_time", 1000)
        s_inactive = staff_repo.create("無効（データあり）", "part_time", 1000)
        staff_repo.set_active(s_inactive["id"], False)
        s_no_data = staff_repo.create("無効（データなし）", "part_time", 1000)
        staff_repo.set_active(s_no_data["id"], False)

        # s_inactive に edited_shifts を挿入
        now = "2026-10-21 00:00:00"
        with transaction() as txn:
            txn.execute(
                "INSERT INTO edited_shifts (period_id, staff_id, work_date, created_at, updated_at) "
                "VALUES (?, ?, '2026-10-21', ?, ?)",
                (p["id"], s_inactive["id"], now, now),
            )

        result_ids = {s["id"] for s in staff_repo.get_for_period(p["id"])}
        assert s_active["id"] in result_ids
        assert s_inactive["id"] in result_ids
        assert s_no_data["id"] not in result_ids


# ── settings_repo ─────────────────────────────────────────────────────────────

class TestSettingsRepo:
    def test_get_returns_defaults(self):
        s = settings_repo.get()
        assert s is not None
        assert s["schema_version"] == 1
        assert s["day_shift_start"] == 8
        assert s["print_font_size"] == 9

    def test_update(self):
        updated = settings_repo.update(
            day_shift_start=9,
            day_shift_end=18,
            night_shift_start=18,
            night_shift_end=23,
            overlap_hours_threshold=1.5,
            saturday_bonus=200,
            sunday_bonus=200,
            holiday_bonus=200,
            weekday_day_min_staff=3,
            weekday_night_min_staff=3,
            weekend_day_min_staff=6,
            weekend_night_min_staff=4,
            print_font_size=10,
        )
        assert updated["day_shift_start"] == 9
        assert updated["saturday_bonus"] == 200
        assert updated["print_font_size"] == 10

    def test_update_persists(self):
        settings_repo.update(
            day_shift_start=10, day_shift_end=19,
            night_shift_start=19, night_shift_end=23,
            overlap_hours_threshold=2,
            saturday_bonus=150, sunday_bonus=150, holiday_bonus=150,
            weekday_day_min_staff=2, weekday_night_min_staff=2,
            weekend_day_min_staff=5, weekend_night_min_staff=3,
            print_font_size=11,
        )
        assert settings_repo.get()["day_shift_start"] == 10
