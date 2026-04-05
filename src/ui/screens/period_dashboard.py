"""期間ダッシュボード（コミット14で本実装）"""

import tkinter as tk
from tkinter import ttk

from src.db.repositories import period_repo


class PeriodDashboardScreen(ttk.Frame):
    """期間ダッシュボードのスタブ。コミット14で本実装する。"""

    def __init__(self, master: tk.Misc, app, period_id: int, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.app = app
        period = period_repo.get_by_id(period_id)
        name = period["name"] if period else "?"
        ttk.Label(self, text=f"期間ダッシュボード: {name}", font=("", 16)).pack(expand=True)
        ttk.Button(self, text="← 戻る", command=self._on_back).pack(pady=12)

    def _on_back(self) -> None:
        from src.ui.screens.start_screen import StartScreen
        self.app.show_screen(StartScreen)
