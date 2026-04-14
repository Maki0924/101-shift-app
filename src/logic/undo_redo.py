"""Undo/Redo スタック（コミット22）

- メモリ内スタック（最大50操作）
- 期間切替時リセット
- 操作の粒度（1単位）:
    - シフト編集: クリア / 希望を反映 / 時刻入力フォーカスアウト（値変化時のみ）
    - 色付け: 手動色の設定・解除
    - 店長メモ: フォーカスアウト保存時
    - 一括反映: 1回の一括反映全体を1単位
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_MAX_STACK = 50


@dataclass
class UndoEntry:
    """1操作分の Undo/Redo エントリ。

    before / after は DB レコードのスナップショット（dict または dict のリスト）。
    kind で操作種別を識別し、undo/redo 時にどのリポジトリを呼ぶかを決定する。
    """

    kind: str  # "shift" | "mark" | "memo" | "bulk"
    staff_id: int
    period_id: int
    work_date: str | None  # bulk の場合は None
    before: Any  # 操作前の値
    after: Any  # 操作後の値


class UndoRedoStack:
    """Undo/Redo スタック。

    1インスタンスをシフト編集画面で保持し、画面破棄時に reset() する。
    """

    def __init__(self) -> None:
        self._undo: list[UndoEntry] = []
        self._redo: list[UndoEntry] = []

    # ── 操作記録 ─────────────────────────────────────────────────────────────

    def push(self, entry: UndoEntry) -> None:
        """操作を記録する（redo スタックはクリア）。"""
        self._undo.append(entry)
        if len(self._undo) > _MAX_STACK:
            self._undo.pop(0)
        self._redo.clear()

    # ── Undo ─────────────────────────────────────────────────────────────────

    def can_undo(self) -> bool:
        return bool(self._undo)

    def pop_undo(self) -> UndoEntry | None:
        """Undo エントリを取り出す（None の場合は履歴なし）。"""
        if not self._undo:
            return None
        entry = self._undo.pop()
        self._redo.append(entry)
        return entry

    # ── Redo ─────────────────────────────────────────────────────────────────

    def can_redo(self) -> bool:
        return bool(self._redo)

    def pop_redo(self) -> UndoEntry | None:
        """Redo エントリを取り出す（None の場合は履歴なし）。"""
        if not self._redo:
            return None
        entry = self._redo.pop()
        self._undo.append(entry)
        return entry

    # ── リセット ─────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """スタックを完全にリセットする（期間切替時に呼ぶ）。"""
        self._undo.clear()
        self._redo.clear()

    @property
    def undo_size(self) -> int:
        return len(self._undo)

    @property
    def redo_size(self) -> int:
        return len(self._redo)
