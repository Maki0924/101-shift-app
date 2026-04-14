"""スタッフ（staff）リポジトリ"""

import sqlite3
from datetime import datetime

from src.db.connection import get_connection, transaction

# 表示順: sort_order ASC → is_active DESC → employment_type (part_time前) → name ASC → id ASC
_ORDER_BY = """
    ORDER BY
        sort_order ASC,
        is_active DESC,
        CASE employment_type WHEN 'part_time' THEN 0 ELSE 1 END ASC,
        name ASC,
        id ASC
"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


# ── 取得 ──────────────────────────────────────────────────────────────────────

def get_all() -> list[dict]:
    """全スタッフを表示順で返す（有効・無効含む）。"""
    rows = get_connection().execute(f"SELECT * FROM staff {_ORDER_BY}").fetchall()
    return [_row_to_dict(r) for r in rows]


def get_active() -> list[dict]:
    """有効スタッフのみを表示順で返す。"""
    rows = get_connection().execute(
        f"SELECT * FROM staff WHERE is_active = 1 {_ORDER_BY}"
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_all_part_time_active() -> list[dict]:
    """有効なバイトスタッフのみを表示順で返す（進捗サマリーの未提出人数算出用）。"""
    rows = get_connection().execute(
        f"SELECT * FROM staff WHERE is_active = 1 AND employment_type = 'part_time' {_ORDER_BY}"
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_by_id(staff_id: int) -> dict | None:
    row = get_connection().execute(
        "SELECT * FROM staff WHERE id = ?", (staff_id,)
    ).fetchone()
    return _row_to_dict(row) if row else None


def get_by_name(name: str) -> dict | None:
    row = get_connection().execute(
        "SELECT * FROM staff WHERE name = ?", (name,)
    ).fetchone()
    return _row_to_dict(row) if row else None


def get_for_period(period_id: int) -> list[dict]:
    """指定期間のシフト表に表示するスタッフを返す。

    - 有効スタッフは常に含む
    - 無効スタッフは wish_shifts または edited_shifts にデータがある場合のみ含む
    """
    rows = get_connection().execute(
        f"""
        SELECT DISTINCT s.*
        FROM staff s
        WHERE s.is_active = 1
           OR EXISTS (
               SELECT 1 FROM wish_shifts w
               WHERE w.staff_id = s.id AND w.period_id = ?
           )
           OR EXISTS (
               SELECT 1 FROM edited_shifts e
               WHERE e.staff_id = s.id AND e.period_id = ?
           )
        {_ORDER_BY}
        """,
        (period_id, period_id),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


# ── 作成・更新 ─────────────────────────────────────────────────────────────────

def create(
    name: str,
    employment_type: str,
    hourly_wage: float,
    sort_order: int = 0,
) -> dict:
    """スタッフを新規作成し、作成したレコードを返す。"""
    now = _now()
    with transaction() as txn:
        cursor = txn.execute(
            """
            INSERT INTO staff (name, employment_type, hourly_wage, is_active, sort_order,
                               created_at, updated_at)
            VALUES (?, ?, ?, 1, ?, ?, ?)
            """,
            (name, employment_type, hourly_wage, sort_order, now, now),
        )
    return get_by_id(cursor.lastrowid)


def update(
    staff_id: int,
    name: str,
    employment_type: str,
    hourly_wage: float,
    sort_order: int,
) -> dict | None:
    """スタッフ情報を更新し、更新後のレコードを返す。"""
    now = _now()
    with transaction() as txn:
        txn.execute(
            """
            UPDATE staff
            SET name = ?, employment_type = ?, hourly_wage = ?,
                sort_order = ?, updated_at = ?
            WHERE id = ?
            """,
            (name, employment_type, hourly_wage, sort_order, now, staff_id),
        )
    return get_by_id(staff_id)


def set_active(staff_id: int, is_active: bool) -> dict | None:
    """有効フラグを更新し、更新後のレコードを返す。"""
    now = _now()
    with transaction() as txn:
        txn.execute(
            "UPDATE staff SET is_active = ?, updated_at = ? WHERE id = ?",
            (1 if is_active else 0, now, staff_id),
        )
    return get_by_id(staff_id)
