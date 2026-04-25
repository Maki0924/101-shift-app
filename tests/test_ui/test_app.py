"""App._poll_ui_queue のテスト"""

import queue
from unittest import mock

from src.ui.app import App


class TestPollUiQueue:
    def _make_app(self):
        """Tk 初期化をスキップして App インスタンスを生成する。"""
        app = App.__new__(App)
        app._ui_queue = queue.SimpleQueue()
        app.after = mock.Mock()
        app._shutdown_event = mock.Mock()
        app._current_screen = None
        return app

    def test_executes_queued_callbacks(self):
        app = self._make_app()
        results = []
        app._ui_queue.put(lambda: results.append(1))
        app._ui_queue.put(lambda: results.append(2))

        app._poll_ui_queue()

        assert results == [1, 2]

    def test_reschedules_after_even_if_callback_raises(self):
        app = self._make_app()
        app._ui_queue.put(lambda: (_ for _ in ()).throw(RuntimeError("boom")))

        app._poll_ui_queue()

        app.after.assert_called_once_with(100, app._poll_ui_queue)

    def test_subsequent_callbacks_run_after_exception(self):
        app = self._make_app()
        results = []
        app._ui_queue.put(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        app._ui_queue.put(lambda: results.append("ok"))

        app._poll_ui_queue()

        assert results == ["ok"]

    def test_empty_queue_still_reschedules(self):
        app = self._make_app()

        app._poll_ui_queue()

        app.after.assert_called_once_with(100, app._poll_ui_queue)


class TestCurrentScreenRefresh:
    def test_refresh_current_screen_data_calls_hook_when_available(self):
        app = App.__new__(App)
        app._current_screen = mock.Mock()

        app.refresh_current_screen_data()

        app._current_screen.refresh_after_data_change.assert_called_once()

    def test_refresh_current_screen_data_ignores_unsupported_screen(self):
        app = App.__new__(App)
        app._current_screen = object()

        app.refresh_current_screen_data()


class TestShutdownState:
    def test_is_shutting_down_reflects_event_state(self):
        app = App.__new__(App)
        app._shutdown_event = mock.Mock()
        app._shutdown_event.is_set.return_value = True

        assert app.is_shutting_down() is True
