"""シフト編集画面（コミット19）"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from src.db.repositories import (
    custom_day_repo,
    edited_shift_repo,
    mark_repo,
    period_repo,
    settings_repo,
    staff_repo,
    submission_repo,
    wish_shift_repo,
)
from src.ui.app import STATUS_LABELS
from src.ui.components.dialogs import show_error
from src.ui.components.shift_grid import ShiftGrid
from src.utils.logger import get_logger


class ShiftEditScreen(ttk.Frame):
    def __init__(self, master: tk.Misc, app, period_id: int, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.app = app
        self._period_id = period_id
        self._edit_mode = False
        self._grid: ShiftGrid | None = None
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

        self._grid_frame = ttk.Frame(self)
        self._grid_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

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

            staff_list = staff_repo.get_for_period(self._period_id)
            edited_shifts = edited_shift_repo.get_by_period(self._period_id)
            wish_shifts = wish_shift_repo.get_by_period(self._period_id)
            cell_marks = mark_repo.get_by_period(self._period_id)
            submissions = submission_repo.get_by_period(self._period_id)
            settings = settings_repo.get()
            rules = custom_day_repo.get_by_period(0) + custom_day_repo.get_by_period(self._period_id)
        except Exception as e:
            get_logger().error("シフト編集データ読み込み失敗: %s", e, exc_info=True)
            show_error(self, "データの読み込みに失敗しました。")
            return

        if settings is None:
            show_error(self, "設定が取得できませんでした。")
            return

        if self._grid is not None:
            self._grid.destroy()

        self._grid = ShiftGrid(
            self._grid_frame,
            period=period,
            staff_list=staff_list,
            on_cell_select=self._on_cell_select,
        )
        self._grid.pack(fill="both", expand=True)
        self._grid.load(
            edited_shifts=edited_shifts,
            wish_shifts=wish_shifts,
            cell_marks=cell_marks,
            submissions=submissions,
            settings=settings,
            rules=rules,
        )

        self._edit_toggle_btn.configure(state="disabled" if is_archived else "normal")
        self._judge_btn.configure(state="disabled" if is_archived else "normal")
        if is_archived:
            self._edit_mode = False

    # ── コールバック・操作 ──────────────────────────────────────────────────

    def _on_cell_select(self, staff_id: int, work_date: str) -> None:
        # コミット20で右パネルを実装
        pass

    def _on_edit_toggle(self) -> None:
        self._edit_mode = not self._edit_mode
        if self._grid:
            self._grid.set_edit_mode(self._edit_mode)
        self._edit_toggle_btn.configure(text="通常モード" if self._edit_mode else "編集モード")

    def _on_judge_weekly(self) -> None:
        # コミット23で実装
        pass

    def _on_back(self) -> None:
        from src.ui.screens.period_dashboard import PeriodDashboardScreen

        self.app.show_screen(PeriodDashboardScreen, period_id=self._period_id)

    def set_save_status(self, text: str, color: str = "gray") -> None:
        """保存状態表示を更新する（コミット21から使用）。"""
        self._save_lbl.configure(text=text, foreground=color)
