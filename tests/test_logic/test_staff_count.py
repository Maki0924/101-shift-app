"""昼夜人数集計・人数不足判定テスト"""

import datetime

import pytest

from src.logic.staff_count import calc_day_count, count_for_zone, overlap_hours

# デフォルト設定値
DAY_START, DAY_END = 8.0, 17.0
NIGHT_START, NIGHT_END = 17.0, 22.0
THRESHOLD = 2.0

WEEKDAY = datetime.date(2026, 10, 21)  # 水曜
SATURDAY = datetime.date(2026, 10, 24)
SUNDAY = datetime.date(2026, 10, 25)
HOLIDAY = datetime.date(2026, 11, 3)  # 文化の日

# デフォルト最低人数
WD_DAY, WD_NIGHT = 2, 2
WE_DAY, WE_NIGHT = 5, 3


def _shift(start: float | None, end: float | None) -> dict:
    return {"start_time": start, "end_time": end}


def _calc(date, shifts, wd_day=WD_DAY, wd_night=WD_NIGHT, we_day=WE_DAY, we_night=WE_NIGHT, rules=None):
    return calc_day_count(
        date,
        shifts,
        DAY_START,
        DAY_END,
        NIGHT_START,
        NIGHT_END,
        THRESHOLD,
        wd_day,
        wd_night,
        we_day,
        we_night,
        rules,
    )


# ── overlap_hours ─────────────────────────────────────────────────────────────


class TestOverlapHours:
    def test_full_overlap(self):
        assert overlap_hours(8.0, 17.0, 8.0, 17.0) == 9.0

    def test_no_overlap(self):
        assert overlap_hours(17.0, 22.0, 8.0, 17.0) == 0.0

    def test_partial_overlap(self):
        # 15:00〜20:00 と 昼帯(8〜17) → 重複2時間
        assert overlap_hours(15.0, 20.0, 8.0, 17.0) == 2.0

    def test_boundary_touch(self):
        # shift_end == zone_start → 重複0
        assert overlap_hours(6.0, 8.0, 8.0, 17.0) == 0.0

    def test_shift_contains_zone(self):
        # シフトが時間帯を完全包含
        assert overlap_hours(6.0, 23.0, 8.0, 17.0) == 9.0


# ── count_for_zone ────────────────────────────────────────────────────────────


class TestCountForZone:
    def test_counts_above_threshold(self):
        shifts = [
            _shift(9.0, 17.0),  # 昼重複9h ≥ 2h → カウント
            _shift(15.0, 22.0),  # 昼重複2h = 2h → カウント（境界）
            _shift(16.0, 22.0),  # 昼重複1h < 2h → カウントしない
        ]
        assert count_for_zone(shifts, DAY_START, DAY_END, THRESHOLD) == 2

    def test_threshold_boundary_exact(self):
        """重複時間 == threshold はカウント対象。"""
        shifts = [_shift(15.0, 22.0)]  # 昼重複ちょうど2h
        assert count_for_zone(shifts, DAY_START, DAY_END, THRESHOLD) == 1

    def test_threshold_boundary_just_under(self):
        """重複時間 < threshold はカウント対象外。"""
        shifts = [_shift(15.5, 22.0)]  # 昼重複1.5h
        assert count_for_zone(shifts, DAY_START, DAY_END, THRESHOLD) == 0

    def test_null_shift_excluded(self):
        """勤務なし（NULL/NULL）は除外。"""
        shifts = [_shift(None, None), _shift(9.0, 17.0)]
        assert count_for_zone(shifts, DAY_START, DAY_END, THRESHOLD) == 1

    def test_error_shift_excluded(self):
        """エラー状態（片側NULL・start>=end）は除外。"""
        shifts = [
            _shift(9.0, None),  # 片側NULL
            _shift(17.0, 9.0),  # start > end
            _shift(9.0, 17.0),  # 正常
        ]
        assert count_for_zone(shifts, DAY_START, DAY_END, THRESHOLD) == 1

    def test_night_zone(self):
        shifts = [
            _shift(17.0, 22.0),  # 夜重複5h → カウント
            _shift(9.0, 17.0),  # 夜重複0h → カウントしない
        ]
        assert count_for_zone(shifts, NIGHT_START, NIGHT_END, THRESHOLD) == 1


# ── calc_day_count ────────────────────────────────────────────────────────────


class TestCalcDayCount:
    def test_weekday_sufficient(self):
        shifts = [_shift(9.0, 17.0), _shift(9.0, 17.0)]  # 昼2人
        result = _calc(WEEKDAY, shifts)
        assert result.day_count == 2
        assert not result.day_short

    def test_weekday_day_short(self):
        shifts = [_shift(9.0, 17.0)]  # 昼1人（最低2人）
        result = _calc(WEEKDAY, shifts)
        assert result.day_short

    def test_weekday_night_short(self):
        shifts = [_shift(17.0, 22.0)]  # 夜1人（最低2人）
        result = _calc(WEEKDAY, shifts)
        assert result.night_short

    def test_weekend_uses_weekend_min(self):
        """土曜は weekend_min を使用。"""
        shifts = [_shift(9.0, 17.0), _shift(9.0, 17.0)]  # 昼2人
        result = _calc(SATURDAY, shifts)  # weekend_day_min=5
        assert result.day_short  # 2 < 5

    def test_sunday_uses_weekend_min(self):
        shifts = [_shift(9.0, 17.0)] * 5  # 昼5人
        result = _calc(SUNDAY, shifts)  # weekend_day_min=5
        assert not result.day_short  # 5 >= 5

    def test_holiday_uses_weekend_min(self):
        shifts = [_shift(9.0, 17.0)] * 3  # 昼3人
        result = _calc(HOLIDAY, shifts)  # weekend_day_min=5
        assert result.day_short  # 3 < 5

    def test_min_zero_no_short(self):
        """最低人数が0の区分は不足判定しない。"""
        result = _calc(WEEKDAY, [], wd_day=0, wd_night=0)
        assert not result.day_short
        assert not result.night_short

    def test_custom_holiday_rule(self):
        """custom_day_rules で独自休日 → 週末判定を使用。"""
        rules = [
            {
                "period_id": 0,
                "rule_date": "2026-10-21",
                "is_custom_holiday": 1,
                "exclude_auto_holiday": 0,
                "wage_bonus": None,
            }
        ]
        shifts = [_shift(9.0, 17.0), _shift(9.0, 17.0)]  # 昼2人
        result = _calc(WEEKDAY, shifts, rules=rules)
        # 独自休日 → weekend_day_min=5 → 不足
        assert result.day_short

    @pytest.mark.parametrize(
        "threshold,expected_count",
        [
            (1.5, 2),  # threshold=1.5h → 重複2h・1.5hともカウント
            (2.0, 2),  # threshold=2.0h → 重複2h・2hともカウント（境界）
            (2.5, 1),  # threshold=2.5h → 重複2hはカウントしない
        ],
    )
    def test_threshold_variants(self, threshold, expected_count):
        """overlap_hours_threshold の境界値。"""
        shifts = [
            _shift(9.0, 17.0),  # 昼重複9h
            _shift(15.0, 22.0),  # 昼重複2h
        ]
        result = calc_day_count(
            WEEKDAY,
            shifts,
            DAY_START,
            DAY_END,
            NIGHT_START,
            NIGHT_END,
            threshold,
            WD_DAY,
            WD_NIGHT,
            WE_DAY,
            WE_NIGHT,
        )
        assert result.day_count == expected_count
