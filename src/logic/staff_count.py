"""昼夜人数集計・人数不足判定

重複時間閾値（overlap_hours_threshold）を用いて昼夜をカウントし、
app_settings の最低人数と比較して不足を判定する。
"""

import datetime
from dataclasses import dataclass

from src.logic.holiday import is_weekend_or_holiday
from src.logic.time_utils import is_error


@dataclass
class DayCount:
    """1日分の昼夜人数と不足フラグ。"""
    day_count: int
    night_count: int
    day_short: bool    # 昼人数不足
    night_short: bool  # 夜人数不足


def overlap_hours(
    shift_start: float,
    shift_end: float,
    zone_start: float,
    zone_end: float,
) -> float:
    """勤務時間と時間帯の重複時間を返す。"""
    return max(0.0, min(shift_end, zone_end) - max(shift_start, zone_start))


def count_for_zone(
    shifts: list[dict],
    zone_start: float,
    zone_end: float,
    threshold: float,
) -> int:
    """指定時間帯にカウントされるスタッフ数を返す。

    確定シフト（start/end 両方非NULL・エラーなし）のみ対象。
    """
    count = 0
    for s in shifts:
        start = s.get("start_time")
        end = s.get("end_time")
        if start is None or end is None:
            continue
        if is_error(start, end):
            continue
        if overlap_hours(start, end, zone_start, zone_end) >= threshold:
            count += 1
    return count


def calc_day_count(
    date: datetime.date,
    shifts: list[dict],
    day_shift_start: float,
    day_shift_end: float,
    night_shift_start: float,
    night_shift_end: float,
    overlap_hours_threshold: float,
    weekday_day_min: int,
    weekday_night_min: int,
    weekend_day_min: int,
    weekend_night_min: int,
    rules: list[dict] | None = None,
) -> DayCount:
    """1日分の昼夜人数を集計し、不足判定も行う。

    Args:
        date: 集計対象日
        shifts: 当日の全スタッフの edited_shifts レコード
        rules: custom_day_rules（土日祝判定に使用）
    """
    day_count = count_for_zone(shifts, day_shift_start, day_shift_end, overlap_hours_threshold)
    night_count = count_for_zone(shifts, night_shift_start, night_shift_end, overlap_hours_threshold)

    is_weh = is_weekend_or_holiday(date, rules)
    day_min = weekend_day_min if is_weh else weekday_day_min
    night_min = weekend_night_min if is_weh else weekday_night_min

    day_short = (day_min > 0) and (day_count < day_min)
    night_short = (night_min > 0) and (night_count < night_min)

    return DayCount(
        day_count=day_count,
        night_count=night_count,
        day_short=day_short,
        night_short=night_short,
    )
