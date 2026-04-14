"""UndoRedoStack のユニットテスト（コミット22）"""

from src.logic.undo_redo import UndoEntry, UndoRedoStack


def _entry(n: int) -> UndoEntry:
    return UndoEntry(kind="shift", staff_id=1, period_id=1, work_date="2025-04-01", before=n, after=n + 1)


class TestUndoRedoStack:
    def test_initial_state(self):
        s = UndoRedoStack()
        assert not s.can_undo()
        assert not s.can_redo()

    def test_push_enables_undo(self):
        s = UndoRedoStack()
        s.push(_entry(0))
        assert s.can_undo()
        assert not s.can_redo()

    def test_pop_undo_returns_entry(self):
        s = UndoRedoStack()
        e = _entry(0)
        s.push(e)
        result = s.pop_undo()
        assert result is e
        assert not s.can_undo()
        assert s.can_redo()

    def test_pop_redo_after_undo(self):
        s = UndoRedoStack()
        e = _entry(0)
        s.push(e)
        s.pop_undo()
        result = s.pop_redo()
        assert result is e
        assert s.can_undo()
        assert not s.can_redo()

    def test_push_clears_redo(self):
        s = UndoRedoStack()
        s.push(_entry(0))
        s.pop_undo()
        assert s.can_redo()
        s.push(_entry(1))
        assert not s.can_redo()

    def test_max_stack_limit(self):
        s = UndoRedoStack()
        for i in range(55):
            s.push(_entry(i))
        assert s.undo_size == 50

    def test_reset_clears_all(self):
        s = UndoRedoStack()
        s.push(_entry(0))
        s.pop_undo()
        s.reset()
        assert not s.can_undo()
        assert not s.can_redo()

    def test_pop_undo_none_when_empty(self):
        s = UndoRedoStack()
        assert s.pop_undo() is None

    def test_pop_redo_none_when_empty(self):
        s = UndoRedoStack()
        assert s.pop_redo() is None
