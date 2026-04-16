"""印刷処理（コミット25）

HTML テーブルを生成し、webbrowser.open() 経由でブラウザの印刷ダイアログを開く。
webbrowser モジュールは Windows / macOS / Linux 対応の標準ライブラリ。
外部ライブラリ不要。reportlab / fpdf2 は使用しない。

生成する HTML は以下の仕様:
- A4横 @page ルール（10mm マージン）
- スタッフ × 日付テーブル（セル色: 手動色 > 曜日色）
- ページ境界は CSS page-break-after で制御
- 人件費・サマリー行なし（§17-5）
- 期間外の日付列も印刷（セル空欄・曜日色）
"""

from __future__ import annotations

import datetime
import html
import tempfile
import webbrowser
from pathlib import Path

from src.logic.holiday import is_holiday, is_saturday, is_sunday
from src.logic.print_layout import PageLayout, calc_layout
from src.ui.components.shift_grid import make_date_list

# セル色（CSS 16進数）
_C_SAT = "#dbeafe"
_C_SUN = "#fce7f3"
_C_MARK_R = "#fca5a5"
_C_MARK_Y = "#fef08a"
_C_HDR = "#f3f4f6"
_C_NAME = "#f9fafb"
_C_WHITE = "#ffffff"
_C_GRID = "#d1d5db"

_WDAY_JP = ("月", "火", "水", "木", "金", "土", "日")


def print_shift(
    period: dict,
    from_date_str: str,
    to_date_str: str,
    staff_list: list[dict],
    edited: dict[tuple[int, str], dict],
    marks: dict[tuple[int, str], str],
    rules: list[dict],
    font_size: int = 10,
) -> None:
    """シフト表を HTML で生成してブラウザの印刷ダイアログで開く。

    Args:
        period: 期間レコード（name / start_date / end_date）
        from_date_str: 印刷開始日（YYYY-MM-DD）
        to_date_str: 印刷終了日（YYYY-MM-DD）
        staff_list: スタッフリスト
        edited: {(staff_id, work_date): shift_record}
        marks: {(staff_id, work_date): mark_color}
        rules: custom_day_rules レコードリスト
        font_size: ターゲットフォントサイズ（pt）
    """
    # 指定範囲をそのまま日付リストにする（期間外の列はセル空欄・曜日色）
    dates = make_date_list(from_date_str, to_date_str)

    if not dates or not staff_list:
        return

    layout = calc_layout(dates, staff_list, font_size=font_size)
    html_str = _build_html(period, layout, edited, marks, rules)

    tmp_path = _write_preview_html(html_str)

    # webbrowser.open は Windows / macOS / Linux 対応
    webbrowser.open(Path(tmp_path).as_uri())


# アプリ専用の一時ディレクトリ名
_PREVIEW_DIR_NAME = "shift_app_preview"


def _write_preview_html(html_str: str) -> str:
    """専用サブディレクトリにプレビュー HTML を書き出し、古いファイルを削除する。

    Returns:
        書き出したファイルの絶対パス文字列。
    """
    preview_dir = Path(tempfile.gettempdir()) / _PREVIEW_DIR_NAME
    preview_dir.mkdir(exist_ok=True)

    # 古いプレビュー HTML を掃除する
    for old in preview_dir.glob("*.html"):
        try:
            old.unlink()
        except OSError:
            pass  # 他プロセスが開いている場合などは無視

    out = preview_dir / "preview.html"
    out.write_text(html_str, encoding="utf-8")
    return str(out)


def _build_html(
    period: dict,
    layout: PageLayout,
    edited: dict[tuple[int, str], dict],
    marks: dict[tuple[int, str], str],
    rules: list[dict],
) -> str:
    title = html.escape(period["name"])
    pages_html = []
    for i, page in enumerate(layout.pages):
        is_last = i == len(layout.pages) - 1
        page_html = _render_page(page, edited, marks, rules, is_last)
        pages_html.append(page_html)

    body = "\n".join(pages_html)
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
@page {{
  size: A4 landscape;
  margin: 10mm;
}}
body {{
  font-family: "Hiragino Sans", "Yu Gothic", sans-serif;
  font-size: 9pt;
  margin: 0;
  padding: 0;
}}
.page {{
  page-break-after: always;
}}
.page:last-child {{
  page-break-after: avoid;
}}
table {{
  border-collapse: collapse;
  table-layout: fixed;
  width: 100%;
}}
th, td {{
  border: 1px solid {_C_GRID};
  padding: 1px 2px;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
}}
.hdr {{
  background: {_C_HDR};
  font-weight: bold;
  font-size: 8pt;
}}
.name-cell {{
  background: {_C_NAME};
  text-align: left;
  padding-left: 4px;
  min-width: 5em;
}}
.sat {{
  background: {_C_SAT};
}}
.sun {{
  background: {_C_SUN};
}}
.mark-red {{
  background: {_C_MARK_R};
}}
.mark-yellow {{
  background: {_C_MARK_Y};
}}
</style>
</head>
<body>
{body}
</body>
</html>"""


def _render_page(
    page,
    edited: dict[tuple[int, str], dict],
    marks: dict[tuple[int, str], str],
    rules: list[dict],
    is_last: bool,
) -> str:
    rows = []
    # ── ヘッダー行 ──
    header_cells = ['<th class="hdr name-cell">スタッフ名</th>']
    for date_str in page.dates:
        date = datetime.date.fromisoformat(date_str)
        cls = _date_cls(date, rules)
        cls_attr = f' class="hdr {cls}"' if cls else ' class="hdr"'
        day_label = _WDAY_JP[date.weekday()]
        header_cells.append(f"<th{cls_attr}>{date.day}<br>{day_label}</th>")
    rows.append("<tr>" + "".join(header_cells) + "</tr>")

    # ── スタッフ行 ──
    for st in page.staff:
        cells = [f'<td class="name-cell">{html.escape(st["name"])}</td>']
        for date_str in page.dates:
            shift = edited.get((st["id"], date_str))
            mark = marks.get((st["id"], date_str))
            date = datetime.date.fromisoformat(date_str)

            if mark == "red":
                cls = "mark-red"
            elif mark == "yellow":
                cls = "mark-yellow"
            else:
                cls = _date_cls(date, rules)

            cls_attr = f' class="{cls}"' if cls else ""
            text = _print_cell_text(shift)
            cells.append(f"<td{cls_attr}>{html.escape(text)}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")

    table = "<table>\n" + "\n".join(rows) + "\n</table>"
    div_class = "page last-page" if is_last else "page"
    return f'<div class="{div_class}">\n{table}\n</div>'


def _date_cls(date: datetime.date, rules: list[dict]) -> str:
    """CSS クラス名を返す（土→"sat", 日祝→"sun", 平日→""）。"""
    if is_sunday(date) or is_holiday(date, rules):
        return "sun"
    if is_saturday(date):
        return "sat"
    return ""


def _print_cell_text(shift: dict | None) -> str:
    """印刷用セルテキスト（§17-5）。"""
    if shift is None:
        return ""
    s, e = shift.get("start_time"), shift.get("end_time")
    if s is None and e is None:
        return "—"
    if s is None or e is None:
        return ""
    return f"{_fmt(s)}-{_fmt(e)}"


def _fmt(v: float) -> str:
    h, m = int(v), int(round((v - int(v)) * 60))
    return f"{h}:{m:02d}" if m else str(h)
