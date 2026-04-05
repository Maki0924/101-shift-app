"""submission_day_entries → wish_shifts 変換

勤務可能日（start_time / end_time 両方非NULL）のみを wish_shifts 形式に変換する。
"""


def parse(submission_id: int, entries: list[dict]) -> list[dict]:
    """日別エントリーを wish_shifts 形式に変換する。

    Args:
        submission_id: 対象回答ID（wish_shifts.submission_id に設定する）
        entries: submission_day_entries のレコードリスト

    Returns:
        勤務可能日のみのリスト。各要素は
        {"work_date": str, "start_time": float, "end_time": float, "submission_id": int}
    """
    result = []
    for entry in entries:
        start = entry.get("start_time")
        end = entry.get("end_time")
        if start is None or end is None:
            continue
        result.append({
            "work_date": entry["work_date"],
            "start_time": start,
            "end_time": end,
            "submission_id": submission_id,
        })
    return result
