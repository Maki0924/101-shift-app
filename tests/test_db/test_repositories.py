"""リポジトリ層テスト（periods / staff / app_settings / submissions / wish_shifts /
edited_shifts / memo / mark / custom_day / print_settings）"""

import pytest

from src.db import connection as conn_module
from src.db.connection import close_connection, init_connection
from src.db.init_db import init_db
from src.db.repositories import (
    custom_day_repo,
    edited_shift_repo,
    mark_repo,
    memo_repo,
    period_repo,
    print_settings_repo,
    settings_repo,
    staff_repo,
    submission_repo,
    wish_shift_repo,
)


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
        assert s["schema_version"] == 2
        assert s["day_shift_start"] == 8
        assert s["print_font_size"] == 9
        assert s["credentials_filename"] == "credentials.json"

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
            credentials_filename="my-creds.json",
        )
        assert updated["day_shift_start"] == 9
        assert updated["saturday_bonus"] == 200
        assert updated["print_font_size"] == 10
        assert updated["credentials_filename"] == "my-creds.json"

    def test_update_persists(self):
        settings_repo.update(
            day_shift_start=10, day_shift_end=19,
            night_shift_start=19, night_shift_end=23,
            overlap_hours_threshold=2,
            saturday_bonus=150, sunday_bonus=150, holiday_bonus=150,
            weekday_day_min_staff=2, weekday_night_min_staff=2,
            weekend_day_min_staff=5, weekend_night_min_staff=3,
            print_font_size=11,
            credentials_filename="credentials.json",
        )
        assert settings_repo.get()["day_shift_start"] == 10


# ── ヘルパー ───────────────────────────────────────────────────────────────────

def _make_period():
    return period_repo.create("10月度", "2026-10-21", "2026-11-20", "2026-11-10")


def _make_staff(name="田中", employment_type="part_time"):
    return staff_repo.create(name, employment_type, 1000)


def _make_submission(period_id, staff_id=None, key="key1"):
    return submission_repo.create(
        period_id=period_id,
        staff_id=staff_id,
        raw_staff_name="田中",
        external_submission_key=key,
        submitted_at="2026-10-10 12:00:00",
        note_text=None,
        weekly_pref_min=3,
        weekly_pref_max=3,
    )


# ── submission_repo ───────────────────────────────────────────────────────────

class TestSubmissionRepo:
    def test_create_without_staff_id_is_not_latest(self):
        """未紐付け回答は is_latest_for_staff=0 固定。"""
        p = _make_period()
        sub = _make_submission(p["id"], staff_id=None)
        assert sub["apply_status"] == "pending"
        assert sub["is_latest_for_staff"] == 0

    def test_create_with_staff_id_sets_latest(self):
        """staff_id 付きで作成すると is_latest_for_staff が自動更新される。"""
        p = _make_period()
        s = _make_staff()
        sub = _make_submission(p["id"], s["id"])
        assert submission_repo.get_by_id(sub["id"])["is_latest_for_staff"] == 1

    def test_duplicate_key_raises(self):
        import sqlite3
        p = _make_period()
        _make_submission(p["id"], key="dup")
        with pytest.raises(sqlite3.IntegrityError):
            _make_submission(p["id"], key="dup")

    def test_exists_by_key(self):
        p = _make_period()
        _make_submission(p["id"], key="abc")
        assert submission_repo.exists_by_key("abc")
        assert not submission_repo.exists_by_key("xyz")

    def test_update_apply_status(self):
        p = _make_period()
        sub = _make_submission(p["id"])
        updated = submission_repo.update_apply_status(sub["id"], "applied")
        assert updated["apply_status"] == "applied"

    def test_update_staff_id_recalculates_latest(self):
        """手動紐付け後に is_latest_for_staff が再計算される。"""
        p = _make_period()
        s = _make_staff()
        sub = _make_submission(p["id"], staff_id=None)
        assert submission_repo.get_by_id(sub["id"])["is_latest_for_staff"] == 0
        updated = submission_repo.update_staff_id(sub["id"], s["id"])
        assert updated["staff_id"] == s["id"]
        assert submission_repo.get_by_id(sub["id"])["is_latest_for_staff"] == 1

    def test_update_staff_id_recalculates_old_staff(self):
        """別スタッフへ付け替え時、旧スタッフの最新フラグも再計算される。"""
        p = _make_period()
        s1 = _make_staff("スタッフA")
        s2 = _make_staff("スタッフB")
        sub = submission_repo.create(
            p["id"], s1["id"], "スタッフA", "ka", "2026-10-01 10:00:00", None, None, None
        )
        # s1 に紐付いた状態で s2 へ付け替え
        submission_repo.update_staff_id(sub["id"], s2["id"])
        # s1 側は最新フラグなし
        rows_s1 = [r for r in submission_repo.get_by_period(p["id"]) if r["staff_id"] == s1["id"]]
        assert all(r["is_latest_for_staff"] == 0 for r in rows_s1)
        # s2 側は最新フラグあり
        assert submission_repo.get_by_id(sub["id"])["is_latest_for_staff"] == 1

    def test_is_latest_for_staff_multiple_submissions(self):
        """複数回答がある場合、submitted_at 最新の1件のみ is_latest=1。"""
        p = _make_period()
        s = _make_staff()
        sub1 = submission_repo.create(
            p["id"], s["id"], "田中", "k1", "2026-10-01 10:00:00", None, None, None
        )
        sub2 = submission_repo.create(
            p["id"], s["id"], "田中", "k2", "2026-10-05 10:00:00", None, None, None
        )
        assert submission_repo.get_by_id(sub2["id"])["is_latest_for_staff"] == 1
        assert submission_repo.get_by_id(sub1["id"])["is_latest_for_staff"] == 0

    def test_get_by_period_sort_order(self):
        p = _make_period()
        s = _make_staff()
        sub_applied = submission_repo.create(
            p["id"], s["id"], "田中", "k_applied", "2026-10-01 10:00:00", None, None, None
        )
        submission_repo.update_apply_status(sub_applied["id"], "applied")
        _make_submission(p["id"], s["id"], key="k_pending")
        rows = submission_repo.get_by_period(p["id"])
        statuses = [r["apply_status"] for r in rows]
        assert statuses.index("pending") < statuses.index("applied")

    def test_upsert_day_entries(self):
        p = _make_period()
        sub = _make_submission(p["id"])
        entries = [
            {"work_date": "2026-10-21", "start_time": 9.0, "end_time": 17.0},
            {"work_date": "2026-10-22", "start_time": None, "end_time": None},
        ]
        submission_repo.upsert_day_entries(sub["id"], entries)
        days = submission_repo.get_day_entries(sub["id"])
        assert len(days) == 2
        assert days[0]["start_time"] == 9.0
        assert days[1]["start_time"] is None


