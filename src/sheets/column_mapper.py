"""スプレッドシート列名 → work_date 解決

列名規約 (`MM/DD_開始` / `MM/DD_終了` / `MM/DD_午前不可` / `MM/DD_午後不可`) を
解析して列インデックスと対応する work_date にマッピングする。
年跨ぎ期間に対応するため、start_date / end_date から年を解決する。
"""

import datetime
import re
from dataclasses import dataclass, field

_RE_MODE_A = re.compile(r"^(\d{1,2}/\d{1,2})_(開始|終了)$")
_RE_MODE_B = re.compile(r"^(\d{1,2}/\d{1,2})_(午前不可|午後不可)$")


@dataclass
class ColumnMap:
    """ヘッダー行の解析結果。"""
    submitted_at_idx: int | None = None
    staff_name_idx: int | None = None
    note_idx: int | None = None
    weekly_pref_idx: int | None = None
    mode_idx: int | None = None
    # date_str (YYYY-MM-DD) → 列インデックス
    mode_a_start: dict[str, int] = field(default_factory=dict)
    mode_a_end: dict[str, int] = field(default_factory=dict)
    mode_b_morning: dict[str, int] = field(default_factory=dict)
    mode_b_afternoon: dict[str, int] = field(default_factory=dict)
    unknown_cols: list[str] = field(default_factory=list)


def resolve_date(mm_dd: str, start_date: str, end_date: str) -> str | None:
    """MM/DD 形式を期間の年から解決して YYYY-MM-DD 文字列を返す。

    年跨ぎ期間（例: 2026-12-21〜2027-01-20）にも対応する。
    期間外の日付は None を返す。
    """
    try:
        month, day = map(int, mm_dd.split("/"))
    except (ValueError, AttributeError):
        return None

    start = datetime.date.fromisoformat(start_date)
    end = datetime.date.fromisoformat(end_date)

    for year in sorted({start.year, end.year}):
        try:
            d = datetime.date(year, month, day)
            if start <= d <= end:
                return d.isoformat()
        except ValueError:
            continue
    return None


def parse_header(headers: list[str], start_date: str, end_date: str) -> ColumnMap:
    """ヘッダー行を解析して ColumnMap を返す。

    認識できない列名は ColumnMap.unknown_cols に追加する。
    """
    cm = ColumnMap()

    for i, h in enumerate(headers):
        h = h.strip()
        if h == "タイムスタンプ":
            cm.submitted_at_idx = i
        elif h == "スタッフ名":
            cm.staff_name_idx = i
        elif h == "備考":
            cm.note_idx = i
        elif h == "週何回希望":
            cm.weekly_pref_idx = i
        elif h == "入力方式":
            cm.mode_idx = i
        else:
            m = _RE_MODE_A.match(h)
            if m:
                date_str = resolve_date(m.group(1), start_date, end_date)
                if date_str:
                    if m.group(2) == "開始":
                        cm.mode_a_start[date_str] = i
                    else:
                        cm.mode_a_end[date_str] = i
                else:
                    cm.unknown_cols.append(h)
                continue

            m = _RE_MODE_B.match(h)
            if m:
                date_str = resolve_date(m.group(1), start_date, end_date)
                if date_str:
                    if m.group(2) == "午前不可":
                        cm.mode_b_morning[date_str] = i
                    else:
                        cm.mode_b_afternoon[date_str] = i
                else:
                    cm.unknown_cols.append(h)
                continue

            cm.unknown_cols.append(h)

    return cm
