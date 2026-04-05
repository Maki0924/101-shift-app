"""時刻バリデーション・休憩・人件費・時給優先順位テスト"""

import datetime

import pytest

from src.logic.holiday import get_wage_bonus, is_holiday, is_weekend_or_holiday
from src.logic.time_utils import TimeError, is_error, validate
from src.logic.wage_calc import break_hours, calc_wage

# 定数（テスト用の基準設定値）
SAT_BONUS = 100.0
SUN_BONUS = 150.0
HOL_BONUS = 200.0

# テスト用日付
WEEKDAY = datetime.date(2026, 10, 21)       # 水曜日
SATURDAY = datetime.date(2026, 10, 24)      # 土曜
SUNDAY = datetime.date(2026, 10, 25)        # 日曜
HOLIDAY = datetime.date(2026, 11, 3)        # 文化の日（祝日）
HOLIDAY_ON_SUNDAY = datetime.date(2026, 5, 3)    # 憲法記念日（日曜）


# ── time_utils ────────────────────────────────────────────────────────────────

class TestValidate:
    def test_valid_shift(self):
        assert validate(9.0, 17.0) == TimeError.NONE

    def test_both_none_is_valid(self):
        """勤務なし（クリア状態）はエラーではない。"""
        assert validate(None, None) == TimeError.NONE

    def test_one_side_null_start(self):
        assert validate(None, 17.0) == TimeError.ONE_SIDE_NULL

    def test_one_side_null_end(self):
        assert validate(9.0, None) == TimeError.ONE_SIDE_NULL

    def test_start_equals_end(self):
        assert validate(9.0, 9.0) == TimeError.START_GTE_END

    def test_start_greater_than_end(self):
        assert validate(17.0, 9.0) == TimeError.START_GTE_END

    def test_not_half_hour_start(self):
        """範囲内だが30分単位でない → NOT_HALF_HOUR。"""
        assert validate(9.25, 17.0) == TimeError.NOT_HALF_HOUR

    def test_not_half_hour_end(self):
        assert validate(9.0, 17.25) == TimeError.NOT_HALF_HOUR

    def test_out_of_range_negative(self):
        assert validate(-1.0, 17.0) == TimeError.OUT_OF_RANGE

    def test_out_of_range_over_24(self):
        assert validate(9.0, 25.0) == TimeError.OUT_OF_RANGE

    def test_out_of_range_takes_priority_over_not_half_hour(self):
        """範囲外かつ30分単位でない → OUT_OF_RANGE（範囲チェックが先）。"""
        assert validate(9.25, 25.3) == TimeError.OUT_OF_RANGE

    def test_end_24_is_valid(self):
        """終了時刻 24.0 は許可。"""
        assert validate(22.0, 24.0) == TimeError.NONE

    def test_start_24_is_invalid(self):
        """開始時刻 24.0 は start >= end になるため不可。"""
        assert validate(24.0, 24.0) == TimeError.START_GTE_END

    def test_boundary_0(self):
        assert validate(0.0, 8.0) == TimeError.NONE

    @pytest.mark.parametrize("start,end", [
        (9.0, 17.0), (0.0, 24.0), (22.0, 24.0), (0.5, 1.0),
    ])
    def test_valid_patterns(self, start, end):
        assert validate(start, end) == TimeError.NONE


class TestIsError:
    def test_valid_shift_not_error(self):
        assert not is_error(9.0, 17.0)

    def test_both_none_not_error(self):
        assert not is_error(None, None)

    def test_one_side_null_is_error(self):
        assert is_error(9.0, None)

    def test_invalid_range_is_error(self):
        assert is_error(17.0, 9.0)


# ── break_hours ───────────────────────────────────────────────────────────────

class TestBreakHours:
    @pytest.mark.parametrize("work_h,expected", [
        (4.0, 0.0),
        (6.0, 0.0),   # 境界: 6.0h以下 = 休憩なし
        (6.5, 0.5),   # 境界: 6.5h = 30分
        (6.9, 0.5),   # 7.0h未満 = 30分
        (7.0, 1.0),   # 境界: 7.0h以上 = 1時間
        (8.0, 1.0),
        (8.5, 1.0),
        (12.0, 1.0),  # 長時間でも1時間固定
    ])
    def test_break_patterns(self, work_h, expected):
        assert break_hours(work_h) == expected


