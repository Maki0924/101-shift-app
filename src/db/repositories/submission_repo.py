"""回答（submissions / submission_day_entries）リポジトリ"""

import sqlite3
from datetime import datetime

from src.db.connection import get_connection, transaction


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


# ── submissions ───────────────────────────────────────────────────────────────

def get_by_id(submission_id: int) -> dict | None:
    row = get_connection().execute(
        "SELECT * FROM submissions WHERE id = ?", (submission_id,)
    ).fetchone()
    return _row_to_dict(row) if row else None


def get_by_period(period_id: int) -> list[dict]:
    """期間内の回答をデフォルトソート順で返す。

    ソート: pending → applied → on_hold → rejected、同一ステータス内は submitted_at DESC → id DESC
    """
    rows = get_connection().execute(
        """
        SELECT * FROM submissions
        WHERE period_id = ?
        ORDER BY
            CASE apply_status
                WHEN 'pending'   THEN 0
                WHEN 'applied'   THEN 1
                WHEN 'on_hold'   THEN 2
                WHEN 'rejected'  THEN 3
            END ASC,
            submitted_at DESC,
            id DESC
        """,
        (period_id,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def exists_by_key(external_submission_key: str) -> bool:
    """同一キーの回答が既に存在するか確認する（冪等性チェック）。"""
    return get_connection().execute(
        "SELECT 1 FROM submissions WHERE external_submission_key = ?",
        (external_submission_key,),
    ).fetchone() is not None


def create(
    period_id: int,
    staff_id: int | None,
    raw_staff_name: str,
    external_submission_key: str,
    submitted_at: str,
    note_text: str | None,
    weekly_pref_min: int | None,
    weekly_pref_max: int | None,
) -> dict:
    """回答を新規作成し、作成したレコードを返す。"""
    now = _now()
    with transaction() as txn:
        cursor = txn.execute(
            """
            INSERT INTO submissions (
                period_id, staff_id, raw_staff_name, external_submission_key,
                submitted_at, note_text, weekly_pref_min, weekly_pref_max,
                apply_status, is_latest_for_staff, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?)
            """,
            (
                period_id, staff_id, raw_staff_name, external_submission_key,
                submitted_at, note_text, weekly_pref_min, weekly_pref_max,
                now, now,
            ),
        )
    new_id = cursor.lastrowid
    # staff_id が解決済みの場合は最新フラグを再計算する（未紐付けは常に0のまま）
    if staff_id is not None:
        update_is_latest_for_staff(period_id, staff_id)
    return get_by_id(new_id)


def update_apply_status(submission_id: int, status: str) -> dict | None:
    """apply_status を更新し、更新後のレコードを返す。"""
    now = _now()
    with transaction() as txn:
        txn.execute(
            "UPDATE submissions SET apply_status = ?, updated_at = ? WHERE id = ?",
            (status, now, submission_id),
        )
    return get_by_id(submission_id)


def update_staff_id(submission_id: int, staff_id: int) -> dict | None:
    """staff_id（手動紐付け）を更新し、更新後のレコードを返す。

    旧 staff_id が存在し新しい値と異なる場合、旧スタッフの is_latest_for_staff も再計算する。
    """
    existing = get_by_id(submission_id)
    if existing is None:
        return None

    old_staff_id: int | None = existing["staff_id"]
    period_id: int = existing["period_id"]

    now = _now()
    with transaction() as txn:
        txn.execute(
            "UPDATE submissions SET staff_id = ?, updated_at = ? WHERE id = ?",
            (staff_id, now, submission_id),
        )

    # 新スタッフの最新フラグを再計算
    update_is_latest_for_staff(period_id, staff_id)

    # 旧スタッフが存在し別スタッフの場合は旧スタッフ側も再計算
    if old_staff_id is not None and old_staff_id != staff_id:
        update_is_latest_for_staff(period_id, old_staff_id)

    return get_by_id(submission_id)


def update_is_latest_for_staff(period_id: int, staff_id: int) -> None:
    """指定スタッフ・期間の全回答の is_latest_for_staff を再計算する。

    紐付き済み（staff_id非NULL）の中で submitted_at が最も新しい1件を1、他を0に設定する。
    未紐付け回答（staff_id=NULL）は常に0のまま。
    """
    with transaction() as txn:
        # 全件いったん0にリセット
        txn.execute(
            """
            UPDATE submissions SET is_latest_for_staff = 0
            WHERE period_id = ? AND staff_id = ?
            """,
            (period_id, staff_id),
        )
        # 最新1件を1に設定
        txn.execute(
            """
            UPDATE submissions SET is_latest_for_staff = 1
            WHERE id = (
                SELECT id FROM submissions
                WHERE period_id = ? AND staff_id = ?
                ORDER BY submitted_at DESC, id DESC
                LIMIT 1
            )
            """,
            (period_id, staff_id),
        )


# ── submission_day_entries ────────────────────────────────────────────────────

def get_day_entries(submission_id: int) -> list[dict]:
    """回答の日別エントリーを work_date 昇順で返す。"""
    rows = get_connection().execute(
        "SELECT * FROM submission_day_entries WHERE submission_id = ? ORDER BY work_date ASC",
        (submission_id,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def upsert_day_entries(submission_id: int, entries: list[dict]) -> None:
    """日別エントリーを一括 UPSERT する。

    entries の各要素は {"work_date": str, "start_time": float|None, "end_time": float|None}
    """
    now = _now()
    with transaction() as txn:
        for entry in entries:
            txn.execute(
                """
                INSERT INTO submission_day_entries
                    (submission_id, work_date, start_time, end_time, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(submission_id, work_date) DO UPDATE SET
                    start_time = excluded.start_time,
                    end_time   = excluded.end_time,
                    updated_at = excluded.updated_at
                """,
                (submission_id, entry["work_date"], entry.get("start_time"), entry.get("end_time"), now, now),
            )
