"""一括反映ロジック（コミット22）

スタッフ単位の希望シフト一括反映。
モード:
  - "all"       : 全日付を上書き
  - "empty_only": 未編集セルのみ反映（既存の edited_shifts はスキップ）
"""

from __future__ import annotations

from src.db.repositories import edited_shift_repo, wish_shift_repo


def bulk_apply(
    period_id: int,
    staff_id: int,
    mode: str = "all",
) -> list[dict]:
    """スタッフの希望シフトを編集シフトに一括反映し、更新後のレコードリストを返す。

    Args:
        period_id: 対象期間ID
        staff_id: 対象スタッフID
        mode: "all" または "empty_only"

    Returns:
        更新後の edited_shifts レコードリスト（period_id・staff_id で絞り込んだもの）
    """
    if mode not in ("all", "empty_only"):
        raise ValueError(f"mode は 'all' または 'empty_only' のみ有効です: {mode!r}")

    wish_shifts = wish_shift_repo.get_by_period_and_staff(period_id, staff_id)
    if not wish_shifts:
        return edited_shift_repo.get_by_period_and_staff(period_id, staff_id)

    if mode == "empty_only":
        existing = edited_shift_repo.get_by_period_and_staff(period_id, staff_id)
        existing_dates = {r["work_date"] for r in existing}
        targets = [w for w in wish_shifts if w["work_date"] not in existing_dates]
    else:
        targets = wish_shifts

    if targets:
        shifts = [
            {
                "work_date": w["work_date"],
                "start_time": w["start_time"],
                "end_time": w["end_time"],
            }
            for w in targets
        ]
        edited_shift_repo.upsert_bulk(period_id, staff_id, shifts)

    return edited_shift_repo.get_by_period_and_staff(period_id, staff_id)
