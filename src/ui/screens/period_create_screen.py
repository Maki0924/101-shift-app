"""新規作成・期間編集画面

期間名 / 開始日 / 終了日 / 提出期限を入力して期間を作成・編集する。
"""

import datetime
import tkinter as tk
from tkinter import ttk

from src.db.repositories import period_repo
from src.ui.components.dialogs import show_error
from src.utils.logger import get_logger


def _default_dates(today: datetime.date) -> tuple[str, str, str]:
    """今日の日付からデフォルトの (start_date, end_date, submission_deadline) を返す。

    デフォルト期間: 翌月21日 〜 翌々月20日、提出期限: 翌々月10日
    """
    # 翌月を計算
    if today.month == 12:
        next1_year, next1_month = today.year + 1, 1
    else:
        next1_year, next1_month = today.year, today.month + 1

    # 翌々月を計算
    if next1_month == 12:
        next2_year, next2_month = next1_year + 1, 1
    else:
        next2_year, next2_month = next1_year, next1_month + 1

    start = datetime.date(next1_year, next1_month, 21)
    end = datetime.date(next2_year, next2_month, 20)
    deadline = datetime.date(next2_year, next2_month, 10)
    return start.isoformat(), end.isoformat(), deadline.isoformat()


def _deadline_day_warning(deadline_str: str) -> bool:
    """提出期限の日付部分が10日以外なら True を返す（警告表示の判定用）。"""
    try:
        return datetime.date.fromisoformat(deadline_str).day != 10
    except ValueError:
        return False


def _parse_date(s: str) -> datetime.date | None:
    """YYYY-MM-DD 文字列を date に変換する。不正なら None。"""
    try:
        return datetime.date.fromisoformat(s.strip())
    except ValueError:
        return None


class PeriodCreateScreen(ttk.Frame):
    """新規作成モード（period=None）と編集モード（period=dict）を共用する。"""

    def __init__(self, master: tk.Misc, app, period: dict | None = None, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.app = app
        self._period = period  # None = 新規作成、dict = 編集
        self._build()
        self._fill_defaults()

    def _build(self) -> None:
        is_edit = self._period is not None
        title = "期間を編集" if is_edit else "新規作成"
        ttk.Label(self, text=title, font=("", 16)).pack(pady=(20, 12))

        form = ttk.Frame(self)
        form.pack(padx=40)

        labels = ["期間名", "開始日 (YYYY-MM-DD)", "終了日 (YYYY-MM-DD)", "提出期限 (YYYY-MM-DD)"]
        self._entries: dict[str, ttk.Entry] = {}
        keys = ["name", "start_date", "end_date", "submission_deadline"]

        for row, (lbl, key) in enumerate(zip(labels, keys, strict=True)):
            ttk.Label(form, text=lbl, anchor="e", width=22).grid(row=row, column=0, pady=6, sticky="e")
            entry = ttk.Entry(form, width=24)
            entry.grid(row=row, column=1, pady=6, padx=(8, 0), sticky="w")
            self._entries[key] = entry

        # 提出期限の変更で警告を動的更新
        self._entries["submission_deadline"].bind("<FocusOut>", self._on_deadline_change)

        # 警告ラベル（提出期限が10日以外の場合）
        self._warn_label = ttk.Label(self, text="", foreground="orange")
        self._warn_label.pack(pady=(0, 4))

        # ボタン行
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=12)
        ttk.Button(btn_frame, text="保存", command=self._on_save, width=12).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="キャンセル", command=self._on_cancel, width=12).pack(side="left", padx=6)

    def _fill_defaults(self) -> None:
        if self._period is not None:
            # 編集モード: 既存値を埋める
            self._entries["name"].insert(0, self._period["name"])
            self._entries["start_date"].insert(0, self._period["start_date"])
            self._entries["end_date"].insert(0, self._period["end_date"])
            self._entries["submission_deadline"].insert(0, self._period["submission_deadline"])
        else:
            # 新規作成モード: デフォルト日付を補完
            start, end, deadline = _default_dates(datetime.date.today())
            self._entries["start_date"].insert(0, start)
            self._entries["end_date"].insert(0, end)
            self._entries["submission_deadline"].insert(0, deadline)
        self._update_deadline_warning()

    def _on_deadline_change(self, _event=None) -> None:
        self._update_deadline_warning()

    def _update_deadline_warning(self) -> None:
        dl = self._entries["submission_deadline"].get().strip()
        if dl and _deadline_day_warning(dl):
            self._warn_label.configure(text="提出期限が10日以外です（このまま保存も可能）")
        else:
            self._warn_label.configure(text="")

    def _on_save(self) -> None:
        name = self._entries["name"].get().strip()
        start_str = self._entries["start_date"].get().strip()
        end_str = self._entries["end_date"].get().strip()
        deadline_str = self._entries["submission_deadline"].get().strip()

        # バリデーション
        if not name:
            show_error(self, "期間名を入力してください。")
            return

        start = _parse_date(start_str)
        if start is None:
            show_error(self, "開始日の形式が不正です（YYYY-MM-DD）。")
            return

        end = _parse_date(end_str)
        if end is None:
            show_error(self, "終了日の形式が不正です（YYYY-MM-DD）。")
            return

        if start >= end:
            show_error(self, "開始日は終了日より前の日付を指定してください。")
            return

        deadline = _parse_date(deadline_str)
        if deadline is None:
            show_error(self, "提出期限の形式が不正です（YYYY-MM-DD）。")
            return

        exclude_id = self._period["id"] if self._period else None
        saved: dict | None = None
        try:
            if period_repo.has_overlap(start_str, end_str, exclude_id=exclude_id):
                show_error(self, "指定した期間は既存の期間と重複しています。")
                return
            if self._period is None:
                saved = period_repo.create(name, start_str, end_str, deadline_str)
            else:
                saved = period_repo.update(self._period["id"], name, start_str, end_str, deadline_str)
                if saved is None:
                    get_logger().warning("period_repo.update が None を返した: period_id=%s", self._period["id"])
                    show_error(self, "期間の更新に失敗しました。")
                    return
        except Exception as e:
            get_logger().error("期間保存に失敗: %s", e, exc_info=True)
            show_error(self, "保存に失敗しました。")
            return

        from src.ui.screens.period_dashboard import PeriodDashboardScreen
        self.app.show_screen(PeriodDashboardScreen, period_id=saved["id"])

    def _on_cancel(self) -> None:
        from src.ui.screens.start_screen import StartScreen
        self.app.show_screen(StartScreen)
