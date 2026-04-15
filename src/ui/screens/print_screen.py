"""印刷プレビュー画面（コミット24）

A4横レイアウトのプレビューを Canvas に描画する。
日付範囲の変更・ページ切り替えをサポート。
印刷ボタンはコミット25で有効化。
"""

from __future__ import annotations

import datetime
import tkinter as tk
from tkinter import ttk

from src.db.repositories import (
    custom_day_repo,
    edited_shift_repo,
    mark_repo,
    period_repo,
    print_settings_repo,
    staff_repo,
)
from src.logic.holiday import is_holiday, is_saturday, is_sunday
from src.logic.print_layout import PageLayout, calc_layout
from src.ui.components.dialogs import show_error
from src.ui.components.shift_grid import make_date_list
from src.utils.logger import get_logger

# ── プレビュースケール ───────────────────────────────────────────────────────
_SCALE = 2.5  # プレビュー: px/mm
_MARGIN_PX = 16  # 用紙周囲の余白 (px)
_PAPER_W_PX = round(297 * _SCALE)
_PAPER_H_PX = round(210 * _SCALE)

# ── 色定数 ──────────────────────────────────────────────────────────────────
_C_BG = "#e5e7eb"  # キャンバス背景
_C_PAPER = "#ffffff"  # 用紙
_C_GRID = "#d1d5db"  # グリッド線
_C_HDR = "#f3f4f6"  # ヘッダー背景
_C_NAME = "#f9fafb"  # 名前列背景
_C_SAT = "#dbeafe"  # 土曜背景
_C_SUN = "#fce7f3"  # 日祝背景
_C_MARK_R = "#fca5a5"  # 手動色赤
_C_MARK_Y = "#fef08a"  # 手動色黄

_WDAY_JP = ("月", "火", "水", "木", "金", "土", "日")