# ── holiday / get_wage_bonus ──────────────────────────────────────────────────

class TestHoliday:
    def test_weekday_not_holiday(self):
        assert not is_holiday(WEEKDAY)

    def test_jpholiday_is_holiday(self):
        assert is_holiday(HOLIDAY)

    def test_saturday_not_holiday(self):
        """土曜は is_holiday=False（土曜判定は is_saturday で別途行う）。"""
        assert not is_holiday(SATURDAY)

    def test_weekend_or_holiday_saturday(self):
        assert is_weekend_or_holiday(SATURDAY)

    def test_weekend_or_holiday_sunday(self):
        assert is_weekend_or_holiday(SUNDAY)

    def test_weekend_or_holiday_holiday(self):
        assert is_weekend_or_holiday(HOLIDAY)

    def test_weekend_or_holiday_weekday(self):
        assert not is_weekend_or_holiday(WEEKDAY)

    def test_custom_holiday_rule(self):
        rules = [{"period_id": 0, "rule_date": "2026-10-21",
                  "is_custom_holiday": 1, "exclude_auto_holiday": 0,
                  "wage_bonus": None}]
        assert is_holiday(WEEKDAY, rules)

    def test_exclude_auto_holiday(self):
        """exclude_auto_holiday=1 で jpholiday を無効化する。"""
        rules = [{"period_id": 0, "rule_date": "2026-11-03",
                  "is_custom_holiday": 0, "exclude_auto_holiday": 1,
                  "wage_bonus": None}]
        assert not is_holiday(HOLIDAY, rules)

    def test_exclude_auto_holiday_does_not_affect_sunday(self):
        """exclude_auto_holiday=1 は日曜判定に影響しない。"""
        rules = [{"period_id": 0, "rule_date": "2026-05-03",
                  "is_custom_holiday": 0, "exclude_auto_holiday": 1,
                  "wage_bonus": None}]
        assert is_weekend_or_holiday(HOLIDAY_ON_SUNDAY, rules)

    def test_period_rule_takes_priority_over_global(self):
        """期間別ルールがグローバルルールより優先される。"""
        rules = [
            {"period_id": 0,  "rule_date": "2026-10-21",
             "is_custom_holiday": 1, "exclude_auto_holiday": 0, "wage_bonus": None},
            {"period_id": 99, "rule_date": "2026-10-21",
             "is_custom_holiday": 0, "exclude_auto_holiday": 0, "wage_bonus": None},
        ]
        # 期間別ルール（period_id=99）が is_custom_holiday=0 → 祝日でない
        assert not is_holiday(WEEKDAY, rules)


