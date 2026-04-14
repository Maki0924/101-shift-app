"""シフト編集グリッドコンポーネント（コミット19）

Canvas/Label によるグリッド描画。Entry widget は使用しない。
左列（スタッフ名）と上行（日付ヘッダー）は固定、本体セルは横スクロール可。
"""

from __future__ import annotations

import datetime
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from src.logic.holiday import is_holiday, is_saturday, is_sunday
from src.logic.staff_count import calc_day_count
from src.logic.time_utils import is_error
from src.logic.wage_calc import calc_wage, is_calculable

# ── レイアウト定数 ──────────────────────────────────────────────────────────
_LEFT_W = 92  # スタッフ名列幅 (px)
_ROW_H = 26  # 行高さ (px)
_HDR_H = 44  # 日付ヘッダー高さ (px)
_COL_W = 52  # 日付列幅 (px)

_SUMMARY_LABELS = ("昼人数", "夜人数", "日別人件費")
_WDAY_JP = ("月", "火", "水", "木", "金", "土", "日")

# ── 色定数 ──────────────────────────────────────────────────────────────────
_C_SAT_BG = "#dbeafe"  # 土曜背景
_C_SUN_BG = "#fce7f3"  # 日祝背景
_C_WHITE = "#ffffff"  # 通常背景
_C_ERR_BG = "#fee2e2"  # エラーセル背景
_C_MARK_R = "#fca5a5"  # 手動色赤
_C_MARK_Y = "#fef08a"  # 手動色黄
_C_ERR_BD = "#ef4444"  # エラー枠
_C_SEL_BD = "#2563eb"  # 選択枠
_C_GRID = "#d1d5db"  # グリッド線
_C_HDR_BG = "#f3f4f6"  # ヘッダー背景
_C_SUM_BG = "#f9fafb"  # サマリー行背景
_C_SHORT = "#ef4444"  # 人数不足背景
_C_UNSUB = "#f97316"  # 未提出スタッフ文字色