class PrintScreen(ttk.Frame):
    """印刷プレビュー画面。"""

    def __init__(self, master: tk.Misc, app, period_id: int, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.app = app
        self._period_id = period_id
        # データ
        self._period: dict | None = None
        self._staff_list: list[dict] = []
        self._edited: dict[tuple[int, str], dict] = {}
        self._marks: dict[tuple[int, str], str] = {}
        self._rules: list[dict] = []
        # 状態
        self._layout: PageLayout | None = None
        self._current_page = 0
        self._from_var = tk.StringVar()
        self._to_var = tk.StringVar()
        self._build()
        self._load()

    # ── UI構築 ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # ── ヘッダーバー ──
        top = ttk.Frame(self)
        top.pack(fill="x", padx=16, pady=(12, 4))
        self._title_lbl = ttk.Label(top, text="印刷プレビュー", font=("", 14))
        self._title_lbl.pack(side="left")
        ttk.Button(top, text="戻る", command=self._on_back, width=8).pack(side="right")
        # 印刷ボタン: commit 25 で有効化
        self._print_btn = ttk.Button(top, text="印刷", command=self._on_print, width=8, state="disabled")
        self._print_btn.pack(side="right", padx=(0, 6))

        # ── 日付範囲 ──
        range_frame = ttk.LabelFrame(self, text="印刷範囲", padding=6)
        range_frame.pack(fill="x", padx=16, pady=(0, 4))
        ttk.Label(range_frame, text="開始日:").pack(side="left")
        ttk.Entry(range_frame, textvariable=self._from_var, width=12).pack(side="left", padx=(4, 12))
        ttk.Label(range_frame, text="終了日:").pack(side="left")
        ttk.Entry(range_frame, textvariable=self._to_var, width=12).pack(side="left", padx=(4, 12))
        ttk.Button(range_frame, text="更新", command=self._on_update_range, width=6).pack(side="left")

        # ── ページナビ ──
        nav_frame = ttk.Frame(self)
        nav_frame.pack(fill="x", padx=16, pady=(0, 4))
        self._prev_btn = ttk.Button(nav_frame, text="◀ 前ページ", command=self._on_prev, width=12, state="disabled")
        self._prev_btn.pack(side="left")
        self._page_lbl = ttk.Label(nav_frame, text="")
        self._page_lbl.pack(side="left", padx=8)
        self._next_btn = ttk.Button(nav_frame, text="次ページ ▶", command=self._on_next, width=12, state="disabled")
        self._next_btn.pack(side="left")

        # ── プレビューキャンバス ──
        cv_frame = ttk.Frame(self)
        cv_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        cv_frame.rowconfigure(0, weight=1)
        cv_frame.columnconfigure(0, weight=1)

        self._canvas = tk.Canvas(cv_frame, bg=_C_BG, highlightthickness=0)
        self._canvas.grid(row=0, column=0, sticky="nsew")

        hbar = ttk.Scrollbar(cv_frame, orient="horizontal", command=self._canvas.xview)
        hbar.grid(row=1, column=0, sticky="ew")
        vbar = ttk.Scrollbar(cv_frame, orient="vertical", command=self._canvas.yview)
        vbar.grid(row=0, column=1, sticky="ns")
        self._canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        self._canvas.bind("<MouseWheel>", self._on_wheel)

    # ── データ読み込み ────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            period = period_repo.get_by_id(self._period_id)
        except Exception as e:
            get_logger().error("印刷プレビュー: 期間読み込みエラー: %s", e, exc_info=True)
            show_error(self, "期間の読み込みに失敗しました。")
            return
        if period is None:
            show_error(self, "期間が見つかりません。")
            return

        self._period = period
        self._title_lbl.configure(text=f"印刷プレビュー — {period['name']}")

        try:
            self._staff_list = staff_repo.get_for_period(self._period_id)
            edited = edited_shift_repo.get_by_period(self._period_id)
            self._edited = {(r["staff_id"], r["work_date"]): r for r in edited}
            marks = mark_repo.get_by_period(self._period_id)
            self._marks = {(r["staff_id"], r["work_date"]): r["mark_color"] for r in marks}
            period_rules = custom_day_repo.get_by_period(self._period_id)
            global_rules = custom_day_repo.get_global()
            self._rules = period_rules + global_rules
        except Exception as e:
            get_logger().error("印刷プレビュー: データ読み込みエラー: %s", e, exc_info=True)
            show_error(self, "データの読み込みに失敗しました。")
            return

        # 印刷設定から日付範囲を取得（なければ期間全体）
        try:
            settings = print_settings_repo.get_by_period(self._period_id)
        except Exception:
            settings = None

        from_date = (settings or {}).get("print_from_date") or period["start_date"]
        to_date = (settings or {}).get("print_to_date") or period["end_date"]
        self._from_var.set(from_date)
        self._to_var.set(to_date)
        self._compute_and_draw()

    # ── レイアウト計算・描画 ──────────────────────────────────────────────────

    def _compute_and_draw(self) -> None:
        """日付範囲を解釈してレイアウトを再計算し、プレビューを描画する。"""
        if self._period is None:
            return

        from_str = self._from_var.get().strip()
        to_str = self._to_var.get().strip()

        try:
            from_date = datetime.date.fromisoformat(from_str)
            to_date = datetime.date.fromisoformat(to_str)
        except ValueError:
            show_error(self, "日付の形式が不正です（YYYY-MM-DD）。")
            return

        # 期間内にクランプ
        period_start = datetime.date.fromisoformat(self._period["start_date"])
        period_end = datetime.date.fromisoformat(self._period["end_date"])
        from_date = max(from_date, period_start)
        to_date = min(to_date, period_end)

        if from_date > to_date:
            show_error(self, "開始日が終了日より後になっています。")
            return

        # 日付リスト（期間の全日付から範囲を切り出す）
        all_dates = make_date_list(self._period["start_date"], self._period["end_date"])
        dates = [d for d in all_dates if from_date.isoformat() <= d <= to_date.isoformat()]

        if not dates:
            self._layout = None
            self._current_page = 0
            self._update_nav()
            self._canvas.delete("all")
            return

        self._layout = calc_layout(dates, self._staff_list)
        self._current_page = 0
        self._update_nav()
        self._draw_current_page()

    def _draw_current_page(self) -> None:
        self._canvas.delete("all")
        if not self._layout or not self._layout.pages:
            return
        self._draw_page(self._layout.pages[self._current_page])

    def _draw_page(self, page) -> None:
        """1ページ分をキャンバスに描画する。"""
        cv = self._canvas
        total_w = _PAPER_W_PX + 2 * _MARGIN_PX
        total_h = _PAPER_H_PX + 2 * _MARGIN_PX
        cv.configure(scrollregion=(0, 0, total_w, total_h))

        ox, oy = _MARGIN_PX, _MARGIN_PX

        # 用紙背景
        cv.create_rectangle(ox, oy, ox + _PAPER_W_PX, oy + _PAPER_H_PX, fill=_C_PAPER, outline="#9ca3af")

        # コンテンツ原点（印刷マージン分オフセット）
        margin_px = round(10.0 * _SCALE)
        cx, cy = ox + margin_px, oy + margin_px

        col_w = round(page.col_w_mm * _SCALE)
        row_h = round(page.row_h_mm * _SCALE)
        name_w = round(page.name_w_mm * _SCALE)
        hdr_h = round(page.hdr_h_mm * _SCALE)
        fs = max(6, page.font_size - 2)

        # ── コーナー ──
        cv.create_rectangle(cx, cy, cx + name_w, cy + hdr_h, fill=_C_HDR, outline=_C_GRID)
        cv.create_text(cx + name_w // 2, cy + hdr_h // 2, text="スタッフ名", font=("", fs - 1), anchor="center")

        # ── 日付ヘッダー ──
        for col, date_str in enumerate(page.dates):
            x1 = cx + name_w + col * col_w
            x2 = x1 + col_w
            y2 = cy + hdr_h
            date = datetime.date.fromisoformat(date_str)
            bg = _date_bg(date, self._rules)
            cv.create_rectangle(x1, cy, x2, y2, fill=bg, outline=_C_GRID)
            mid_x = (x1 + x2) // 2
            cv.create_text(
                mid_x, cy + hdr_h * 2 // 5, text=_WDAY_JP[date.weekday()], font=("", fs - 1), anchor="center"
            )
            cv.create_text(mid_x, cy + hdr_h * 4 // 5, text=str(date.day), font=("", fs, "bold"), anchor="center")

        # ── スタッフ行 ──
        for row, st in enumerate(page.staff):
            y1 = cy + hdr_h + row * row_h
            y2 = y1 + row_h
            mid_y = (y1 + y2) // 2

            # 名前列
            cv.create_rectangle(cx, y1, cx + name_w, y2, fill=_C_NAME, outline=_C_GRID)
            cv.create_text(cx + 3, mid_y, text=st["name"], font=("", fs), anchor="w")

            # セル列
            for col, date_str in enumerate(page.dates):
                x1 = cx + name_w + col * col_w
                x2 = x1 + col_w
                shift = self._edited.get((st["id"], date_str))
                mark = self._marks.get((st["id"], date_str))
                date = datetime.date.fromisoformat(date_str)

                # 色優先: 手動色 > 曜日色（エラー色なし）
                if mark == "red":
                    fill = _C_MARK_R
                elif mark == "yellow":
                    fill = _C_MARK_Y
                else:
                    fill = _date_bg(date, self._rules)

                cv.create_rectangle(x1, y1, x2, y2, fill=fill, outline=_C_GRID)
                text = _print_cell_text(shift)
                if text:
                    cv.create_text((x1 + x2) // 2, mid_y, text=text, font=("", fs), anchor="center")

    def _update_nav(self) -> None:
        if not self._layout or not self._layout.pages:
            self._prev_btn.configure(state="disabled")
            self._next_btn.configure(state="disabled")
            self._page_lbl.configure(text="")
            return
        total = self._layout.page_count
        cur = self._current_page
        self._prev_btn.configure(state="normal" if cur > 0 else "disabled")
        self._next_btn.configure(state="normal" if cur < total - 1 else "disabled")
        self._page_lbl.configure(text=f"{cur + 1} / {total} ページ")

    # ── イベント ─────────────────────────────────────────────────────────────

    def _on_update_range(self) -> None:
        self._compute_and_draw()

    def _on_prev(self) -> None:
        if self._layout and self._current_page > 0:
            self._current_page -= 1
            self._update_nav()
            self._draw_current_page()

    def _on_next(self) -> None:
        if self._layout and self._current_page < self._layout.page_count - 1:
            self._current_page += 1
            self._update_nav()
            self._draw_current_page()

    def _on_wheel(self, event: tk.Event) -> None:
        delta = -1 if event.delta > 0 else 1
        self._canvas.yview_scroll(delta, "units")

    def _on_print(self) -> None:
        # commit 25 で実装
        show_error(self, "印刷機能はまだ実装されていません。")

    def _on_back(self) -> None:
        from src.ui.screens.period_dashboard import PeriodDashboardScreen

        self.app.show_screen(PeriodDashboardScreen, period_id=self._period_id)

    # ── 公開: printer.py から参照するデータ ──────────────────────────────────

    def get_print_data(self) -> tuple[str, str, list[dict], dict, dict, list[dict]]:
        """印刷に必要なデータを返す（commit 25 の printer.py 用）。

        Returns:
            (from_date_str, to_date_str, staff_list, edited_dict, marks_dict, rules)
        """
        return (
            self._from_var.get().strip(),
            self._to_var.get().strip(),
            self._staff_list,
            self._edited,
            self._marks,
            self._rules,
        )


# ── モジュールヘルパー ────────────────────────────────────────────────────────


def _date_bg(date: datetime.date, rules: list[dict]) -> str:
    """印刷用セル背景色（手動色・エラー色なし）。"""
    if is_sunday(date) or is_holiday(date, rules):
        return _C_SUN
    if is_saturday(date):
        return _C_SAT
    return _C_PAPER


def _print_cell_text(shift: dict | None) -> str:
    """印刷用セルテキスト（§17-5）。

    未編集→"", 勤務なし→"—", エラー→"", 確定→"H:MM-H:MM"
    """
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
