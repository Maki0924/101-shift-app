"""アプリケーションルートウィンドウ・画面切り替え機構"""

import queue
import threading
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk

from src.ui.components.status_bar import StatusBar
from src.utils.logger import get_logger

# ステータス表示ラベル（全画面共通）
STATUS_LABELS: dict[str, str] = {
    "collecting": "募集中",
    "editing": "編集中",
    "archived": "アーカイブ",
}

# UIキューポーリング間隔 (ms)
_UI_QUEUE_POLL_MS = 100


@dataclass(frozen=True)
class AppWarning:
    """アプリ全体で管理する警告エントリ。

    period_id: 対象期間ID（アプリ全体の警告は None）
    message: 警告メッセージ
    kind: 警告種別（"parse_error" | "general"）。デフォルトは "general"
    """

    period_id: int | None
    message: str
    kind: str = "general"


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
        self._shutdown_event = threading.Event()

        # UI トリガーのワーカースレッド管理（close_connection() 前に join するため）
        self._workers: set[threading.Thread] = set()
        self._workers_lock = threading.Lock()

        # メインコンテナ（画面を配置する領域）
        self._container = ttk.Frame(self)
        self._container.pack(fill="both", expand=True)

        # ステータスバー
        self.status_bar = StatusBar(self)
        self.status_bar.pack(side="bottom", fill="x")

        self._current_screen: ttk.Frame | None = None

        # スレッドセーフUI更新用キュー（ワーカースレッドから直接 after() を呼ばないこと）
        self._ui_queue: queue.SimpleQueue[Callable[[], None]] = queue.SimpleQueue()
        self.after(_UI_QUEUE_POLL_MS, self._poll_ui_queue)
        self.protocol("WM_DELETE_WINDOW", self.request_shutdown)

    def _poll_ui_queue(self) -> None:
        """ワーカースレッドからのUI更新要求をメインスレッドで処理する。"""
        while True:
            try:
                fn = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception as e:
                get_logger().error("post_to_ui のコールバックで例外: %s", e, exc_info=True)
        self.after(_UI_QUEUE_POLL_MS, self._poll_ui_queue)

    def post_to_ui(self, fn: Callable[[], None]) -> None:
        """ワーカースレッドからスレッドセーフにUI更新をスケジュールする。

        ワーカースレッドから Tkinter を操作する際は after() の代わりにこのメソッドを使うこと。
        キューに積まれた関数は約100ms以内にメインスレッドで実行される。
        """
        self._ui_queue.put(fn)

    def request_shutdown(self) -> None:
        """終了要求を記録し、ルートウィンドウを閉じる。"""
        self._shutdown_event.set()
        if self.winfo_exists():
            self.destroy()

    def is_shutting_down(self) -> bool:
        """終了処理が開始済みなら True を返す。"""
        return self._shutdown_event.is_set()

    def start_worker(self, target: Callable[[], None]) -> threading.Thread:
        """daemon スレッドを起動して登録する。join_workers() で close_connection() 前に回収できる。"""
        thread = threading.Thread(target=target, daemon=True)
        with self._workers_lock:
            self._workers = {t for t in self._workers if t.is_alive()}
            self._workers.add(thread)
        thread.start()
        return thread

    def join_workers(self, timeout_each: float = 5.0) -> None:
        """全登録ワーカースレッドを timeout_each 秒ずつ待つ。超過時は警告ログを残す。"""
        with self._workers_lock:
            threads = set(self._workers)
        for t in threads:
            if t.is_alive():
                t.join(timeout=timeout_each)
                if t.is_alive():
                    get_logger().warning("Worker thread did not finish within timeout: %s", t.name)

    def refresh_current_screen_data(self) -> None:
        """現在画面がデータ更新通知に対応していれば再読込する。"""
        screen = self._current_screen
        if screen is None or not hasattr(screen, "refresh_after_data_change"):
            return
        try:
            screen.refresh_after_data_change()
        except Exception as e:
            get_logger().error("current screen refresh failed: %s", e, exc_info=True)

    def show_screen(self, screen_cls: type[ttk.Frame], **kwargs) -> ttk.Frame:
        """指定した画面クラスのインスタンスを生成して表示する。

        既存の画面は破棄する。
        `screen_cls(app=self, **kwargs)` として生成する。
        """
        if self._current_screen is not None:
            self._current_screen.destroy()
            self._current_screen = None  # 先にNoneにして状態不整合を防ぐ

        screen = screen_cls(self._container, app=self, **kwargs)
        screen.pack(fill="both", expand=True)
        self._current_screen = screen
        return screen
