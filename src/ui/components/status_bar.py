"""保存状態インジケーター"""

import tkinter as tk
from tkinter import ttk

_STATE_TEXT = {
    "saved": "保存済み",
    "saving": "保存中…",
    "failed": "保存失敗",
}
_STATE_FG = {
    "saved": "gray",
    "saving": "black",
    "failed": "red",
}


class StatusBar(tk.Frame):
    """ウィンドウ下部に配置する保存状態インジケーター。

    NOTE: ttk.Frame は theme システム経由のため relief が効かない。
    sunken ボーダーを確実に描画するため tk.Frame を使用する。

    使用例:
        bar = StatusBar(root)
        bar.pack(side="bottom", fill="x")
        bar.set_state("saved")
    """

    def __init__(self, master: tk.Misc, **kwargs) -> None:
        super().__init__(master, relief="sunken", bd=1, **kwargs)
        self._label = ttk.Label(self, text="", anchor="e", padding=(4, 2))
        self._label.pack(side="right")

    def set_state(self, state: str) -> None:
        """state: 'saved' | 'saving' | 'failed'"""
        text = _STATE_TEXT.get(state, state)
        fg = _STATE_FG.get(state, "black")
        self._label.configure(text=text, foreground=fg)

    def set_sync_message(self, message: str) -> None:
        """同期状態など任意のメッセージを左側に表示する。"""
        # sync_label は遅延生成（使用する画面でのみ表示）
        if not hasattr(self, "_sync_label"):
            self._sync_label = ttk.Label(self, text="", anchor="w", padding=(4, 2))
            self._sync_label.pack(side="left")
        self._sync_label.configure(text=message)
