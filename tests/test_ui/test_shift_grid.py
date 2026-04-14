"""ShiftGrid のユニットテスト（コミット19）

Canvas を使った描画ロジックを直接テストするのは難しいため、
純粋関数（make_date_list / date_bg / cell_text）と
ShiftGrid の公開プロパティ/メソッドを検証する。
"""

import datetime

from src.ui.components.shift_grid import cell_text, date_bg, make_date_list

# ── make_date_list ────────────────────────────────────────────────────────────


class TestMakeDateList:
    def test_single_day(self):
        assert make_date_list("2025-04-01", "2025-04-01") == ["2025-04-01"]

    def test_one_month(self):
        dates = make_date_list("2025-04-01", "2025-04-30")
        assert len(dates) == 30
        assert dates[0] == "2025-04-01"
        assert dates[-1] == "2025-04-30"

    def test_year_boundary(self):
        dates = make_date_list("2024-12-30", "2025-01-02")
        assert dates == ["2024-12-30", "2024-12-31", "2025-01-01", "2025-01-02"]

    def test_empty_on_invalid_range(self):
        # end < start → 空リスト
        assert make_date_list("2025-04-05", "2025-04-01") == []


# ── date_bg ───────────────────────────────────────────────────────────────────


class TestDateBg:
    def test_weekday_white(self):
        # 2025-04-07 は月曜
        monday = datetime.date(2025, 4, 7)
        assert date_bg(monday, None) == "#ffffff"

    def test_saturday_blue(self):
        # 2025-04-05 は土曜
        saturday = datetime.date(2025, 4, 5)
        assert date_bg(saturday, None) == "#dbeafe"

    def test_sunday_pink(self):
        # 2025-04-06 は日曜
        sunday = datetime.date(2025, 4, 6)
        assert date_bg(sunday, None) == "#fce7f3"

    def test_holiday_pink(self):
        # 2025-01-01 は元日（祝日）
        new_year = datetime.date(2025, 1, 1)
        assert date_bg(new_year, None) == "#fce7f3"

    def test_custom_holiday_overrides_weekday(self):
        # カスタム休日ルールで平日を祝日扱い
        rule = {
            "period_id": 0,
            "rule_date": "2025-04-07",
            "is_custom_holiday": True,
            "exclude_auto_holiday": False,
        }
        monday = datetime.date(2025, 4, 7)
        assert date_bg(monday, [rule]) == "#fce7f3"


# ── cell_text ─────────────────────────────────────────────────────────────────


class TestCellText:
    def test_none_shift_empty(self):
        assert cell_text(None) == ""

    def test_no_shift_dash(self):
        assert cell_text({"start_time": None, "end_time": None}) == "—"

    def test_error_one_side_null(self):
        assert cell_text({"start_time": 9.0, "end_time": None}) == "?"
        assert cell_text({"start_time": None, "end_time": 17.0}) == "?"

    def test_normal_shift_on_hour(self):
        # 9:00-17:00
        assert cell_text({"start_time": 9.0, "end_time": 17.0}) == "9-17"

    def test_normal_shift_with_minutes(self):
        # 9:30-18:00
        assert cell_text({"start_time": 9.5, "end_time": 18.0}) == "9:30-18"

    def test_midnight(self):
        # 22:00-24:00
        assert cell_text({"start_time": 22.0, "end_time": 24.0}) == "22-24"