class ShiftGrid(ttk.Frame):
    """Canvas ベースのシフト編集グリッド。

    使い方::

        grid = ShiftGrid(parent, period=p, staff_list=sl, on_cell_select=cb)
        grid.pack(fill="both", expand=True)
        grid.load(edited_shifts, wish_shifts, cell_marks, submissions, settings, rules)
    """

    def __init__(
        self,
        master: tk.Misc,
        period: dict,
        staff_list: list[dict],
        on_cell_select: Callable[[int, str], None],
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self._period = period
        self._staff_list = staff_list
        self._on_cell_select = on_cell_select
        self._dates: list[str] = make_date_list(period["start_date"], period["end_date"])

        # データ
        self._edited: dict[tuple[int, str], dict] = {}
        self._wishes: dict[int, list[dict]] = {}
        self._marks: dict[tuple[int, str], str] = {}
        self._unsubmitted: set[int] = set()
        self._settings: dict = {}
        self._rules: list[dict] = []

        # 状態
        self._edit_mode: bool = False
        self._selected: tuple[int, str] | None = None
        self._weekly_colors: dict[int, str] = {}

        # 計算済みサマリー
        self._day_counts: dict[str, tuple[int, int, bool, bool]] = {}
        self._day_wages: dict[str, int] = {}

        self._build()

    # ── 構築 ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        n_content = len(self._staff_list) + len(_SUMMARY_LABELS)
        total_w = len(self._dates) * _COL_W
        body_h = n_content * _ROW_H

        self.grid_columnconfigure(0, weight=0, minsize=_LEFT_W)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=0, minsize=_HDR_H)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)

        # コーナー
        self._corner = tk.Canvas(
            self,
            width=_LEFT_W,
            height=_HDR_H,
            bg=_C_HDR_BG,
            highlightthickness=1,
            highlightbackground=_C_GRID,
        )
        self._corner.grid(row=0, column=0, sticky="nsew")
        self._corner.create_text(
            _LEFT_W // 2,
            _HDR_H // 2,
            text="スタッフ名",
            font=("", 9, "bold"),
            anchor="center",
        )

        # 日付ヘッダー Canvas（x スクロールのみ）
        self._hdr_cv = tk.Canvas(
            self,
            height=_HDR_H,
            bg=_C_HDR_BG,
            highlightthickness=0,
        )
        self._hdr_cv.grid(row=0, column=1, sticky="ew")
        self._hdr_cv.configure(scrollregion=(0, 0, total_w, _HDR_H))

        # スタッフ名 Canvas（固定）
        self._name_cv = tk.Canvas(
            self,
            width=_LEFT_W,
            bg=_C_WHITE,
            highlightthickness=1,
            highlightbackground=_C_GRID,
        )
        self._name_cv.grid(row=1, column=0, sticky="nsew")
        self._name_cv.configure(scrollregion=(0, 0, _LEFT_W, body_h))

        # ボディ Canvas（x スクロール）
        self._body_cv = tk.Canvas(self, bg=_C_WHITE, highlightthickness=0)
        self._body_cv.grid(row=1, column=1, sticky="nsew")
        self._body_cv.configure(scrollregion=(0, 0, total_w, body_h))

        # 横スクロールバー
        self._hbar = ttk.Scrollbar(self, orient="horizontal", command=self._sync_xscroll)
        self._hbar.grid(row=2, column=1, sticky="ew")
        self._body_cv.configure(xscrollcommand=self._on_body_xscroll)

        # イベント
        self._body_cv.bind("<Button-1>", self._on_body_click)
        self._body_cv.bind("<MouseWheel>", self._on_wheel)
        self._hdr_cv.bind("<MouseWheel>", self._on_wheel)

    def _sync_xscroll(self, *args) -> None:
        self._hdr_cv.xview(*args)
        self._body_cv.xview(*args)

    def _on_body_xscroll(self, *args) -> None:
        self._hbar.set(*args)
        self._hdr_cv.xview_moveto(float(args[0]))

    def _on_wheel(self, event: tk.Event) -> None:
        delta = -1 if event.delta > 0 else 1
        self._sync_xscroll("scroll", delta, "units")

    # ── 公開 API ────────────────────────────────────────────────────────────

    def load(
        self,
        edited_shifts: list[dict],
        wish_shifts: list[dict],
        cell_marks: list[dict],
        submissions: list[dict],
        settings: dict,
        rules: list[dict],
    ) -> None:
        """全データを設定して再描画する。"""
        self._edited = {(r["staff_id"], r["work_date"]): r for r in edited_shifts}
        self._wishes = {}
        for w in wish_shifts:
            self._wishes.setdefault(w["staff_id"], []).append(w)
        self._marks = {(r["staff_id"], r["work_date"]): r["mark_color"] for r in cell_marks}
        applied_ids = {
            s["staff_id"] for s in submissions if s["apply_status"] == "applied" and s["staff_id"] is not None
        }
        self._unsubmitted = {
            s["id"] for s in self._staff_list if s["employment_type"] == "part_time" and s["id"] not in applied_ids
        }
        self._settings = settings
        self._rules = rules
        self._compute_summary()
        self._draw()

    def refresh_cell(
        self,
        staff_id: int,
        work_date: str,
        shift: dict | None,
        mark: dict | None,
    ) -> None:
        """単一セルを更新して再描画する。"""
        key = (staff_id, work_date)
        if shift is not None:
            self._edited[key] = shift
        else:
            self._edited.pop(key, None)
        if mark is not None:
            self._marks[key] = mark["mark_color"]
        else:
            self._marks.pop(key, None)
        self._compute_summary()
        self._draw()

    def set_edit_mode(self, edit_mode: bool) -> None:
        self._edit_mode = edit_mode
        self._draw_names()

    def set_weekly_colors(self, colors: dict[int, str] | None) -> None:
        """週回数判定色を設定する（None で解除）。"""
        self._weekly_colors = colors or {}
        self._draw_names()

    @property
    def selected_cell(self) -> tuple[int, str] | None:
        return self._selected

    def get_shift(self, staff_id: int, work_date: str) -> dict | None:
        return self._edited.get((staff_id, work_date))

    def get_wish_shifts(self, staff_id: int) -> list[dict]:
        return self._wishes.get(staff_id, [])

    # ── 計算 ────────────────────────────────────────────────────────────────

    def _compute_summary(self) -> None:
        s = self._settings
        if not s:
            return
        for date_str in self._dates:
            date = datetime.date.fromisoformat(date_str)
            day_shifts = [self._edited.get((st["id"], date_str)) or {} for st in self._staff_list]
            dc = calc_day_count(
                date,
                day_shifts,
                s["day_shift_start"],
                s["day_shift_end"],
                s["night_shift_start"],
                s["night_shift_end"],
                s["overlap_hours_threshold"],
                s["weekday_day_min_staff"],
                s["weekday_night_min_staff"],
                s["weekend_day_min_staff"],
                s["weekend_night_min_staff"],
                self._rules,
            )
            self._day_counts[date_str] = (dc.day_count, dc.night_count, dc.day_short, dc.night_short)
            total = 0
            for st in self._staff_list:
                sh = self._edited.get((st["id"], date_str))
                if sh and is_calculable(sh.get("start_time"), sh.get("end_time")):
                    total += calc_wage(
                        sh["start_time"],
                        sh["end_time"],
                        st["hourly_wage"],
                        date,
                        s["saturday_bonus"],
                        s["sunday_bonus"],
                        s["holiday_bonus"],
                        self._rules,
                    )
            self._day_wages[date_str] = total

    # ── 描画 ────────────────────────────────────────────────────────────────

    def _draw(self) -> None:
        self._draw_header()
        self._draw_names()
        self._draw_body()

    def _draw_header(self) -> None:
        cv = self._hdr_cv
        cv.delete("all")
        for col, date_str in enumerate(self._dates):
            x1, x2 = col * _COL_W, (col + 1) * _COL_W
            date = datetime.date.fromisoformat(date_str)
            bg = date_bg(date, self._rules)
            cv.create_rectangle(x1, 0, x2, _HDR_H, fill=bg, outline=_C_GRID)
            cv.create_text(x1 + _COL_W // 2, 12, text=_WDAY_JP[date.weekday()], font=("", 8), anchor="center")
            cv.create_text(x1 + _COL_W // 2, 30, text=str(date.day), font=("", 11, "bold"), anchor="center")

    def _draw_names(self) -> None:
        cv = self._name_cv
        cv.delete("all")
        wc_bg = {"red": "#fca5a5", "orange": "#fed7aa", "green": "#bbf7d0"}
        for row, st in enumerate(self._staff_list):
            y1, y2 = row * _ROW_H, (row + 1) * _ROW_H
            bg = wc_bg.get(self._weekly_colors.get(st["id"], ""), _C_WHITE)
            cv.create_rectangle(0, y1, _LEFT_W, y2, fill=bg, outline=_C_GRID)
            is_part = st["employment_type"] == "part_time"
            is_unsub = is_part and st["id"] in self._unsubmitted
            name = ("★ " if is_unsub else "") + st["name"]
            fg = _C_UNSUB if is_unsub else "black"
            cv.create_text(5, y1 + _ROW_H // 2, text=name, font=("", 9), anchor="w", fill=fg)

        for i, label in enumerate(_SUMMARY_LABELS):
            row = len(self._staff_list) + i
            y1, y2 = row * _ROW_H, (row + 1) * _ROW_H
            cv.create_rectangle(0, y1, _LEFT_W, y2, fill=_C_SUM_BG, outline=_C_GRID)
            cv.create_text(5, y1 + _ROW_H // 2, text=label, font=("", 9), anchor="w")

    def _draw_body(self) -> None:
        cv = self._body_cv
        cv.delete("all")
        for row, st in enumerate(self._staff_list):
            for col, date_str in enumerate(self._dates):
                self._draw_cell(cv, row, col, st, date_str)
        self._draw_summary(cv)

    def _draw_cell(self, cv: tk.Canvas, row: int, col: int, st: dict, date_str: str) -> None:
        x1, y1 = col * _COL_W, row * _ROW_H
        x2, y2 = x1 + _COL_W, y1 + _ROW_H

        shift = self._edited.get((st["id"], date_str))
        mark = self._marks.get((st["id"], date_str))
        date = datetime.date.fromisoformat(date_str)
        selected = self._selected == (st["id"], date_str)

        s_val = shift.get("start_time") if shift else None
        e_val = shift.get("end_time") if shift else None
        err = shift is not None and is_error(s_val, e_val)

        # 色優先順位: エラー > 手動色赤 > 手動色黄 > 曜日色
        if err:
            fill = _C_ERR_BG
        elif mark == "red":
            fill = _C_MARK_R
        elif mark == "yellow":
            fill = _C_MARK_Y
        else:
            fill = date_bg(date, self._rules)

        outline = _C_ERR_BD if err else (_C_SEL_BD if selected else _C_GRID)
        width = 2 if (err or selected) else 1

        tag = f"c_{st['id']}_{date_str}"
        cv.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=width, tags=tag)
        cv.create_text(
            x1 + _COL_W // 2, y1 + _ROW_H // 2, text=cell_text(shift), font=("", 8), anchor="center", tags=tag
        )

    def _draw_summary(self, cv: tk.Canvas) -> None:
        base = len(self._staff_list)
        for col, date_str in enumerate(self._dates):
            x1, x2 = col * _COL_W, (col + 1) * _COL_W
            counts = self._day_counts.get(date_str)
            wage = self._day_wages.get(date_str, 0)

            for i, (val, short) in enumerate(
                [
                    (str(counts[0]) if counts else "—", counts[2] if counts else False),
                    (str(counts[1]) if counts else "—", counts[3] if counts else False),
                ]
            ):
                y1, y2 = (base + i) * _ROW_H, (base + i + 1) * _ROW_H
                fill = _C_SHORT if short else _C_SUM_BG
                fg = "white" if short else "black"
                cv.create_rectangle(x1, y1, x2, y2, fill=fill, outline=_C_GRID)
                cv.create_text(x1 + _COL_W // 2, y1 + _ROW_H // 2, text=val, font=("", 8), anchor="center", fill=fg)

            y1, y2 = (base + 2) * _ROW_H, (base + 3) * _ROW_H
            wage_str = f"¥{wage:,}" if wage else "—"
            cv.create_rectangle(x1, y1, x2, y2, fill=_C_SUM_BG, outline=_C_GRID)
            cv.create_text(x1 + _COL_W // 2, y1 + _ROW_H // 2, text=wage_str, font=("", 7), anchor="center")

    # ── イベント ─────────────────────────────────────────────────────────────

    def _on_body_click(self, event: tk.Event) -> None:
        cx = self._body_cv.canvasx(event.x)
        cy = self._body_cv.canvasy(event.y)
        col = int(cx / _COL_W)
        row = int(cy / _ROW_H)
        if 0 <= col < len(self._dates) and 0 <= row < len(self._staff_list):
            st = self._staff_list[row]
            date_str = self._dates[col]
            self._selected = (st["id"], date_str)
            self._draw_body()
            self._on_cell_select(st["id"], date_str)


# ── モジュール公開ヘルパー（テストからも利用） ────────────────────────────────


def make_date_list(start_date: str, end_date: str) -> list[str]:
    """期間内の全日付（YYYY-MM-DD）リストを返す。"""
    start = datetime.date.fromisoformat(start_date)
    end = datetime.date.fromisoformat(end_date)
    dates: list[str] = []
    cur = start
    while cur <= end:
        dates.append(cur.isoformat())
        cur += datetime.timedelta(days=1)
    return dates


def date_bg(date: datetime.date, rules: list[dict] | None) -> str:
    """日付に対応するセル背景色を返す。"""
    if is_sunday(date) or is_holiday(date, rules):
        return _C_SUN_BG
    if is_saturday(date):
        return _C_SAT_BG
    return _C_WHITE


def cell_text(shift: dict | None) -> str:
    """シフトレコードからセル表示テキストを返す。"""
    if shift is None:
        return ""  # 未編集: 空欄
    s, e = shift.get("start_time"), shift.get("end_time")
    if s is None and e is None:
        return "—"  # 勤務なし
    if s is None or e is None:
        return "?"  # エラー（片側 NULL）
    return f"{_fmt(s)}-{_fmt(e)}"


def _fmt(v: float) -> str:
    h, m = int(v), int(round((v - int(v)) * 60))
    return f"{h}:{m:02d}" if m else str(h)
