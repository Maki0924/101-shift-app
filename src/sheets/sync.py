"""Google Sheets 同期

スプレッドシートから回答を読み込み、submissions / submission_day_entries に保存する。
冪等性キー（SHA-256）で重複を排除し、モードA/B両対応でパースする。
"""

import datetime
import hashlib
import re
from dataclasses import dataclass, field

from src.db.repositories import submission_repo
from src.logic.weekly_pref_parser import parse as parse_weekly_pref
from src.sheets import column_mapper as col_mod
from src.sheets.column_mapper import ColumnMap
from src.utils.logger import get_logger

_NULL_TOKEN = "__NULL__"
_NOTE_MAX_LEN = 150

# モードB変換テーブル: (午前不可, 午後不可) → (start_time, end_time)
_MODE_B_TABLE: dict[tuple[bool, bool], tuple[float | None, float | None]] = {
    (False, False): (11.0, 22.0),   # 両方チェックなし → 終日
    (True,  False): (18.0, 22.0),   # 午前不可のみ → 午後のみ入れる
    (False, True):  (11.0, 16.0),   # 午後不可のみ → 午前のみ入れる
    (True,  True):  (None, None),   # 両方不可 → 勤務不可
}

# タイムスタンプ解析フォーマット候補
_TS_FORMATS = [
    "%Y/%m/%d %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
]


@dataclass
class SyncResult:
    """1期間の同期結果。"""
    period_id: int
    added: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)


# ── 内部ヘルパー ──────────────────────────────────────────────────────────────

def _norm_str(value: str | None) -> str:
    """文字列を正規化する（トリム・改行統一・NULL変換）。"""
    if value is None:
        return _NULL_TOKEN
    s = value.strip().replace("\r\n", "\n").replace("\r", "\n")
    return s if s else _NULL_TOKEN


def _parse_time_str(s: str | None) -> float | None:
    """HH:MM 形式を30分単位の float に変換する。変換不能なら None。"""
    if not s or not s.strip():
        return None
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s.strip())
    if not m:
        return None
    h, mm = int(m.group(1)), int(m.group(2))
    if mm not in (0, 30):
        return None
    return float(h) + (0.5 if mm == 30 else 0.0)


def _norm_time_for_hash(raw: str | None) -> str:
    """時刻文字列をハッシュ用正規化表現に変換する。9 と 9.0 を同一視する。"""
    if not raw or not raw.strip():
        return _NULL_TOKEN
    v = _parse_time_str(raw.strip())
    return str(v) if v is not None else raw.strip()


def _generate_key(
    submitted_at_raw: str,
    raw_staff_name: str,
    period_id: int,
    note_raw: str | None,
    weekly_pref_raw: str | None,
    mode_raw: str | None,
    date_time_values: list[tuple[str | None, str | None]],
) -> str:
    """external_submission_key（SHA-256 hex）を生成する。"""
    parts = [
        _norm_str(submitted_at_raw),
        _norm_str(raw_staff_name),
        str(period_id),
        _norm_str(note_raw),
        _norm_str(weekly_pref_raw),
        _norm_str(mode_raw),
    ]
    for start_raw, end_raw in date_time_values:
        parts.append(_norm_time_for_hash(start_raw))
        parts.append(_norm_time_for_hash(end_raw))

    raw = "\t".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_submitted_at(raw: str) -> str:
    """スプレッドシートのタイムスタンプを YYYY-MM-DD HH:MM:SS 形式に変換する。"""
    for fmt in _TS_FORMATS:
        try:
            return datetime.datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return raw.strip()[:19]  # フォールバック


def _cell(row: list[str], idx: int | None) -> str | None:
    """行から指定インデックスのセル値を返す。範囲外・空は None。"""
    if idx is None or idx >= len(row):
        return None
    v = row[idx]
    return v if v else None


def _date_range(start_date: str, end_date: str) -> list[str]:
    """期間内の全日付を YYYY-MM-DD リストで返す。"""
    start = datetime.date.fromisoformat(start_date)
    end = datetime.date.fromisoformat(end_date)
    dates = []
    d = start
    while d <= end:
        dates.append(d.isoformat())
        d += datetime.timedelta(days=1)
    return dates


def _parse_mode_a(
    start_raw: str | None,
    end_raw: str | None,
    date_str: str,
    result: SyncResult,
    ctx: str,
) -> tuple[float | None, float | None]:
    """モードAの開始・終了をパースする。片側でも異常なら両方 None（警告追加）。"""
    start = _parse_time_str(start_raw)
    end = _parse_time_str(end_raw)

    if start_raw and start is None:
        result.warnings.append(f"時刻異常: {date_str}_開始='{start_raw}' → NULL ({ctx})")
        return None, None
    if end_raw and end is None:
        result.warnings.append(f"時刻異常: {date_str}_終了='{end_raw}' → NULL ({ctx})")
        return None, None
    # 片側のみ入力（time_utils の ONE_SIDE_NULL に相当）
    if (start is None) != (end is None):
        side = "終了" if start is not None else "開始"
        result.warnings.append(f"時刻異常: {date_str} 片側のみ入力（{side}が空欄） → NULL ({ctx})")
        return None, None
    if start is not None and end is not None and start >= end:
        result.warnings.append(f"時刻異常: {date_str} 開始({start}) >= 終了({end}) → NULL ({ctx})")
        return None, None

    return start, end


def _parse_mode_b(
    morning_raw: str | None,
    afternoon_raw: str | None,
) -> tuple[float | None, float | None]:
    """モードBの午前不可・午後不可フラグから start/end を返す。

    Sheets はチェックボックスのオプション値テキスト（"入れない"）を記録するため、
    非空文字列 = チェックあり として判定する。
    """
    is_morning = bool((morning_raw or "").strip())
    is_afternoon = bool((afternoon_raw or "").strip())
    return _MODE_B_TABLE[(is_morning, is_afternoon)]