# ── wish_shift_repo ───────────────────────────────────────────────────────────

class TestWishShiftRepo:
    def test_upsert_bulk_and_get(self):
        p = _make_period()
        s = _make_staff()
        sub = _make_submission(p["id"], s["id"])
        shifts = [
            {"work_date": "2026-10-21", "start_time": 9.0, "end_time": 17.0, "submission_id": sub["id"]},
            {"work_date": "2026-10-22", "start_time": 10.0, "end_time": 18.0, "submission_id": sub["id"]},
        ]
        wish_shift_repo.rebuild_bulk(p["id"], s["id"], shifts)
        result = wish_shift_repo.get_by_period_and_staff(p["id"], s["id"])
        assert len(result) == 2

    def test_upsert_bulk_replaces_existing(self):
        p = _make_period()
        s = _make_staff()
        sub = _make_submission(p["id"], s["id"])
        wish_shift_repo.rebuild_bulk(
            p["id"], s["id"],
            [{"work_date": "2026-10-21", "start_time": 9.0, "end_time": 17.0, "submission_id": sub["id"]}],
        )
        wish_shift_repo.rebuild_bulk(p["id"], s["id"], [])
        assert wish_shift_repo.get_by_period_and_staff(p["id"], s["id"]) == []

    def test_delete_by_period_and_staff(self):
        p = _make_period()
        s = _make_staff()
        sub = _make_submission(p["id"], s["id"])
        wish_shift_repo.rebuild_bulk(
            p["id"], s["id"],
            [{"work_date": "2026-10-21", "start_time": 9.0, "end_time": 17.0, "submission_id": sub["id"]}],
        )
        wish_shift_repo.delete_by_period_and_staff(p["id"], s["id"])
        assert wish_shift_repo.get_by_period_and_staff(p["id"], s["id"]) == []


# ── edited_shift_repo ─────────────────────────────────────────────────────────

class TestEditedShiftRepo:
    def test_upsert_and_get(self):
        p = _make_period()
        s = _make_staff()
        edited_shift_repo.upsert(p["id"], s["id"], "2026-10-21", 9.0, 17.0)
        row = edited_shift_repo.get_one(p["id"], s["id"], "2026-10-21")
        assert row["start_time"] == 9.0

    def test_upsert_overwrites(self):
        p = _make_period()
        s = _make_staff()
        edited_shift_repo.upsert(p["id"], s["id"], "2026-10-21", 9.0, 17.0)
        edited_shift_repo.upsert(p["id"], s["id"], "2026-10-21", 10.0, 18.0)
        row = edited_shift_repo.get_one(p["id"], s["id"], "2026-10-21")
        assert row["start_time"] == 10.0

    def test_clear_sets_null(self):
        p = _make_period()
        s = _make_staff()
        edited_shift_repo.upsert(p["id"], s["id"], "2026-10-21", 9.0, 17.0)
        edited_shift_repo.clear(p["id"], s["id"], "2026-10-21")
        row = edited_shift_repo.get_one(p["id"], s["id"], "2026-10-21")
        assert row["start_time"] is None
        assert row["end_time"] is None

    def test_upsert_bulk(self):
        p = _make_period()
        s = _make_staff()
        shifts = [
            {"work_date": "2026-10-21", "start_time": 9.0, "end_time": 17.0},
            {"work_date": "2026-10-22", "start_time": 10.0, "end_time": 18.0},
        ]
        edited_shift_repo.upsert_bulk(p["id"], s["id"], shifts)
        assert len(edited_shift_repo.get_by_period_and_staff(p["id"], s["id"])) == 2


