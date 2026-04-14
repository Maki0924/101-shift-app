"""30分単位時刻セレクタコンポーネント（コミット21）

仕様:
- 0:00〜24:00 の 30分単位コンボボックス
- フォーカスアウト時に確定ロジックを実行（片側→片側フォーカス移動は除外）
- 変換不能入力は破棄してフォーカス前の値を維持
- on_commit コールバックでシフト保存をトリガー
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from src.logic.time_utils import is_valid_time


def _time_values() -> list[str]:
    """0:00〜24:00 の 30分刻みリストを返す。"""
    vals: list[str] = []
    for h in range(25):
        vals.append(f"{h}:00")
        if h < 24:
            vals.append(f"{h}:30")
    return vals


_TIME_VALUES = _time_values()


def str_to_float(s: str) -> float | None:
    """時刻文字列を float に変換する。変換不能なら None を返す。"""
    s = s.strip()
    if not s:
        return None
    try:
        if ":" in s:
            h_str, m_str = s.split(":", 1)
            h, m = int(h_str), int(m_str)
            return h + m / 60
        return float(s)
    except (ValueError, TypeError):
        return None


def float_to_str(v: float | None) -> str:
    """float を時刻文字列に変換する。None なら空文字を返す。"""
    if v is None:
        return ""
    h, m = int(v), int(round((v - int(v)) * 60))
    return f"{h}:{m:02d}" if m else f"{h}:00"


class TimeSelector(ttk.Combobox):
    """30分単位の時刻入力コンボボックス。

    on_commit(value: float | None) は確定時に呼ばれる。
    value が None の場合は「入力なし（クリア）」を意味する。

    Args:
        partner: ペアとなる反対側の TimeSelector（開始↔終了）。
                 パートナーへのフォーカス移動は保存トリガーとしない（§14-3）。
    """

    def __init__(
        self,
        master: tk.Misc,
        on_commit: Callable[[float | None], None],
        partner: TimeSelector | None = None,
        **kwargs,
    ) -> None:
        kwargs.setdefault("values", _TIME_VALUES)
        kwargs.setdefault("width", 7)
        super().__init__(master, **kwargs)
        self._on_commit = on_commit
        self._partner: TimeSelector | None = partner
        self._last_value: float | None = None
        self._var = tk.StringVar()
        self.configure(textvariable=self._var)

        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<<ComboboxSelected>>", self._on_selected)

    def set_partner(self, partner: TimeSelector) -> None:
        self._partner = partner

    def set_value(self, v: float | None) -> None:
        """外部から値をセットする（ロード時・リフレッシュ時）。"""
        self._last_value = v
        self._var.set(float_to_str(v))

    def get_value(self) -> float | None:
        """現在の入力値を float で返す（未入力なら None）。"""
        return str_to_float(self._var.get())

    def mark_error(self, has_error: bool) -> None:
        """エラー状態を視覚的に示す（赤枠）。"""
        style = "Error.TCombobox" if has_error else "TCombobox"
        self.configure(style=style)

    # ── 内部ハンドラ ──────────────────────────────────────────────────────────

    def _on_focus_out(self, event: tk.Event) -> None:
        # フォーカス移動先がパートナーなら保存トリガーしない（§14-3）
        focus_widget = self.focus_get()
        if self._partner is not None and focus_widget is self._partner:
            return
        self._commit()

    def _on_selected(self, _event: tk.Event) -> None:
        # プルダウン選択は即時確定
        self._commit()

    def _commit(self) -> None:
        raw = self._var.get().strip()
        new_val = str_to_float(raw)

        if raw and new_val is None:
            # 変換不能: フォーカスアウト前の値に戻す（破棄）
            self._var.set(float_to_str(self._last_value))
            return

        if not is_valid_time(new_val) and new_val is not None:
            # 30分単位・範囲チェック
            self._var.set(float_to_str(self._last_value))
            return

        if new_val == self._last_value:
            return  # 値変化なし → 履歴に積まない

        self._last_value = new_val
        self._on_commit(new_val)
