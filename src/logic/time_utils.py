"""時刻バリデーション

時刻は REAL 型（例: 9.0, 17.5）。有効範囲: 0.0〜24.0（30分単位）。
"""

from enum import Enum, auto


class TimeError(Enum):
    NONE = auto()
    ONE_SIDE_NULL = auto()   # 片側のみ入力
    START_GTE_END = auto()   # start >= end
    NOT_HALF_HOUR = auto()   # 30分単位でない
    OUT_OF_RANGE = auto()    # 0.0〜24.0 範囲外


def _in_range(value: float) -> bool:
    """時刻値が 0.0〜24.0 の範囲内かどうかを返す。"""
    return 0.0 <= value <= 24.0


def _is_half_hour(value: float) -> bool:
    """時刻値が 30分単位かどうかを返す。"""
    return (value * 2) % 1 == 0


def is_valid_time(value: float) -> bool:
    """時刻値が 0.0〜24.0 かつ 30分単位かどうかを返す。"""
    return _in_range(value) and _is_half_hour(value)


def validate(start: float | None, end: float | None) -> TimeError:
    """開始・終了時刻のペアを検証してエラー種別を返す。

    両方 None は「勤務なし」（クリア状態）として NONE を返す。
    """
    if start is None and end is None:
        return TimeError.NONE  # 勤務なし（正常状態）

    if start is None or end is None:
        return TimeError.ONE_SIDE_NULL

    if not _in_range(start) or not _in_range(end):
        return TimeError.OUT_OF_RANGE

    if not _is_half_hour(start) or not _is_half_hour(end):
        return TimeError.NOT_HALF_HOUR

    if start >= end:
        return TimeError.START_GTE_END

    return TimeError.NONE


def is_error(start: float | None, end: float | None) -> bool:
    """エラー状態（計算除外対象）かどうかを返す。

    両方 None（勤務なし）はエラーではない。
    """
    return validate(start, end) != TimeError.NONE


def work_hours(start: float, end: float) -> float:
    """勤務時間を返す（バリデーション済みの値を渡すこと）。"""
    return end - start
