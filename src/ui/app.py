"""アプリケーションルートウィンドウ・画面切り替え機構"""

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

from src.ui.components.status_bar import StatusBar


@dataclass(frozen=True)
class AppWarning:
    """アプリ全体で管理する警告エントリ。

    period_id: 対象期間ID（アプリ全体の警告は None）
    message: 警告メッセージ
    """
    period_id: int | None
    message: str


class App(tk.Tk):
    """アプリケーションルートウィンドウ。

    `show_screen(screen_cls, **kwargs)` で画面を切り替える。
    各画面クラスは `ttk.Frame` のサブクラスとして実装し、
    コンストラクタで `app` を受け取る規約とする。
    """

    def __init__(self, creds_available: bool = False) -> None:
        super().__init__()
        self.title("シフト管理")
        self.geometry("960x640")
        self.minsize(800, 500)

        # credentials 利用可否フラグ（各画面から参照）
        self.creds_available: bool = creds_available

        # 警告リスト（アプリ全体で1つ）。period_id で期間別フィルタリング可能
        self.warnings: list[AppWarning] = []

        # メインコンテナ（画面を配置する領域）
        self._container = ttk.Frame(self)
        self._container.pack(fill="both", expand=True)

        # ステータスバー
        self.status_bar = StatusBar(self)
        self.status_bar.pack(side="bottom", fill="x")

        self._current_screen: ttk.Frame | None = None

    def show_screen(self, screen_cls: type, **kwargs) -> ttk.Frame:
        """指定した画面クラスのインスタンスを生成して表示する。

        既存の画面は破棄する。
        `screen_cls(app=self, **kwargs)` として生成する。
        """
        if self._current_screen is not None:
            self._current_screen.destroy()

        screen = screen_cls(self._container, app=self, **kwargs)
        screen.pack(fill="both", expand=True)
        self._current_screen = screen
        return screen