def _process_row(
    row: list[str],
    cm: ColumnMap,
    period: dict,
    all_dates: list[str],
    staff_map: dict[str, int],
    result: SyncResult,
) -> None:
    period_id = period["id"]

    submitted_at_raw = _cell(row, cm.submitted_at_idx)
    if not submitted_at_raw:
        result.warnings.append("タイムスタンプが空の行をスキップ")
        return

    raw_staff_name = (_cell(row, cm.staff_name_idx) or "").strip()
    if not raw_staff_name:
        result.warnings.append(f"スタッフ名が空の行をスキップ ({submitted_at_raw})")
        return

    ctx = f"{raw_staff_name} @ {submitted_at_raw}"
    submitted_at = _parse_submitted_at(submitted_at_raw)

    note_raw = _cell(row, cm.note_idx)
    note_text: str | None = None
    if note_raw:
        note_text = note_raw.strip()
        if len(note_text) > _NOTE_MAX_LEN:
            result.warnings.append(f"備考が{_NOTE_MAX_LEN}文字を超えているため切り捨て ({ctx})")
            note_text = note_text[:_NOTE_MAX_LEN]

    weekly_pref_raw = _cell(row, cm.weekly_pref_idx)
    weekly_pref_min, weekly_pref_max = parse_weekly_pref(weekly_pref_raw)
    if (weekly_pref_raw and weekly_pref_raw.strip()
            and weekly_pref_min is None and weekly_pref_max is None):
        result.warnings.append(f"週何回希望のパース不能: '{weekly_pref_raw}' ({ctx})")

    mode_raw = (_cell(row, cm.mode_idx) or "").strip()
    is_mode_b = mode_raw == "mode_b"

    # 全日付の時刻値をハッシュ用に収集
    date_time_values: list[tuple[str | None, str | None]] = []
    for date_str in all_dates:
        if is_mode_b:
            date_time_values.append((
                _cell(row, cm.mode_b_morning.get(date_str)),
                _cell(row, cm.mode_b_afternoon.get(date_str)),
            ))
        else:
            date_time_values.append((
                _cell(row, cm.mode_a_start.get(date_str)),
                _cell(row, cm.mode_a_end.get(date_str)),
            ))

    key = _generate_key(
        submitted_at_raw, raw_staff_name, period_id,
        note_raw, weekly_pref_raw, mode_raw, date_time_values,
    )

    if submission_repo.exists_by_key(key):
        result.skipped += 1
        return

    staff_id = staff_map.get(raw_staff_name)
    if staff_id is None:
        result.warnings.append(f"未紐付け回答: '{raw_staff_name}' ({ctx})")

    # 全日付分の day_entries を作成（列なし・勤務不可 は NULL/NULL）
    entries = []
    for i, date_str in enumerate(all_dates):
        s_raw, e_raw = date_time_values[i]
        if is_mode_b:
            start, end = _parse_mode_b(s_raw, e_raw)
        else:
            start, end = _parse_mode_a(s_raw, e_raw, date_str, result, ctx)
        entries.append({"work_date": date_str, "start_time": start, "end_time": end})

    # submission と day_entries を1トランザクションで作成する
    # （分断した場合、day_entries 失敗時に submission だけ残り永久スキップになる）
    submission_repo.create_with_day_entries(
        period_id=period_id,
        staff_id=staff_id,
        raw_staff_name=raw_staff_name,
        external_submission_key=key,
        submitted_at=submitted_at,
        note_text=note_text,
        weekly_pref_min=weekly_pref_min,
        weekly_pref_max=weekly_pref_max,
        day_entries=entries,
    )
    result.added += 1
    get_logger().debug("added submission: %s (period %d)", key[:8], period_id)


# ── 公開 API ──────────────────────────────────────────────────────────────────

def sync_period(
    period: dict,
    sheets_service,
    staff_map: dict[str, int],
) -> SyncResult:
    """1期間のスプレッドシートから回答を同期する。

    Args:
        period: periods レコード（id / start_date / end_date / spreadsheet_id を使用）
        sheets_service: Sheets API v4 サービス
        staff_map: raw_staff_name → staff_id のマッピング

    Returns:
        SyncResult（追加件数・スキップ件数・警告リスト）
    """
    result = SyncResult(period_id=period["id"])
    spreadsheet_id = period.get("spreadsheet_id")
    if not spreadsheet_id:
        return result

    response = sheets_service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="A:ZZZ",  # 列数が期間長に応じて動的に変わるため広めに指定
    ).execute()

    rows = response.get("values", [])
    if len(rows) < 2:
        get_logger().info("sync_period: no data rows (period %d)", period["id"])
        return result

    headers = [str(h) for h in rows[0]]
    cm = col_mod.parse_header(headers, period["start_date"], period["end_date"])

    for col_name in cm.unknown_cols:
        result.warnings.append(f"対象外列: {col_name}")

    all_dates = _date_range(period["start_date"], period["end_date"])

    for row in rows[1:]:
        try:
            _process_row(row, cm, period, all_dates, staff_map, result)
        except Exception as e:
            get_logger().warning("sync_period row error (period %d): %s", period["id"], e, exc_info=True)
            result.warnings.append(f"行処理エラー: {e}")

    get_logger().info(
        "sync_period done (period %d): added=%d skipped=%d warnings=%d",
        period["id"], result.added, result.skipped, len(result.warnings),
    )
    return result
