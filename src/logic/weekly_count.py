"""週回数判定

月曜起算で週を集計し、確定回数と採用済み希望を比較して判定結果を返す。
"""

import datetime
from enum import Enum, auto


class WeeklyJudgment(Enum):
    NO_PREF = auto()   # 希望なし（採用済み回答なし、またはmin/max共にNULL）
    UNDER = auto()     # 未達（確定回数 < min）
    OK = auto()        # 適正（min <= 確定回数 <= max）
    OVER = auto()      # 超過（確定回数 > max）


def _monday_of(date: datetime.date) -> datetime.date:
    """指定日が属する週の月曜日を返す（月曜起算）。"""
    return date - datetime.timedelta(days=date.weekday())


def _weeks_in_period(
    start_date: datetime.date,
    end_date: datetime.date,
    prev_end_date: datetime.date | None,
) -> list[tuple[datetime.date, datetime.date]]:
    """期間内の週リスト（月曜〜日曜）を返す。

    先頭週は前期間末日の翌月曜から現期間 start_date を含む週として扱う。
    前期間がない場合は start_date を含む週の月曜から開始。
    """
    if prev_end_date is not None:
        week_start = _monday_of(prev_end_date + datetime.timedelta(days=1))
    else:
        week_start = _monday_of(start_date)

    weeks = []
    while week_start <= end_date:
        week_end = week_start + datetime.timedelta(days=6)
        weeks.append((week_start, week_end))
        week_start += datetime.timedelta(weeks=1)
    return weeks


def count_confirmed_in_range(
    edited_shifts: list[dict],
    range_start: datetime.date,
    range_end: datetime.date,
) -> int:
    """指定日付範囲内の確定シフト（start/end 両方非NULL）の日数を返す。"""
    count = 0
    for s in edited_shifts:
        if s["start_time"] is None or s["end_time"] is None:
            continue
        work_date = datetime.date.fromisoformat(s["work_date"])
        if range_start <= work_date <= range_end:
            count += 1
    return count


def judge(
    period_start: datetime.date,
    period_end: datetime.date,
    weekly_pref_min: int | None,
    weekly_pref_max: int | None,
    current_edited_shifts: list[dict],
    prev_edited_shifts: list[dict] | None = None,
    prev_period_end: datetime.date | None = None,
) -> list[tuple[tuple[datetime.date, datetime.date], int, WeeklyJudgment]]:
    """週ごとの判定結果を返す。

    Args:
        period_start / period_end: 対象期間の開始・終了日
        weekly_pref_min / weekly_pref_max: 採用済み回答の希望（Noneは希望なし）
        current_edited_shifts: 現期間の edited_shifts レコードリスト
        prev_edited_shifts: 直近前期間の edited_shifts（前期間参照用）
        prev_period_end: 直近前期間の end_date（週範囲計算用）

    Returns:
        [(週範囲(月曜, 日曜), 確定回数, 判定結果), ...]
    """
    all_shifts = list(current_edited_shifts)
    if prev_edited_shifts:
        all_shifts.extend(prev_edited_shifts)

    weeks = _weeks_in_period(period_start, period_end, prev_period_end)
    results = []

    for week_start, week_end in weeks:
        confirmed = count_confirmed_in_range(all_shifts, week_start, week_end)
        judgment = _judge_week(confirmed, weekly_pref_min, weekly_pref_max)
        results.append(((week_start, week_end), confirmed, judgment))

    return results


def judge_total(
    period_start: datetime.date,
    period_end: datetime.date,
    weekly_pref_min: int | None,
    weekly_pref_max: int | None,
    current_edited_shifts: list[dict],
    prev_edited_shifts: list[dict] | None = None,
    prev_period_end: datetime.date | None = None,
) -> WeeklyJudgment:
    """期間全体で最も悪い判定を返す（UI の名前セル色付け用）。

    優先順位: UNDER > OVER > OK > NO_PREF
    """
    weekly = judge(
        period_start, period_end,
        weekly_pref_min, weekly_pref_max,
        current_edited_shifts, prev_edited_shifts, prev_period_end,
    )
    if not weekly:
        return WeeklyJudgment.NO_PREF

    priorities = {
        WeeklyJudgment.UNDER: 0,
        WeeklyJudgment.OVER: 1,
        WeeklyJudgment.OK: 2,
        WeeklyJudgment.NO_PREF: 3,
    }
    return min((j for _, _, j in weekly), key=lambda j: priorities[j])


def _judge_week(
    confirmed: int,
    pref_min: int | None,
    pref_max: int | None,
) -> WeeklyJudgment:
    if pref_min is None and pref_max is None:
        return WeeklyJudgment.NO_PREF
    # UNDER: min が設定されていて未達
    if pref_min is not None and confirmed < pref_min:
        return WeeklyJudgment.UNDER
    # OVER: max が設定されていて超過
    if pref_max is not None and confirmed > pref_max:
        return WeeklyJudgment.OVER
    # (None, max) パターン: min未設定でmaxのみ設定 → max以下なら OK
    return WeeklyJudgment.OK
