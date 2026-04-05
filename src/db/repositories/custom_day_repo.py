"""日付別特別ルール（custom_day_rules）リポジトリ

period_id = 0 はグローバルルール（全期間共通）。
"""

import sqlite3
from datetime import datetime

from src.db.connection import get_connection, transaction

_GLOBAL_PERIOD_ID = 0
_UNSET = object()  # 「未指定（既存値を保持）」を表すセンチネル


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def get_by_period(period_id: int) -> list[dict]:
    """指定期間のルールを返す（period_id=0 でグローバルルールを取得）。"""
    rows = get_connection().execute(
        "SELECT * FROM custom_day_rules WHERE period_id = ? ORDER BY rule_date ASC",
        (period_id,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_global() -> list[dict]:
    """グローバルルール（period_id=0）を返す。"""
    return get_by_period(_GLOBAL_PERIOD_ID)


def get_one(period_id: int, rule_date: str) -> dict | None:
    row = get_connection().execute(
        "SELECT * FROM custom_day_rules WHERE period_id = ? AND rule_date = ?",
        (period_id, rule_date),
    ).fetchone()
    return _row_to_dict(row) if row else None


def upsert(
    period_id: int,
    rule_date: str,
    is_custom_holiday: bool | object = _UNSET,
    exclude_auto_holiday: bool | object = _UNSET,
    wage_bonus: float | None | object = _UNSET,
    note_text: str | None | object = _UNSET,
) -> dict | None:
    """ルールを UPSERT し、更新後のレコードを返す。

    _UNSET（デフォルト）のフィールドは既存レコードの値を保持する。
    新規作成時は _UNSET フィールドにデフォルト値（False / None）を使用する。
    """
    existing = get_one(period_id, rule_date)

    final_is_custom_holiday = (
        is_custom_holiday if is_custom_holiday is not _UNSET
        else (bool(existing["is_custom_holiday"]) if existing else False)
    )
    final_exclude_auto_holiday = (
        exclude_auto_holiday if exclude_auto_holiday is not _UNSET
        else (bool(existing["exclude_auto_holiday"]) if existing else False)
    )
    final_wage_bonus = (
        wage_bonus if wage_bonus is not _UNSET
        else (existing["wage_bonus"] if existing else None)
    )
    final_note_text = (
        note_text if note_text is not _UNSET
        else (existing["note_text"] if existing else None)
    )

    now = _now()
    with transaction() as txn:
        txn.execute(
            """
            INSERT INTO custom_day_rules
                (period_id, rule_date, is_custom_holiday, exclude_auto_holiday,
                 wage_bonus, note_text, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(period_id, rule_date) DO UPDATE SET
                is_custom_holiday    = excluded.is_custom_holiday,
                exclude_auto_holiday = excluded.exclude_auto_holiday,
                wage_bonus           = excluded.wage_bonus,
                note_text            = excluded.note_text,
                updated_at           = excluded.updated_at
            """,
            (
                period_id, rule_date,
                1 if final_is_custom_holiday else 0,
                1 if final_exclude_auto_holiday else 0,
                final_wage_bonus, final_note_text,
                now, now,
            ),
        )
    return get_one(period_id, rule_date)


def delete(period_id: int, rule_date: str) -> None:
    with transaction() as txn:
        txn.execute(
            "DELETE FROM custom_day_rules WHERE period_id = ? AND rule_date = ?",
            (period_id, rule_date),
        )