# ── memo_repo / mark_repo ─────────────────────────────────────────────────────

class TestMemoRepo:
    def test_upsert_and_get(self):
        p = _make_period()
        s = _make_staff()
        memo_repo.upsert(p["id"], s["id"], "2026-10-21", "テストメモ")
        row = memo_repo.get_one(p["id"], s["id"], "2026-10-21")
        assert row["memo_text"] == "テストメモ"

    def test_upsert_overwrites(self):
        p = _make_period()
        s = _make_staff()
        memo_repo.upsert(p["id"], s["id"], "2026-10-21", "初回")
        memo_repo.upsert(p["id"], s["id"], "2026-10-21", "更新後")
        assert memo_repo.get_one(p["id"], s["id"], "2026-10-21")["memo_text"] == "更新後"


class TestMarkRepo:
    def test_upsert_and_get(self):
        p = _make_period()
        s = _make_staff()
        mark_repo.upsert(p["id"], s["id"], "2026-10-21", "red")
        row = mark_repo.get_one(p["id"], s["id"], "2026-10-21")
        assert row["mark_color"] == "red"

    def test_upsert_overwrites_color(self):
        p = _make_period()
        s = _make_staff()
        mark_repo.upsert(p["id"], s["id"], "2026-10-21", "red")
        mark_repo.upsert(p["id"], s["id"], "2026-10-21", "yellow")
        assert mark_repo.get_one(p["id"], s["id"], "2026-10-21")["mark_color"] == "yellow"

    def test_delete(self):
        p = _make_period()
        s = _make_staff()
        mark_repo.upsert(p["id"], s["id"], "2026-10-21", "red")
        mark_repo.delete(p["id"], s["id"], "2026-10-21")
        assert mark_repo.get_one(p["id"], s["id"], "2026-10-21") is None


# ── custom_day_repo ───────────────────────────────────────────────────────────

class TestCustomDayRepo:
    def test_upsert_global_and_get(self):
        custom_day_repo.upsert(0, "2026-10-21", is_custom_holiday=True, wage_bonus=200.0)
        rules = custom_day_repo.get_global()
        assert len(rules) == 1
        assert rules[0]["is_custom_holiday"] == 1
        assert rules[0]["wage_bonus"] == 200.0

    def test_upsert_full_overwrite(self):
        custom_day_repo.upsert(0, "2026-10-21", is_custom_holiday=True)
        custom_day_repo.upsert(0, "2026-10-21", is_custom_holiday=False, exclude_auto_holiday=True)
        row = custom_day_repo.get_one(0, "2026-10-21")
        assert row["is_custom_holiday"] == 0
        assert row["exclude_auto_holiday"] == 1

    def test_upsert_partial_preserves_existing(self):
        """未指定フィールドは既存値を保持する（部分更新）。"""
        custom_day_repo.upsert(0, "2026-10-21", is_custom_holiday=True, note_text="メモ")
        # wage_bonus だけ更新 → is_custom_holiday と note_text は保持されること
        custom_day_repo.upsert(0, "2026-10-21", wage_bonus=300.0)
        row = custom_day_repo.get_one(0, "2026-10-21")
        assert row["is_custom_holiday"] == 1
        assert row["note_text"] == "メモ"
        assert row["wage_bonus"] == 300.0

    def test_delete(self):
        custom_day_repo.upsert(0, "2026-10-21", is_custom_holiday=True)
        custom_day_repo.delete(0, "2026-10-21")
        assert custom_day_repo.get_one(0, "2026-10-21") is None

    def test_period_rule_separate_from_global(self):
        p = _make_period()
        custom_day_repo.upsert(0, "2026-10-21", is_custom_holiday=True)
        custom_day_repo.upsert(p["id"], "2026-10-21", wage_bonus=500.0)
        global_rule = custom_day_repo.get_one(0, "2026-10-21")
        period_rule = custom_day_repo.get_one(p["id"], "2026-10-21")
        assert global_rule["is_custom_holiday"] == 1
        assert period_rule["wage_bonus"] == 500.0


# ── print_settings_repo ───────────────────────────────────────────────────────

class TestPrintSettingsRepo:
    def test_upsert_and_get(self):
        p = _make_period()
        print_settings_repo.upsert(p["id"], "2026-10-21", "2026-11-20")
        row = print_settings_repo.get_by_period(p["id"])
        assert row["print_from_date"] == "2026-10-21"
        assert row["print_to_date"] == "2026-11-20"

    def test_upsert_overwrites(self):
        p = _make_period()
        print_settings_repo.upsert(p["id"], "2026-10-21", "2026-11-20")
        print_settings_repo.upsert(p["id"], "2026-10-25", "2026-11-15")
        row = print_settings_repo.get_by_period(p["id"])
        assert row["print_from_date"] == "2026-10-25"

    def test_not_found_returns_none(self):
        p = _make_period()
        assert print_settings_repo.get_by_period(p["id"]) is None