class TestGetWageBonus:
    def test_weekday_no_bonus(self):
        assert get_wage_bonus(WEEKDAY, SAT_BONUS, SUN_BONUS, HOL_BONUS) == 0.0

    def test_saturday_bonus(self):
        assert get_wage_bonus(SATURDAY, SAT_BONUS, SUN_BONUS, HOL_BONUS) == SAT_BONUS

    def test_sunday_bonus(self):
        assert get_wage_bonus(SUNDAY, SAT_BONUS, SUN_BONUS, HOL_BONUS) == SUN_BONUS

    def test_holiday_bonus(self):
        assert get_wage_bonus(HOLIDAY, SAT_BONUS, SUN_BONUS, HOL_BONUS) == HOL_BONUS

    def test_holiday_on_sunday_uses_holiday_bonus(self):
        """日曜かつ祝日 → 祝日加算（jpholiday優先）。"""
        bonus = get_wage_bonus(HOLIDAY_ON_SUNDAY, SAT_BONUS, SUN_BONUS, HOL_BONUS)
        assert bonus == HOL_BONUS

    def test_wage_bonus_in_rule_takes_top_priority(self):
        """custom_day_rules.wage_bonus が最優先。"""
        rules = [{"period_id": 0, "rule_date": "2026-10-21",
                  "is_custom_holiday": 0, "exclude_auto_holiday": 0,
                  "wage_bonus": 500.0}]
        assert get_wage_bonus(WEEKDAY, SAT_BONUS, SUN_BONUS, HOL_BONUS, rules) == 500.0

    def test_custom_holiday_without_wage_bonus_uses_holiday_bonus(self):
        """is_custom_holiday=1 かつ wage_bonus=NULL → holiday_bonus を適用。"""
        rules = [{"period_id": 0, "rule_date": "2026-10-21",
                  "is_custom_holiday": 1, "exclude_auto_holiday": 0,
                  "wage_bonus": None}]
        assert get_wage_bonus(WEEKDAY, SAT_BONUS, SUN_BONUS, HOL_BONUS, rules) == HOL_BONUS

    def test_exclude_auto_holiday_on_holiday_falls_through_to_weekday(self):
        """exclude_auto_holiday=1 で祝日無効化 → 平日扱い（土日でなければ0）。"""
        rules = [{"period_id": 0, "rule_date": "2026-11-03",
                  "is_custom_holiday": 0, "exclude_auto_holiday": 1,
                  "wage_bonus": None}]
        assert get_wage_bonus(HOLIDAY, SAT_BONUS, SUN_BONUS, HOL_BONUS, rules) == 0.0

    def test_wage_bonus_zero_applies_zero(self):
        """wage_bonus=0.0 は加算なしの明示設定として 0 を返す。"""
        rules = [{"period_id": 0, "rule_date": "2026-11-03",
                  "is_custom_holiday": 0, "exclude_auto_holiday": 0,
                  "wage_bonus": 0.0}]
        assert get_wage_bonus(HOLIDAY, SAT_BONUS, SUN_BONUS, HOL_BONUS, rules) == 0.0


# ── calc_wage ─────────────────────────────────────────────────────────────────

class TestCalcWage:
    def test_weekday_no_break(self):
        """平日・6時間以内・休憩なし。"""
        # 9:00〜15:00 = 6h, 休憩0h, 実働6h, 時給1000円
        result = calc_wage(9.0, 15.0, 1000, WEEKDAY, SAT_BONUS, SUN_BONUS, HOL_BONUS)
        assert result == 6000

    def test_weekday_with_30min_break(self):
        """平日・6.5時間・休憩30分。"""
        # 9:00〜15:30 = 6.5h, 休憩0.5h, 実働6h, 時給1000円
        result = calc_wage(9.0, 15.5, 1000, WEEKDAY, SAT_BONUS, SUN_BONUS, HOL_BONUS)
        assert result == 6000

    def test_weekday_with_1h_break(self):
        """平日・7時間以上・休憩1時間。"""
        # 9:00〜17:00 = 8h, 休憩1h, 実働7h, 時給1000円
        result = calc_wage(9.0, 17.0, 1000, WEEKDAY, SAT_BONUS, SUN_BONUS, HOL_BONUS)
        assert result == 7000

    def test_saturday_bonus_applied(self):
        # 9:00〜17:00 = 8h, 休憩1h, 実働7h, 時給1000+100=1100円
        result = calc_wage(9.0, 17.0, 1000, SATURDAY, SAT_BONUS, SUN_BONUS, HOL_BONUS)
        assert result == 7700

    def test_floor_truncation(self):
        """端数切り捨て確認。"""
        # 9:00〜15:30 = 6.5h, 休憩0.5h, 実働6h, 時給1234円 → 7404円
        result = calc_wage(9.0, 15.5, 1234, WEEKDAY, SAT_BONUS, SUN_BONUS, HOL_BONUS)
        assert result == 7404

    def test_fractional_hours_floor(self):
        """時給が割り切れない場合の切り捨て。"""
        # 9:00〜16:30 = 7.5h, 休憩1h, 実働6.5h, 時給1000円 → 6500円
        result = calc_wage(9.0, 16.5, 1000, WEEKDAY, SAT_BONUS, SUN_BONUS, HOL_BONUS)
        assert result == 6500
