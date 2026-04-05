"""採用処理トランザクション

回答採用を1トランザクションで実行する:
  1. 旧採用解除（同一スタッフ・同一期間の applied → pending）
  2. 新回答を採用（apply_status = 'applied'）
  3. wish_shifts 再生成（DELETE + INSERT）
  4. is_latest_for_staff 再計算
"""

from datetime import datetime

from src.db.connection import transaction
from src.db.repositories import submission_repo
from src.logic import submission_day_parser


class ApplyError(Exception):
    """採用処理の前提条件違反。"""


def apply(submission_id: int) -> None:
    """回答を採用する。

    Args:
        submission_id: 採用する回答のID

    Raises:
        ApplyError: 回答が存在しない、または staff_id が未解決の場合
    """
    sub = submission_repo.get_by_id(submission_id)
    if sub is None:
        raise ApplyError(f"submission {submission_id} not found")

    staff_id: int | None = sub["staff_id"]
    if staff_id is None:
        raise ApplyError("staff_id が未解決のため採用できません。スタッフ紐付け後に採用してください。")

    period_id: int = sub["period_id"]

    entries = submission_repo.get_day_entries(submission_id)
    wish_records = submission_day_parser.parse(submission_id, entries)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with transaction() as txn:
        # 1. 旧採用解除
        txn.execute(
            "UPDATE submissions SET apply_status = 'pending', updated_at = ? "
            "WHERE period_id = ? AND staff_id = ? AND apply_status = 'applied'",
            (now, period_id, staff_id),
        )
        # 2. 新採用
        txn.execute(
            "UPDATE submissions SET apply_status = 'applied', updated_at = ? WHERE id = ?",
            (now, submission_id),
        )
        # 3. wish_shifts 再生成（DELETE + INSERT）
        txn.execute(
            "DELETE FROM wish_shifts WHERE period_id = ? AND staff_id = ?",
            (period_id, staff_id),
        )
        for r in wish_records:
            txn.execute(
                """
                INSERT INTO wish_shifts
                    (period_id, staff_id, work_date, start_time, end_time, submission_id,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    period_id, staff_id,
                    r["work_date"], r["start_time"], r["end_time"], r["submission_id"],
                    now, now,
                ),
            )
        # 4. is_latest_for_staff 再計算
        txn.execute(
            "UPDATE submissions SET is_latest_for_staff = 0 WHERE period_id = ? AND staff_id = ?",
            (period_id, staff_id),
        )
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
