"""希望検索画面（コミット26）

指定日・時間帯と重複する希望シフトを持つスタッフを一覧表示する。

検索条件:
  - 日付（YYYY-MM-DD）
  - 時間帯（開始〜終了、H:MM または float）
  - 雇用形態フィルター（全員 / バイト / 社員）
  - 確定シフトフィルター（全員 / なし / あり）

重複判定: max(0, min(wish_end, search_end) - max(wish_start, search_start)) > 0

結果列: スタッフ名 / 希望時間 / メモ / 週希望 / 今週確定数
"""

from __future__ import annotations

import datetime
import tkinter as tk
from tkinter import ttk

from src.db.repositories import (
    edited_shift_repo,
    period_repo,
    staff_repo,
    submission_repo,
    wish_shift_repo,
)
from src.logic.weekly_count import count_confirmed_in_range
from src.ui.components.dialogs import show_error
from src.ui.components.time_selector import str_to_float
from src.utils.logger import get_logger

_EMP_OPTIONS = ("全員", "バイト", "社員")
_CONFIRMED_OPTIONS = ("全員", "なし", "あり")
_EMP_TYPE_MAP = {"バイト": "part_time", "社員": "employee"}

# 結果ツリービュー列定義
_COLUMNS = ("name", "wish_time", "note", "weekly_pref", "confirmed_count")
_COL_HEADINGS = {
    "name": "スタッフ名",
    "wish_time": "希望時間",
    "note": "メモ",
    "weekly_pref": "週希望",
    "confirmed_count": "今週確定",
}
_COL_WIDTHS = {
    "name": 120,
    "wish_time": 100,
    "note": 200,
    "weekly_pref": 90,
    "confirmed_count": 70,
}


