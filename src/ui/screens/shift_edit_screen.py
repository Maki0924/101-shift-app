"""シフト編集画面（コミット19〜23）"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from src.db.repositories import (
    custom_day_repo,
    edited_shift_repo,
    mark_repo,
    memo_repo,
    period_repo,
    settings_repo,
    staff_repo,
    submission_repo,
    wish_shift_repo,
)
from src.ui.app import STATUS_LABELS
from src.ui.components.dialogs import show_error
from src.ui.components.right_panel import RightPanel
from src.ui.components.shift_grid import ShiftGrid
from src.utils.logger import get_logger


class ShiftEditScreen(ttk.Frame):
    def __init__(self, master: tk.Misc, app, period_id: int, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.app = app
        self._period_id = period_id
        self._edit_mode = False
        self._grid: ShiftGrid | None = None
        self._period: dict | None = None
        self._staff_list: list[dict] = []
        self._settings: dict | None = None
        self._rules: list[dict] = []
        self._build()
        self._load()

    # ── UI構築 ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=16, pady=(12, 4))

        self._title_lbl = ttk.Label(top, text="シフト編集", font=("", 14))
        self._title_lbl.pack(side="left")

        ttk.Button(top, text="戻る", command=self._on_back, width=8).pack(side="right")

        self._judge_btn = ttk.Button(
            top,
            text="週回数判定",
            command=self._on_judge_weekly,
            width=12,
            state="disabled",
        )
        self._judge_btn.pack(side="right", padx=(0, 6))

        self._edit_toggle_btn = ttk.Button(
            top,
            text="編集モード",
            command=self._on_edit_toggle,
            width=12,
            state="disabled",
        )
        self._edit_toggle_btn.pack(side="right", padx=(0, 6))

        self._save_lbl = ttk.Label(top, text="", foreground="gray")
        self._save_lbl.pack(side="right", padx=(0, 12))

        # グリッド + 右パネル
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=0)
        body.rowconfigure(0, weight=1)

        self._grid_frame = ttk.Frame(body)
        self._grid_frame.grid(row=0, column=0, sticky="nsew")

        self._right_panel = RightPanel(
            body,
            on_apply_wish=self._on_apply_wish,
            on_save_shift=self._on_save_shift,
            on_clear_shift=self._on_clear_shift,
            on_save_memo=self._on_save_memo,
            on_toggle_mark=self._on_toggle_mark,
            width=200,
        )
        # 初期は非表示
        # self._right_panel は show_cell 後に grid で表示する

    # ── データ読み込み ───────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            period = period_repo.get_by_id(self._period_id)
            if period is None:
                show_error(self, "期間が見つかりません。")
                return

            self._period = period
            is_archived = period["status"] == "archived"
            self._title_lbl.configure(
                text=f"シフト編集  —  {period['name']} [{STATUS_LABELS.get(period['status'], period['status'])}]"
            )

            self._staff_list = staff_repo.get_for_period(self._period_id)
            edited_shifts = edited_shift_repo.get_by_period(self._period_id)
            wish_shifts = wish_shift_repo.get_by_period(self._period_id)
            cell_marks = mark_repo.get_by_period(self._period_id)
            submissions = submission_repo.get_by_period(self._period_id)
            self._settings = settings_repo.get()
            self._rules = custom_day_repo.get_by_period(0) + custom_day_repo.get_by_period(self._period_id)
        except Exception as e:
            get_logger().error("シフト編集データ読み込み失敗: %s", e, exc_info=True)
            show_error(self, "データの読み込みに失敗しました。")
            return

        if self._settings is None:
            show_error(self, "設定が取得できませんでした。")
            return

        if self._grid is not None:
            self._grid.destroy()

        self._grid = ShiftGrid(
            self._grid_frame,
            period=period,
            staff_list=self._staff_list,
            on_cell_select=self._on_cell_select,
        )
        self._grid.pack(fill="both", expand=True)
        self._grid.load(
            edited_shifts=edited_shifts,
            wish_shifts=wish_shifts,
            cell_marks=cell_marks,
            submissions=submissions,
            settings=self._settings,
            rules=self._rules,
        )

        self._edit_toggle_btn.configure(state="disabled" if is_archived else "normal")
        self._judge_btn.configure(state="disabled" if is_archived else "normal")
        if is_archived:
            self._edit_mode = False

    # ── セル選択 ─────────────────────────────────────────────────────────────

    def _on_cell_select(self, staff_id: int, work_date: str) -> None:
        if self._grid is None:
            return
        staff = next((s for s in self._staff_list if s["id"] == staff_id), None)
        if staff is None:
            return

        shift = self._grid.get_shift(staff_id, work_date)
        wish_shifts = self._grid.get_wish_shifts(staff_id)

        try:
            memo = memo_repo.get_one(self._period_id, staff_id, work_date)
            mark_rec = mark_repo.get_one(self._period_id, staff_id, work_date)
        except Exception as e:
            get_logger().error("メモ/マーク読み込み失敗: %s", e, exc_info=True)
            memo, mark_rec = None, None

        self._right_panel.show_cell(
            staff=staff,
            work_date=work_date,
            shift=shift,
            wish_shifts=wish_shifts,
            memo=memo,
            mark=mark_rec,
            edit_mode=self._edit_mode,
        )
        # 右パネルを表示
        self._right_panel.grid(row=0, column=1, sticky="ns", padx=(4, 0))

    # ── 右パネルコールバック ─────────────────────────────────────────────────

    def _on_apply_wish(self, staff_id: int, work_date: str) -> None:
        """希望シフトを編集シフトに反映する。"""
        if self._grid is None:
            return
        wish_shifts = self._grid.get_wish_shifts(staff_id)
        day_wish = next((w for w in wish_shifts if w["work_date"] == work_date), None)
        if day_wish is None:
            return
        try:
            shift = edited_shift_repo.upsert(
                self._period_id,
                staff_id,
                work_date,
                day_wish["start_time"],
                day_wish["end_time"],
            )
        except Exception as e:
            get_logger().error("希望反映失敗: %s", e, exc_info=True)
            show_error(self, "希望の反映に失敗しました。")
            return
        self.set_save_status("保存済み", "green")
        mark_rec = mark_repo.get_one(self._period_id, staff_id, work_date)
        self._grid.refresh_cell(staff_id, work_date, shift, mark_rec)
        self._on_cell_select(staff_id, work_date)

    def _on_save_shift(self, staff_id: int, work_date: str, start: float | None, end: float | None) -> None:
        """編集タブからのシフト保存（コミット21で time_selector に置き換え）。"""
        try:
            shift = edited_shift_repo.upsert(self._period_id, staff_id, work_date, start, end)
        except Exception as e:
            get_logger().error("シフト保存失敗: %s", e, exc_info=True)
            show_error(self, "保存に失敗しました。")
            self.set_save_status("保存失敗", "red")
            return
        self.set_save_status("保存済み", "green")
        mark_rec = mark_repo.get_one(self._period_id, staff_id, work_date)
        self._grid.refresh_cell(staff_id, work_date, shift, mark_rec)
        self._on_cell_select(staff_id, work_date)

    def _on_clear_shift(self, staff_id: int, work_date: str) -> None:
        """勤務なし（NULL/NULL）に設定する。"""
        try:
            edited_shift_repo.clear(self._period_id, staff_id, work_date)
            shift = edited_shift_repo.get_one(self._period_id, staff_id, work_date)
        except Exception as e:
            get_logger().error("クリア失敗: %s", e, exc_info=True)
            show_error(self, "クリアに失敗しました。")
            self.set_save_status("保存失敗", "red")
            return
        self.set_save_status("保存済み", "green")
        mark_rec = mark_repo.get_one(self._period_id, staff_id, work_date)
        self._grid.refresh_cell(staff_id, work_date, shift, mark_rec)
        self._on_cell_select(staff_id, work_date)

    def _on_save_memo(self, staff_id: int, work_date: str, text: str | None) -> None:
        try:
            memo_repo.upsert(self._period_id, staff_id, work_date, text)
        except Exception as e:
            get_logger().error("メモ保存失敗: %s", e, exc_info=True)

    def _on_toggle_mark(self, staff_id: int, work_date: str, color: str) -> None:
        """手動色をトグルする（同色再押下で解除）。"""
        try:
            existing = mark_repo.get_one(self._period_id, staff_id, work_date)
            if existing and existing["mark_color"] == color:
                mark_repo.delete(self._period_id, staff_id, work_date)
                mark_rec = None
            else:
                mark_rec = mark_repo.upsert(self._period_id, staff_id, work_date, color)
        except Exception as e:
            get_logger().error("色付け失敗: %s", e, exc_info=True)
            show_error(self, "色付けの保存に失敗しました。")
            return
        shift = self._grid.get_shift(staff_id, work_date) if self._grid else None
        if self._grid:
            self._grid.refresh_cell(staff_id, work_date, shift, mark_rec)
        self._on_cell_select(staff_id, work_date)

    # ── 操作ボタン ───────────────────────────────────────────────────────────

    def _on_edit_toggle(self) -> None:
        self._edit_mode = not self._edit_mode
        if self._grid:
            self._grid.set_edit_mode(self._edit_mode)
        self._edit_toggle_btn.configure(text="通常モード" if self._edit_mode else "編集モード")
        # 右パネルが表示中ならセル再選択で情報タブ表示を更新
        if self._grid and self._grid.selected_cell:
            self._on_cell_select(*self._grid.selected_cell)

    def _on_judge_weekly(self) -> None:
        # コミット23で実装
        pass

    def _on_back(self) -> None:
        from src.ui.screens.period_dashboard import PeriodDashboardScreen

        self.app.show_screen(PeriodDashboardScreen, period_id=self._period_id)

    def set_save_status(self, text: str, color: str = "gray") -> None:
        self._save_lbl.configure(text=text, foreground=color)
