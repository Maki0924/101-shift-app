"""共通ダイアログコンポーネント"""

import tkinter as tk
from tkinter import ttk


def show_error(parent: tk.Misc | None, message: str, title: str = "エラー") -> None:
    """モーダルエラーダイアログを表示する。"""
    dlg = tk.Toplevel(parent)
    dlg.title(title)
    if parent:
        dlg.transient(parent)
    dlg.resizable(False, False)

    ttk.Label(dlg, text=message, wraplength=360, justify="left", padding=(16, 12)).pack()
    ttk.Button(dlg, text="OK", command=dlg.destroy, width=10).pack(pady=(0, 12))

    dlg.bind("<Return>", lambda e: dlg.destroy())

    dlg.update_idletasks()
    dlg.grab_set()  # ウィジェット配置・描画後にグラブ（macOS でグラブが効かないケース回避）
    if parent:
        x = parent.winfo_rootx() + (parent.winfo_width() - dlg.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{x}+{y}")

    dlg.wait_window()


def ask_confirm(parent: tk.Misc | None, message: str, title: str = "確認") -> bool:
    """モーダル確認ダイアログを表示し、OKなら True を返す。"""
    result: list[bool] = [False]

    dlg = tk.Toplevel(parent)
    dlg.title(title)
    if parent:
        dlg.transient(parent)
    dlg.resizable(False, False)

    ttk.Label(dlg, text=message, wraplength=360, justify="left", padding=(16, 12)).pack()

    btn_frame = ttk.Frame(dlg, padding=(0, 0, 0, 12))
    btn_frame.pack()

    def _ok() -> None:
        result[0] = True
        dlg.destroy()

    ttk.Button(btn_frame, text="OK", command=_ok, width=10).pack(side="left", padx=4)
    ttk.Button(btn_frame, text="キャンセル", command=dlg.destroy, width=10).pack(side="left", padx=4)

    dlg.bind("<Return>", lambda e: _ok())

    dlg.update_idletasks()
    dlg.grab_set()  # ウィジェット配置・描画後にグラブ（macOS でグラブが効かないケース回避）
    if parent:
        x = parent.winfo_rootx() + (parent.winfo_width() - dlg.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{x}+{y}")

    dlg.wait_window()
    return result[0]