class WishSearchScreen(ttk.Frame):
    """希望検索画面。"""

    def __init__(self, master: tk.Misc, app, period_id: int, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.app = app
        self._period_id = period_id
        # データ
        self._period: dict | None = None
        self._staff_map: dict[int, dict] = {}
        self._wish_shifts: list[dict] = []
        self._edited_by_staff: dict[int, list[dict]] = {}
        self._submission_map: dict[int, dict] = {}
        # UI 変数
        self._date_var = tk.StringVar()
        self._start_var = tk.StringVar()
        self._end_var = tk.StringVar()
        self._emp_var = tk.StringVar(value=_EMP_OPTIONS[0])
        self._confirmed_var = tk.StringVar(value=_CONFIRMED_OPTIONS[0])
        self._build()
        self._load()

    # ── UI構築 ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # ── ヘッダーバー ──
        top = ttk.Frame(self)
        top.pack(fill="x", padx=16, pady=(12, 4))
        self._title_lbl = ttk.Label(top, text="希望検索", font=("", 14))
        self._title_lbl.pack(side="left")
        ttk.Button(top, text="戻る", command=self._on_back, width=8).pack(side="right")

        # ── 検索条件 ──
        cond_frame = ttk.LabelFrame(self, text="検索条件", padding=8)
        cond_frame.pack(fill="x", padx=16, pady=(0, 4))

        # 行1: 日付・時間帯
        row1 = ttk.Frame(cond_frame)
        row1.pack(fill="x", pady=(0, 4))
        ttk.Label(row1, text="日付:").pack(side="left")
        ttk.Entry(row1, textvariable=self._date_var, width=12).pack(side="left", padx=(4, 16))
        ttk.Label(row1, text="時間帯:").pack(side="left")
        ttk.Entry(row1, textvariable=self._start_var, width=7).pack(side="left", padx=(4, 2))
        ttk.Label(row1, text="〜").pack(side="left")
        ttk.Entry(row1, textvariable=self._end_var, width=7).pack(side="left", padx=(2, 16))

        # 行2: フィルター・検索ボタン
        row2 = ttk.Frame(cond_frame)
        row2.pack(fill="x")
        ttk.Label(row2, text="雇用形態:").pack(side="left")
        ttk.Combobox(row2, textvariable=self._emp_var, values=_EMP_OPTIONS, state="readonly", width=8).pack(
            side="left", padx=(4, 16)
        )
        ttk.Label(row2, text="確定シフト:").pack(side="left")
        ttk.Combobox(row2, textvariable=self._confirmed_var, values=_CONFIRMED_OPTIONS, state="readonly", width=8).pack(
            side="left", padx=(4, 16)
        )
        ttk.Button(row2, text="検索", command=self._on_search, width=8).pack(side="left")

        # ── 結果カウント ──
        self._count_lbl = ttk.Label(self, text="")
        self._count_lbl.pack(anchor="w", padx=16, pady=(0, 4))

        # ── 結果ツリービュー ──
        tv_frame = ttk.Frame(self)
        tv_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        tv_frame.rowconfigure(0, weight=1)
        tv_frame.columnconfigure(0, weight=1)

        self._tree = ttk.Treeview(tv_frame, columns=_COLUMNS, show="headings", selectmode="browse")
        for col in _COLUMNS:
            self._tree.heading(col, text=_COL_HEADINGS[col])
            self._tree.column(col, width=_COL_WIDTHS[col], minwidth=40)

        vsb = ttk.Scrollbar(tv_frame, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(tv_frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

    # ── データ読み込み ────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            period = period_repo.get_by_id(self._period_id)
        except Exception as e:
            get_logger().error("希望検索: 期間読み込みエラー: %s", e, exc_info=True)
            show_error(self, "期間の読み込みに失敗しました。")
            return
        if period is None:
            show_error(self, "期間が見つかりません。")
            return

        self._period = period
        self._title_lbl.configure(text=f"希望検索 — {period['name']}")

        try:
            staff_list = staff_repo.get_for_period(self._period_id)
            self._staff_map = {s["id"]: s for s in staff_list}
            self._wish_shifts = wish_shift_repo.get_by_period(self._period_id)
            edited_all = edited_shift_repo.get_by_period(self._period_id)
            self._edited_by_staff = {}
            for r in edited_all:
                self._edited_by_staff.setdefault(r["staff_id"], []).append(r)
            subs = submission_repo.get_by_period(self._period_id)
            self._submission_map = {s["id"]: s for s in subs}
        except Exception as e:
            get_logger().error("希望検索: データ読み込みエラー: %s", e, exc_info=True)
            show_error(self, "データの読み込みに失敗しました。")
            return

        # 初期日付: 期間の最初の日
        self._date_var.set(period["start_date"])

    # ── 検索実行 ─────────────────────────────────────────────────────────────

    def _on_search(self) -> None:
        # ── 入力バリデーション ──
        date_str = self._date_var.get().strip()
        try:
            search_date = datetime.date.fromisoformat(date_str)
        except ValueError:
            show_error(self, "日付の形式が不正です（YYYY-MM-DD）。")
            return

        start_str = self._start_var.get().strip()
        end_str = self._end_var.get().strip()
        search_start = str_to_float(start_str) if start_str else None
        search_end = str_to_float(end_str) if end_str else None

        if (start_str and search_start is None) or (end_str and search_end is None):
            show_error(self, "時間帯の形式が不正です（例: 9:00 または 9.0）。")
            return

        emp_filter = _EMP_TYPE_MAP.get(self._emp_var.get())  # None = 全員
        confirmed_filter = self._confirmed_var.get()  # "全員" / "なし" / "あり"

        # ── 当日の希望シフトを絞り込み ──
        day_wishes = [w for w in self._wish_shifts if w["work_date"] == date_str]

        # ── 週範囲（月曜起算、前期間参照なし） ──
        week_start = search_date - datetime.timedelta(days=search_date.weekday())
        week_end = week_start + datetime.timedelta(days=6)

        # スタッフ表示順マップ（get_for_period の返り順）
        staff_order = {sid: idx for idx, sid in enumerate(self._staff_map)}

        # ── フィルタリング＆結果構築（sort key 付き）──
        # raw: (wish_start, staff_order_idx, display_row)
        raw: list[tuple[float, int, tuple]] = []
        seen_staff: set[int] = set()  # 同一スタッフの複数希望は重複表示

        for wish in day_wishes:
            staff_id = wish["staff_id"]
            if staff_id in seen_staff:
                continue
            st = self._staff_map.get(staff_id)
            if st is None:
                continue

            # 雇用形態フィルター
            if emp_filter and st["employment_type"] != emp_filter:
                continue

            # 時間帯重複フィルター
            w_start = wish.get("start_time")
            w_end = wish.get("end_time")
            if search_start is not None and search_end is not None:
                if w_start is None or w_end is None:
                    continue
                overlap = max(0.0, min(w_end, search_end) - max(w_start, search_start))
                if overlap <= 0.0:
                    continue

            # 確定シフトフィルター
            if confirmed_filter != "全員":
                staff_edits = self._edited_by_staff.get(staff_id, [])
                has_confirmed = any(
                    e["work_date"] == date_str and e.get("start_time") is not None and e.get("end_time") is not None
                    for e in staff_edits
                )
                if confirmed_filter == "あり" and not has_confirmed:
                    continue
                if confirmed_filter == "なし" and has_confirmed:
                    continue

            # ── 表示値を計算 ──
            wish_time = _fmt_time_range(w_start, w_end)
            sub = self._submission_map.get(wish.get("submission_id") or -1)
            note = (sub or {}).get("note_text") or ""
            weekly_pref = _fmt_weekly_pref(
                (sub or {}).get("weekly_pref_min"),
                (sub or {}).get("weekly_pref_max"),
            )
            confirmed_count = count_confirmed_in_range(
                self._edited_by_staff.get(staff_id, []),
                week_start,
                week_end,
            )

            sort_start = w_start if w_start is not None else float("inf")
            sort_order = staff_order.get(staff_id, len(self._staff_map))
            raw.append((sort_start, sort_order, (st["name"], wish_time, note, weekly_pref, str(confirmed_count))))
            seen_staff.add(staff_id)

        # 希望開始が早い順 → スタッフ表示順
        raw.sort(key=lambda x: (x[0], x[1]))

        # ── Treeview 更新 ──
        for item in self._tree.get_children():
            self._tree.delete(item)
        for _, _, row in raw:
            self._tree.insert("", "end", values=row)

        self._count_lbl.configure(text=f"検索結果: {len(raw)} 件")

    # ── 画面遷移 ────────────────────────────────────────────────────────────

    def _on_back(self) -> None:
        from src.ui.screens.period_dashboard import PeriodDashboardScreen

        self.app.show_screen(PeriodDashboardScreen, period_id=self._period_id)


# ── モジュールヘルパー ────────────────────────────────────────────────────────


def _fmt_time_range(start: float | None, end: float | None) -> str:
    """希望時間を "H:MM-H:MM" 形式で返す。"""
    if start is None or end is None:
        return "—"
    return f"{_fmt(start)}-{_fmt(end)}"


def _fmt_weekly_pref(pref_min: int | None, pref_max: int | None) -> str:
    """週希望テキストを返す。"""
    if pref_min is None and pref_max is None:
        return "—"
    if pref_min is not None and pref_max is not None:
        if pref_min == pref_max:
            return f"週{pref_min}回"
        return f"週{pref_min}〜{pref_max}回"
    if pref_min is not None:
        return f"週{pref_min}回以上"
    return f"週{pref_max}回以下"


def _fmt(v: float) -> str:
    h, m = int(v), int(round((v - int(v)) * 60))
    return f"{h}:{m:02d}" if m else str(h)
