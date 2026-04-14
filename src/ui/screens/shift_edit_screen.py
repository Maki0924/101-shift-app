"""シフト編集画面（コミット19〜23）

コミット23追加:
- 情報タブ: 当日/累計人件費・週何回希望・週判定をセル選択時にリアルタイム計算
- 週回数判定ボタン: 全スタッフのスナップショット判定でグリッド名セルに色付け（再押下で解除）
- 画面遷移時に判定色・ボタン状態をリセット
"""

from __future__ import annotations

import datetime
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
from src.logic.bulk_apply import bulk_apply
from src.logic.undo_redo import UndoEntry, UndoRedoStack
from src.logic.wage_calc import calc_wage, is_calculable
from src.logic.weekly_count import WeeklyJudgment, judge_total
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
        self._undo_stack = UndoRedoStack()
        self._weekly_judge_active = False  # 判定色表示中かどうか
        self._submissions: list[dict] = []
        self._prev_period_end: datetime.date | None = None
        self._prev_edited_by_staff: dict[int, list[dict]] = {}
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

        self._redo_btn = ttk.Button(top, text="Redo", command=self._on_redo, width=6, state="disabled")
        self._redo_btn.pack(side="right", padx=(0, 4))

        self._undo_btn = ttk.Button(top, text="Undo", command=self._on_undo, width=6, state="disabled")
        self._undo_btn.pack(side="right", padx=(0, 4))

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

        # キーバインド
        self.bind_all("<Control-z>", lambda _e: self._on_undo())
        self.bind_all("<Control-y>", lambda _e: self._on_redo())

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
            self._submissions = submissions
            self._settings = settings_repo.get()
            self._rules = custom_day_repo.get_by_period(0) + custom_day_repo.get_by_period(self._period_id)

            # 前期間の編集シフトを読み込む（週回数判定・情報タブ用）
            all_periods = period_repo.get_all()
            prev = None
            for p in all_periods:
                if p["id"] == self._period_id:
                    continue
                if p["end_date"] < period["start_date"]:
                    if prev is None or p["end_date"] > prev["end_date"]:
                        prev = p
            if prev is not None:
                self._prev_period_end = datetime.date.fromisoformat(prev["end_date"])
                prev_shifts = edited_shift_repo.get_by_period(prev["id"])
                self._prev_edited_by_staff = {}
                for sh in prev_shifts:
                    self._prev_edited_by_staff.setdefault(sh["staff_id"], []).append(sh)
            else:
                self._prev_period_end = None
                self._prev_edited_by_staff = {}
        except Exception as e:
            get_logger().error("シフト編集データ読み込み失敗: %s", e, exc_info=True)
            show_error(self, "データの読み込みに失敗しました。")
            return

        if self._settings is None:
            show_error(self, "設定が取得できませんでした。")
            return

        self._undo_stack.reset()
        self._update_undo_redo_buttons()

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

        day_wage_info = None
        if self._edit_mode and self._settings and self._period:
            day_wage_info = self._compute_info_tab(staff, work_date, shift)

        self._right_panel.show_cell(
            staff=staff,
            work_date=work_date,
            shift=shift,
            wish_shifts=wish_shifts,
            memo=memo,
            mark=mark_rec,
            edit_mode=self._edit_mode,
            day_wage_info=day_wage_info,
        )
        self._right_panel.grid(row=0, column=1, sticky="ns", padx=(4, 0))

    # ── 右パネルコールバック ─────────────────────────────────────────────────

    def _on_apply_wish(self, staff_id: int, work_date: str) -> None:
        if self._grid is None:
            return
        wish_shifts = self._grid.get_wish_shifts(staff_id)
        day_wish = next((w for w in wish_shifts if w["work_date"] == work_date), None)
        if day_wish is None:
            return

        before = self._grid.get_shift(staff_id, work_date)
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

        self._undo_stack.push(
            UndoEntry(
                kind="shift",
                staff_id=staff_id,
                period_id=self._period_id,
                work_date=work_date,
                before=before,
                after=shift,
            )
        )
        self._update_undo_redo_buttons()
        self.set_save_status("保存済み", "green")
        mark_rec = mark_repo.get_one(self._period_id, staff_id, work_date)
        self._grid.refresh_cell(staff_id, work_date, shift, mark_rec)
        self._on_cell_select(staff_id, work_date)

    def _on_save_shift(self, staff_id: int, work_date: str, start: float | None, end: float | None) -> None:
        before = self._grid.get_shift(staff_id, work_date) if self._grid else None
        try:
            shift = edited_shift_repo.upsert(self._period_id, staff_id, work_date, start, end)
        except Exception as e:
            get_logger().error("シフト保存失敗: %s", e, exc_info=True)
            show_error(self, "保存に失敗しました。")
            self.set_save_status("保存失敗", "red")
            return

        self._undo_stack.push(
            UndoEntry(
                kind="shift",
                staff_id=staff_id,
                period_id=self._period_id,
                work_date=work_date,
                before=before,
                after=shift,
            )
        )
        self._update_undo_redo_buttons()
        self.set_save_status("保存済み", "green")
        mark_rec = mark_repo.get_one(self._period_id, staff_id, work_date)
        if self._grid:
            self._grid.refresh_cell(staff_id, work_date, shift, mark_rec)
        self._on_cell_select(staff_id, work_date)

    def _on_clear_shift(self, staff_id: int, work_date: str) -> None:
        before = self._grid.get_shift(staff_id, work_date) if self._grid else None
        try:
            edited_shift_repo.clear(self._period_id, staff_id, work_date)
            shift = edited_shift_repo.get_one(self._period_id, staff_id, work_date)
        except Exception as e:
            get_logger().error("クリア失敗: %s", e, exc_info=True)
            show_error(self, "クリアに失敗しました。")
            self.set_save_status("保存失敗", "red")
            return

        self._undo_stack.push(
            UndoEntry(
                kind="shift",
                staff_id=staff_id,
                period_id=self._period_id,
                work_date=work_date,
                before=before,
                after=shift,
            )
        )
        self._update_undo_redo_buttons()
        self.set_save_status("保存済み", "green")
        mark_rec = mark_repo.get_one(self._period_id, staff_id, work_date)
        if self._grid:
            self._grid.refresh_cell(staff_id, work_date, shift, mark_rec)
        self._on_cell_select(staff_id, work_date)

    def _on_save_memo(self, staff_id: int, work_date: str, text: str | None) -> None:
        before_rec = None
        try:
            before_rec = memo_repo.get_one(self._period_id, staff_id, work_date)
            after_rec = memo_repo.upsert(self._period_id, staff_id, work_date, text)
        except Exception as e:
            get_logger().error("メモ保存失敗: %s", e, exc_info=True)
            return
        before_text = before_rec["memo_text"] if before_rec else None
        if before_text != text:
            self._undo_stack.push(
                UndoEntry(
                    kind="memo",
                    staff_id=staff_id,
                    period_id=self._period_id,
                    work_date=work_date,
                    before=before_rec,
                    after=after_rec,
                )
            )
            self._update_undo_redo_buttons()

    def _on_toggle_mark(self, staff_id: int, work_date: str, color: str) -> None:
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

        self._undo_stack.push(
            UndoEntry(
                kind="mark",
                staff_id=staff_id,
                period_id=self._period_id,
                work_date=work_date,
                before=existing,
                after=mark_rec,
            )
        )
        self._update_undo_redo_buttons()
        shift = self._grid.get_shift(staff_id, work_date) if self._grid else None
        if self._grid:
            self._grid.refresh_cell(staff_id, work_date, shift, mark_rec)
        self._on_cell_select(staff_id, work_date)

    # ── 一括反映 ─────────────────────────────────────────────────────────────

    def bulk_apply_staff(self, staff_id: int, mode: str = "all") -> None:
        """スタッフの希望シフトを一括反映する（外部から呼び出し可）。"""
        if self._grid is None:
            return
        # Undo用に反映前のスナップショット
        before_shifts = edited_shift_repo.get_by_period_and_staff(self._period_id, staff_id)
        try:
            after_shifts = bulk_apply(self._period_id, staff_id, mode)
        except Exception as e:
            get_logger().error("一括反映失敗: %s", e, exc_info=True)
            show_error(self, "一括反映に失敗しました。")
            return

        self._undo_stack.push(
            UndoEntry(
                kind="bulk",
                staff_id=staff_id,
                period_id=self._period_id,
                work_date=None,
                before=before_shifts,
                after=after_shifts,
            )
        )
        self._update_undo_redo_buttons()
        self.set_save_status("保存済み", "green")
        # グリッドを再ロード（一括変更は差分更新より全体再描画が確実）
        self._reload_grid()

    def _reload_grid(self) -> None:
        """グリッドデータのみ再取得して再描画する。"""
        if self._grid is None or self._settings is None:
            return
        try:
            edited_shifts = edited_shift_repo.get_by_period(self._period_id)
            wish_shifts = wish_shift_repo.get_by_period(self._period_id)
            cell_marks = mark_repo.get_by_period(self._period_id)
            submissions = submission_repo.get_by_period(self._period_id)
        except Exception as e:
            get_logger().error("グリッド再読み込み失敗: %s", e, exc_info=True)
            return
        self._grid.load(
            edited_shifts=edited_shifts,
            wish_shifts=wish_shifts,
            cell_marks=cell_marks,
            submissions=submissions,
            settings=self._settings,
            rules=self._rules,
        )

    # ── Undo/Redo ────────────────────────────────────────────────────────────

    def _on_undo(self) -> None:
        entry = self._undo_stack.pop_undo()
        if entry is None:
            return
        self._apply_undo_redo(entry, forward=False)
        self._update_undo_redo_buttons()

    def _on_redo(self) -> None:
        entry = self._undo_stack.pop_redo()
        if entry is None:
            return
        self._apply_undo_redo(entry, forward=True)
        self._update_undo_redo_buttons()

    def _apply_undo_redo(self, entry: UndoEntry, forward: bool) -> None:
        """エントリを適用する（forward=True は Redo、False は Undo）。"""
        target = entry.after if forward else entry.before
        try:
            if entry.kind == "shift":
                if target is None:
                    # 「未編集」状態に戻す場合（レコードを削除する手段がないため NULL/NULL で代用）
                    edited_shift_repo.clear(entry.period_id, entry.staff_id, entry.work_date)
                    shift = edited_shift_repo.get_one(entry.period_id, entry.staff_id, entry.work_date)
                else:
                    shift = edited_shift_repo.upsert(
                        entry.period_id,
                        entry.staff_id,
                        entry.work_date,
                        target.get("start_time"),
                        target.get("end_time"),
                    )
                mark_rec = mark_repo.get_one(entry.period_id, entry.staff_id, entry.work_date)
                if self._grid:
                    self._grid.refresh_cell(entry.staff_id, entry.work_date, shift, mark_rec)

            elif entry.kind == "mark":
                if target is None:
                    mark_repo.delete(entry.period_id, entry.staff_id, entry.work_date)
                    mark_rec = None
                else:
                    mark_rec = mark_repo.upsert(entry.period_id, entry.staff_id, entry.work_date, target["mark_color"])
                shift = self._grid.get_shift(entry.staff_id, entry.work_date) if self._grid else None
                if self._grid:
                    self._grid.refresh_cell(entry.staff_id, entry.work_date, shift, mark_rec)

            elif entry.kind == "memo":
                text = target["memo_text"] if target else None
                memo_repo.upsert(entry.period_id, entry.staff_id, entry.work_date, text)

            elif entry.kind == "bulk":
                shifts = target or []
                edited_shift_repo.upsert_bulk(entry.period_id, entry.staff_id, shifts)
                self._reload_grid()
                return

        except Exception as e:
            get_logger().error("Undo/Redo 適用失敗: %s", e, exc_info=True)
            show_error(self, "操作の取り消しに失敗しました。")
            return

        self.set_save_status("保存済み", "green")
        # 右パネルが該当セルを表示中なら更新
        if self._grid and self._grid.selected_cell == (entry.staff_id, entry.work_date):
            self._on_cell_select(entry.staff_id, entry.work_date)

    def _update_undo_redo_buttons(self) -> None:
        self._undo_btn.configure(state="normal" if self._undo_stack.can_undo() else "disabled")
        self._redo_btn.configure(state="normal" if self._undo_stack.can_redo() else "disabled")

    # ── 操作ボタン ───────────────────────────────────────────────────────────

    def _on_edit_toggle(self) -> None:
        self._edit_mode = not self._edit_mode
        if self._grid:
            self._grid.set_edit_mode(self._edit_mode)
        self._edit_toggle_btn.configure(text="通常モード" if self._edit_mode else "編集モード")
        if self._grid and self._grid.selected_cell:
            self._on_cell_select(*self._grid.selected_cell)

    def _on_judge_weekly(self) -> None:
        """週回数判定ボタン：押下で色付け、再押下で解除。"""
        if self._weekly_judge_active:
            self._weekly_judge_active = False
            self._judge_btn.configure(text="週回数判定")
            if self._grid:
                self._grid.set_weekly_colors(None)
            return

        if self._period is None or self._grid is None:
            return

        try:
            period_start = datetime.date.fromisoformat(self._period["start_date"])
            period_end = datetime.date.fromisoformat(self._period["end_date"])

            # 採用済み回答マップ {staff_id: submission}
            applied_map: dict[int, dict] = {}
            for sub in self._submissions:
                if sub["apply_status"] == "applied" and sub["staff_id"] is not None:
                    applied_map[sub["staff_id"]] = sub

            colors: dict[int, str] = {}
            for st in self._staff_list:
                sid = st["id"]
                sub = applied_map.get(sid)
                if sub is None:
                    continue  # NO_PREF → 色なし

                pref_min = sub.get("weekly_pref_min")
                pref_max = sub.get("weekly_pref_max")

                # 現期間のシフトをグリッドキャッシュから収集
                current_shifts = self._collect_staff_shifts(sid, period_start, period_end)

                result = judge_total(
                    period_start,
                    period_end,
                    pref_min,
                    pref_max,
                    current_shifts,
                    self._prev_edited_by_staff.get(sid),
                    self._prev_period_end,
                )

                if result == WeeklyJudgment.UNDER:
                    colors[sid] = "red"
                elif result == WeeklyJudgment.OVER:
                    colors[sid] = "orange"
                elif result == WeeklyJudgment.OK:
                    colors[sid] = "green"
                # NO_PREF → 色なし

            self._grid.set_weekly_colors(colors)
            self._weekly_judge_active = True
            self._judge_btn.configure(text="判定解除")

        except Exception as e:
            get_logger().error("週回数判定失敗: %s", e, exc_info=True)
            show_error(self, "週回数判定に失敗しました。")

    def _collect_staff_shifts(
        self,
        staff_id: int,
        period_start: datetime.date,
        period_end: datetime.date,
    ) -> list[dict]:
        """グリッドキャッシュからスタッフの編集シフトリストを収集する。"""
        shifts = []
        cur = period_start
        while cur <= period_end:
            sh = self._grid.get_shift(staff_id, cur.isoformat()) if self._grid else None
            if sh is not None:
                shifts.append(sh)
            cur += datetime.timedelta(days=1)
        return shifts

    def _compute_info_tab(self, staff: dict, work_date: str, shift: dict | None) -> dict:
        """情報タブ用データ（当日/累計人件費・週何回希望・週判定）を計算する。"""
        s = self._settings
        date = datetime.date.fromisoformat(work_date)
        period_start = datetime.date.fromisoformat(self._period["start_date"])
        period_end = datetime.date.fromisoformat(self._period["end_date"])

        # 当日人件費
        day_wage = 0
        if shift and is_calculable(shift.get("start_time"), shift.get("end_time")):
            try:
                day_wage = calc_wage(
                    shift["start_time"],
                    shift["end_time"],
                    staff["hourly_wage"],
                    date,
                    s["saturday_bonus"],
                    s["sunday_bonus"],
                    s["holiday_bonus"],
                    self._rules,
                )
            except Exception as e:
                get_logger().warning("当日人件費計算失敗（除外）: %s", e)

        # 累計人件費（グリッドキャッシュから全日分を合計）
        total_wage = 0
        cur = period_start
        while cur <= period_end:
            sh = self._grid.get_shift(staff["id"], cur.isoformat()) if self._grid else None
            if sh and is_calculable(sh.get("start_time"), sh.get("end_time")):
                try:
                    total_wage += calc_wage(
                        sh["start_time"],
                        sh["end_time"],
                        staff["hourly_wage"],
                        cur,
                        s["saturday_bonus"],
                        s["sunday_bonus"],
                        s["holiday_bonus"],
                        self._rules,
                    )
                except Exception as e:
                    get_logger().warning("累計人件費計算失敗（除外）: %s", e)
            cur += datetime.timedelta(days=1)

        # 採用済み回答から週何回希望テキストと判定を取得
        weekly_pref_text = "—"
        judgment = None
        applied_sub = next(
            (sub for sub in self._submissions if sub["staff_id"] == staff["id"] and sub["apply_status"] == "applied"),
            None,
        )
        if applied_sub:
            pref_min = applied_sub.get("weekly_pref_min")
            pref_max = applied_sub.get("weekly_pref_max")

            if pref_min is not None and pref_max is not None:
                weekly_pref_text = f"{pref_min}回" if pref_min == pref_max else f"{pref_min}〜{pref_max}回"
            elif pref_min is not None:
                weekly_pref_text = f"{pref_min}回以上"
            elif pref_max is not None:
                weekly_pref_text = f"{pref_max}回以下"

            current_shifts = self._collect_staff_shifts(staff["id"], period_start, period_end)
            try:
                judgment = judge_total(
                    period_start,
                    period_end,
                    pref_min,
                    pref_max,
                    current_shifts,
                    self._prev_edited_by_staff.get(staff["id"]),
                    self._prev_period_end,
                )
            except Exception as e:
                get_logger().warning("週判定計算失敗: %s", e)

        return {
            "day_wage": day_wage,
            "total_wage": total_wage,
            "weekly_pref_text": weekly_pref_text,
            "weekly_judgment": judgment,
        }

    def _on_back(self) -> None:
        # 画面遷移時に判定色・ボタン状態・キーバインドをリセット
        self.unbind_all("<Control-z>")
        self.unbind_all("<Control-y>")
        self._weekly_judge_active = False
        self._judge_btn.configure(text="週回数判定")
        if self._grid:
            self._grid.set_weekly_colors(None)
        from src.ui.screens.period_dashboard import PeriodDashboardScreen

        self.app.show_screen(PeriodDashboardScreen, period_id=self._period_id)

    def set_save_status(self, text: str, color: str = "gray") -> None:
        self._save_lbl.configure(text=text, foreground=color)
