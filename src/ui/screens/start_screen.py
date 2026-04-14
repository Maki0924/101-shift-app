"""スタート画面

期間一覧を表示し、新規作成・開く・設定の各操作へ誘導する。
"""

import tkinter as tk
from tkinter import ttk

from src.db.repositories import period_repo
from src.ui.app import STATUS_LABELS
from src.ui.components.dialogs import show_error
from src.utils.logger import get_logger


class StartScreen(ttk.Frame):
    def __init__(self, master: tk.Misc, app, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.app = app
        self._build()
        self._load()

    def _build(self) -> None:
        # タイトル
        ttk.Label(self, text="シフト管理", font=("", 18)).pack(pady=(20, 8))

        # 期間一覧
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=20, pady=8)

        cols = ("name", "range", "status", "form")
        self._tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")
        self._tree.heading("name", text="期間名")
        self._tree.heading("range", text="対象期間")
        self._tree.heading("status", text="ステータス")
        self._tree.heading("form", text="フォーム")
        self._tree.column("name", width=180)
        self._tree.column("range", width=180)
        self._tree.column("status", width=80, anchor="center")
        self._tree.column("form", width=60, anchor="center")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._tree.bind("<Double-1>", lambda e: self._on_open())

        # ボタン行
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=12)

        ttk.Button(btn_frame, text="新規作成", command=self._on_new, width=14).pack(side="left", padx=6)
        self._open_btn = ttk.Button(btn_frame, text="開く", command=self._on_open, width=14, state="disabled")
        self._open_btn.pack(side="left", padx=6)
        ttk.Button(btn_frame, text="設定", command=self._on_settings, width=14).pack(side="left", padx=6)

        self._tree.bind("<<TreeviewSelect>>", self._on_select)

    def _load(self) -> None:
        """期間一覧を再読み込みする（start_date DESC, id DESC）。"""
        for item in self._tree.get_children():
            self._tree.delete(item)

        try:
            periods = sorted(
                period_repo.get_all(),
                key=lambda p: (p["start_date"], p["id"]),
                reverse=True,
            )
        except Exception as e:
            get_logger().error("期間一覧の読み込みに失敗: %s", e, exc_info=True)
            show_error(self, "期間一覧の読み込みに失敗しました。")
            return
        for p in periods:
            date_range = f"{p['start_date']} 〜 {p['end_date']}"
            status = STATUS_LABELS.get(p["status"], p["status"])
            form_mark = "有" if p.get("form_url") else "無"
            self._tree.insert("", "end", iid=str(p["id"]), values=(p["name"], date_range, status, form_mark))

        self._open_btn.configure(state="disabled")

    def _on_select(self, _event=None) -> None:
        state = "normal" if self._tree.selection() else "disabled"
        self._open_btn.configure(state=state)

    def _on_open(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        period_id = int(sel[0])
        from src.ui.screens.period_dashboard import PeriodDashboardScreen

        self.app.show_screen(PeriodDashboardScreen, period_id=period_id)

    def _on_new(self) -> None:
        from src.ui.screens.period_create_screen import PeriodCreateScreen

        self.app.show_screen(PeriodCreateScreen)

    def _on_settings(self) -> None:
        from src.ui.screens.settings_screen import SettingsScreen

        self.app.show_screen(SettingsScreen)
