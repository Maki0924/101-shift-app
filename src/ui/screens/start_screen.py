"""スタート画面（コミット13で本実装）"""

import tkinter as tk
from tkinter import ttk


class StartScreen(ttk.Frame):
    """スタート画面のスタブ。コミット13で本実装する。"""

    def __init__(self, master: tk.Misc, app, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.app = app
        ttk.Label(self, text="シフト管理", font=("", 20)).pack(expand=True)
