"""アプリ設定（app_settings）リポジトリ

app_settings は常に id=1 の1行のみ存在する。
"""

import sqlite3
from datetime import datetime

from src.db.connection import get_connection, transaction


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def get() -> dict | None:
    """app_settings（id=1）を取得する。"""
    row = get_connection().execute(
        "SELECT * FROM app_settings WHERE id = 1"
    ).fetchone()
    return _row_to_dict(row) if row else None


def update(
    day_shift_start: float,
    day_shift_end: float,
    night_shift_start: float,
    night_shift_end: float,
    overlap_hours_threshold: float,
    saturday_bonus: float,
    sunday_bonus: float,
    holiday_bonus: float,
    weekday_day_min_staff: int,
    weekday_night_min_staff: int,
    weekend_day_min_staff: int,
    weekend_night_min_staff: int,
    print_font_size: int,
) -> dict | None:
    """app_settings（id=1）を更新し、更新後のレコードを返す。"""
    now = _now()
    with transaction() as txn:
        txn.execute(
            """
            UPDATE app_settings SET
                day_shift_start = ?,
                day_shift_end = ?,
                night_shift_start = ?,
                night_shift_end = ?,
                overlap_hours_threshold = ?,
                saturday_bonus = ?,
                sunday_bonus = ?,
                holiday_bonus = ?,
                weekday_day_min_staff = ?,
                weekday_night_min_staff = ?,
                weekend_day_min_staff = ?,
                weekend_night_min_staff = ?,
                print_font_size = ?,
                updated_at = ?
            WHERE id = 1
            """,
            (
                day_shift_start, day_shift_end,
                night_shift_start, night_shift_end,
                overlap_hours_threshold,
                saturday_bonus, sunday_bonus, holiday_bonus,
                weekday_day_min_staff, weekday_night_min_staff,
                weekend_day_min_staff, weekend_night_min_staff,
                print_font_size,
                now,
            ),
        )
    return get()
