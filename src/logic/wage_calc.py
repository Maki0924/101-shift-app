"""人件費計算

休憩計算・人件費計算・適用時給の優先順位を実装する。
"""

import datetime
import math

from src.logic.holiday import get_wage_bonus
from src.logic.time_utils import TimeError, validate


def break_hours(work_h: float) -> float:
    """勤務時間から休憩時間を返す。

    | 勤務時間  | 休憩   |
    |-----------|--------|
    | 6.0h 以下 | 0h     |
    | 6.5h      | 0.5h   |
    | 7.0h 以上 | 1.0h   |
    """
    if work_h <= 6.0:
        return 0.0
    if work_h < 7.0:
        return 0.5
    return 1.0


def calc_wage(
    start: float,
    end: float,
    hourly_wage: float,
    date: datetime.date,
    saturday_bonus: float,
    sunday_bonus: float,
    holiday_bonus: float,
    rules: list[dict] | None = None,
) -> int:
    """1勤務分の人件費を返す（円未満切り捨て）。

    エラー状態（片側NULL等）は呼び出し前に除外すること。

    Args:
        start: 開始時刻（REAL型）
        end: 終了時刻（REAL型）
        hourly_wage: スタッフの通常時給
        date: 勤務日
        saturday_bonus / sunday_bonus / holiday_bonus: app_settings の加算額
        rules: custom_day_rules のレコードリスト（当該日の全ルール）
    """
    work_h = end - start
    actual_h = work_h - break_hours(work_h)
    bonus = get_wage_bonus(date, saturday_bonus, sunday_bonus, holiday_bonus, rules)
    applied_wage = hourly_wage + bonus
    return math.floor(actual_h * applied_wage)


def is_calculable(start: float | None, end: float | None) -> bool:
    """人件費計算可能なセルかどうかを返す（確定シフトのみ対象）。"""
    if start is None or end is None:
        return False
    return validate(start, end) == TimeError.NONE
