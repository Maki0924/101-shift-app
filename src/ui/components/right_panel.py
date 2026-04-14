"""右パネルコンポーネント（コミット20）

セル選択時に表示される4タブパネル。
- 希望タブ: 希望開始/終了・備考・「希望を反映」ボタン
- 編集タブ: 開始/終了の時刻入力・クリアボタン（コミット21で時刻入力を完成させる）
- メモタブ: 店長メモ・手動色トグル（赤/黄）
- 情報タブ（編集モード時のみ）: 当日/累計人件費・週何回希望・週判定
"""

from __future__ import annotations

import datetime
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

# 情報タブの週判定表示
_JUDGMENT_LABELS = {
    "UNDER": ("未達", "#ef4444"),
    "OVER": ("超過", "#f97316"),
    "OK": ("適正", "#16a34a"),
    "NO_PREF": ("希望なし", "#6b7280"),
}


class RightPanel(ttk.Frame):
    """セル選択時に表示される右パネル。

    on_apply_wish   : (staff_id, work_date) -> None  希望を反映
    on_save_shift   : (staff_id, work_date, start, end) -> None  シフト保存（コミット21）
    on_clear_shift  : (staff_id, work_date) -> None  クリア
    on_save_memo    : (staff_id, work_date, text) -> None  メモ保存
    on_toggle_mark  : (staff_id, work_date, color) -> None  色トグル（"red"|"yellow"）
    """

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_apply_wish: Callable[[int, str], None],
        on_save_shift: Callable[[int, str, float | None, float | None], None],
        on_clear_shift: Callable[[int, str], None],
        on_save_memo: Callable[[int, str, str | None], None],
        on_toggle_mark: Callable[[int, str, str], None],
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self._on_apply_wish = on_apply_wish
        self._on_save_shift = on_save_shift
        self._on_clear_shift = on_clear_shift
        self._on_save_memo = on_save_memo
        self._on_toggle_mark = on_toggle_mark

        self._staff_id: int | None = None
        self._work_date: str | None = None
        self._edit_mode: bool = False

        self._build()

    # ── UI 構築 ──────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # ヘッダー
        hdr = ttk.Frame(self)
        hdr.pack(fill="x", padx=8, pady=(8, 4))
        self._cell_lbl = ttk.Label(hdr, text="", font=("", 10, "bold"))
        self._cell_lbl.pack(side="left")
        ttk.Button(hdr, text="✕", command=self._on_close, width=3).pack(side="right")

        sep = ttk.Separator(self, orient="horizontal")
        sep.pack(fill="x")

        # タブノートブック
        self._nb = ttk.Notebook(self)
        self._nb.pack(fill="both", expand=True, padx=4, pady=4)

        self._tab_wish = ttk.Frame(self._nb)
        self._tab_edit = ttk.Frame(self._nb)
        self._tab_memo = ttk.Frame(self._nb)
        self._tab_info = ttk.Frame(self._nb)

        self._nb.add(self._tab_wish, text="希望")
        self._nb.add(self._tab_edit, text="編集")
        self._nb.add(self._tab_memo, text="メモ")
        self._nb.add(self._tab_info, text="情報")

        self._build_wish_tab()
        self._build_edit_tab()
        self._build_memo_tab()
        self._build_info_tab()

    # ── 希望タブ ─────────────────────────────────────────────────────────────

    def _build_wish_tab(self) -> None:
        f = self._tab_wish
        self._wish_lbl = ttk.Label(f, text="希望なし", wraplength=160, justify="left")
        self._wish_lbl.pack(padx=8, pady=(8, 4), anchor="w")

        self._apply_wish_btn = ttk.Button(f, text="希望を反映", command=self._on_apply_wish_clicked, state="disabled")
        self._apply_wish_btn.pack(padx=8, pady=(0, 8), anchor="w")

    # ── 編集タブ ─────────────────────────────────────────────────────────────

    def _build_edit_tab(self) -> None:
        f = self._tab_edit
        ttk.Label(f, text="開始:").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self._start_var = tk.StringVar()
        self._start_cb = ttk.Combobox(f, textvariable=self._start_var, state="readonly", width=7)
        self._start_cb["values"] = _time_choices()
        self._start_cb.grid(row=0, column=1, padx=4, pady=4)

        ttk.Label(f, text="終了:").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        self._end_var = tk.StringVar()
        self._end_cb = ttk.Combobox(f, textvariable=self._end_var, state="readonly", width=7)
        self._end_cb["values"] = _time_choices()
        self._end_cb.grid(row=1, column=1, padx=4, pady=4)

        btn_frame = ttk.Frame(f)
        btn_frame.grid(row=2, column=0, columnspan=2, padx=8, pady=(4, 8))
        self._save_shift_btn = ttk.Button(btn_frame, text="保存", command=self._on_save_shift_clicked, width=8)
        self._save_shift_btn.pack(side="left", padx=4)
        self._clear_btn = ttk.Button(btn_frame, text="クリア", command=self._on_clear_clicked, width=8)
        self._clear_btn.pack(side="left", padx=4)

    # ── メモタブ ─────────────────────────────────────────────────────────────

    def _build_memo_tab(self) -> None:
        f = self._tab_memo

        # 手動色トグル
        color_frame = ttk.LabelFrame(f, text="手動色", padding=4)
        color_frame.pack(fill="x", padx=8, pady=(8, 4))

        self._mark_red_btn = tk.Button(
            color_frame,
            text="赤",
            bg="#fca5a5",
            width=5,
            relief="raised",
            command=lambda: self._on_toggle_mark_clicked("red"),
        )
        self._mark_red_btn.pack(side="left", padx=4)
        self._mark_yellow_btn = tk.Button(
            color_frame,
            text="黄",
            bg="#fef08a",
            width=5,
            relief="raised",
            command=lambda: self._on_toggle_mark_clicked("yellow"),
        )
        self._mark_yellow_btn.pack(side="left", padx=4)
        self._mark_none_lbl = ttk.Label(color_frame, text="（なし）", foreground="gray")
        self._mark_none_lbl.pack(side="left", padx=4)

        # メモテキスト
        ttk.Label(f, text="店長メモ（500文字）:").pack(padx=8, pady=(4, 0), anchor="w")
        memo_frame = ttk.Frame(f)
        memo_frame.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        self._memo_txt = tk.Text(memo_frame, wrap="word", height=6, width=18)
        vsb = ttk.Scrollbar(memo_frame, orient="vertical", command=self._memo_txt.yview)
        self._memo_txt.configure(yscrollcommand=vsb.set)
        self._memo_txt.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        ttk.Button(f, text="メモを保存", command=self._on_save_memo_clicked).pack(padx=8, pady=(0, 8), anchor="w")
        self._memo_txt.bind("<FocusOut>", lambda _e: self._on_save_memo_clicked())

    # ── 情報タブ ─────────────────────────────────────────────────────────────

    def _build_info_tab(self) -> None:
        f = self._tab_info
        info_vars = [
            ("当日人件費", "_info_day_wage"),
            ("累計人件費", "_info_total_wage"),
            ("週何回希望", "_info_weekly_pref"),
            ("週判定", "_info_weekly_judge"),
        ]
        for row, (label, attr) in enumerate(info_vars):
            ttk.Label(f, text=label + ":").grid(row=row, column=0, sticky="w", padx=8, pady=4)
            var = ttk.Label(f, text="—")
            var.grid(row=row, column=1, sticky="w", padx=4, pady=4)
            setattr(self, attr, var)

    # ── 公開 API ─────────────────────────────────────────────────────────────

    def show_cell(
        self,
        staff: dict,
        work_date: str,
        shift: dict | None,
        wish_shifts: list[dict],
        memo: dict | None,
        mark: dict | None,
        edit_mode: bool,
        day_wage_info: dict | None = None,
    ) -> None:
        """セルが選択されたときにパネルを更新する。"""
        self._staff_id = staff["id"]
        self._work_date = work_date
        self._edit_mode = edit_mode

        date = datetime.date.fromisoformat(work_date)
        self._cell_lbl.configure(text=f"{staff['name']}  {date.month}/{date.day}（{_WDAY_JP[date.weekday()]}）")

        self._update_wish_tab(wish_shifts, work_date)
        self._update_edit_tab(shift, edit_mode)
        self._update_memo_tab(memo, mark)
        self._update_info_tab(day_wage_info, edit_mode)

        # 情報タブは編集モード時のみ
        idx = self._nb.index(self._tab_info)
        self._nb.tab(idx, state="normal" if edit_mode else "hidden")

    def _on_close(self) -> None:
        self.pack_forget()

    # ── タブ更新 ─────────────────────────────────────────────────────────────

    def _update_wish_tab(self, wish_shifts: list[dict], work_date: str) -> None:
        # 当日の希望を抽出
        day_wish = next((w for w in wish_shifts if w["work_date"] == work_date), None)
        if day_wish is None:
            self._wish_lbl.configure(text="希望なし")
            self._apply_wish_btn.configure(state="disabled")
            return

        s, e = day_wish.get("start_time"), day_wish.get("end_time")
        if s is None and e is None:
            wish_text = "勤務不可"
        elif s is not None and e is not None:
            wish_text = f"希望: {_fmt(s)} ～ {_fmt(e)}"
        else:
            wish_text = "希望（データ不正）"
        self._wish_lbl.configure(text=wish_text)
        self._apply_wish_btn.configure(state="normal" if (s is not None and e is not None) else "disabled")

    def _update_edit_tab(self, shift: dict | None, edit_mode: bool) -> None:
        state = "readonly" if edit_mode else "disabled"
        self._start_cb.configure(state=state)
        self._end_cb.configure(state=state)
        self._save_shift_btn.configure(state="normal" if edit_mode else "disabled")
        self._clear_btn.configure(state="normal" if edit_mode else "disabled")

        if shift:
            self._start_var.set(_float_to_str(shift.get("start_time")))
            self._end_var.set(_float_to_str(shift.get("end_time")))
        else:
            self._start_var.set("")
            self._end_var.set("")

    def _update_memo_tab(self, memo: dict | None, mark: dict | None) -> None:
        self._memo_txt.delete("1.0", "end")
        if memo and memo.get("memo_text"):
            self._memo_txt.insert("1.0", memo["memo_text"])

        # 色ボタンの状態（同色再押下で解除できるようにrelief変更）
        current_color = mark["mark_color"] if mark else None
        self._mark_red_btn.configure(relief="sunken" if current_color == "red" else "raised")
        self._mark_yellow_btn.configure(relief="sunken" if current_color == "yellow" else "raised")
        self._mark_none_lbl.configure(foreground="black" if current_color is None else "gray")

    def _update_info_tab(self, day_wage_info: dict | None, edit_mode: bool) -> None:
        if day_wage_info is None or not edit_mode:
            for attr in ("_info_day_wage", "_info_total_wage", "_info_weekly_pref", "_info_weekly_judge"):
                getattr(self, attr).configure(text="—", foreground="black")
            return

        day_w = day_wage_info.get("day_wage", 0)
        total_w = day_wage_info.get("total_wage", 0)
        pref_text = day_wage_info.get("weekly_pref_text", "—")
        judgment = day_wage_info.get("weekly_judgment")  # WeeklyJudgment or None

        self._info_day_wage.configure(text=f"¥{day_w:,}" if day_w is not None else "—")
        self._info_total_wage.configure(text=f"¥{total_w:,}" if total_w is not None else "—")
        self._info_weekly_pref.configure(text=pref_text)

        if judgment is not None:
            j_name = judgment.name  # WeeklyJudgment.UNDER -> "UNDER"
            label, color = _JUDGMENT_LABELS.get(j_name, ("—", "black"))
            self._info_weekly_judge.configure(text=label, foreground=color)
        else:
            self._info_weekly_judge.configure(text="—", foreground="black")

    # ── ボタンハンドラ ──────────────────────────────────────────────────────

    def _on_apply_wish_clicked(self) -> None:
        if self._staff_id and self._work_date:
            self._on_apply_wish(self._staff_id, self._work_date)

    def _on_save_shift_clicked(self) -> None:
        if not (self._staff_id and self._work_date):
            return
        start = _str_to_float(self._start_var.get())
        end = _str_to_float(self._end_var.get())
        self._on_save_shift(self._staff_id, self._work_date, start, end)

    def _on_clear_clicked(self) -> None:
        if self._staff_id and self._work_date:
            self._start_var.set("")
            self._end_var.set("")
            self._on_clear_shift(self._staff_id, self._work_date)

    def _on_save_memo_clicked(self) -> None:
        if not (self._staff_id and self._work_date):
            return
        text = self._memo_txt.get("1.0", "end-1c").strip() or None
        self._on_save_memo(self._staff_id, self._work_date, text)

    def _on_toggle_mark_clicked(self, color: str) -> None:
        if self._staff_id and self._work_date:
            self._on_toggle_mark(self._staff_id, self._work_date, color)


# ── ヘルパー ──────────────────────────────────────────────────────────────────

_WDAY_JP = ("月", "火", "水", "木", "金", "土", "日")


def _time_choices() -> list[str]:
    """0:00 〜 24:00 の 30分刻み選択肢リストを返す。"""
    choices = []
    for h in range(25):
        choices.append(f"{h}:00")
        if h < 24:
            choices.append(f"{h}:30")
    return choices


def _fmt(v: float) -> str:
    h, m = int(v), int(round((v - int(v)) * 60))
    return f"{h}:{m:02d}" if m else str(h)


def _float_to_str(v: float | None) -> str:
    if v is None:
        return ""
    return _fmt(v)


def _str_to_float(s: str) -> float | None:
    s = s.strip()
    if not s:
        return None
    try:
        if ":" in s:
            h, m = s.split(":", 1)
            return int(h) + int(m) / 60
        return float(s)
    except ValueError:
        return None
