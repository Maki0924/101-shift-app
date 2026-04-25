"""App._poll_ui_queue のテスト"""

import queue
import threading
import time
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


class TestWorkerManagement:
    def _make_app(self):
        app = App.__new__(App)
        app._workers = set()
        app._workers_lock = threading.Lock()
        return app

    def test_start_worker_runs_target(self):
        app = self._make_app()
        done = threading.Event()
        app.start_worker(done.set)
        assert done.wait(timeout=2)

    def test_start_worker_registers_thread(self):
        app = self._make_app()
        started = threading.Event()
        blocking = threading.Event()

        def target():
            started.set()
            blocking.wait()

        thread = app.start_worker(target)
        started.wait(timeout=2)
        try:
            assert thread in app._workers
        finally:
            blocking.set()
            thread.join(timeout=2)

    def test_start_worker_is_daemon(self):
        app = self._make_app()
        done = threading.Event()
        thread = app.start_worker(done.set)
        assert thread.daemon is True
        done.wait(timeout=2)

    def test_join_workers_waits_for_completion(self):
        app = self._make_app()
        results = []

        def slow_target():
            time.sleep(0.05)
            results.append(1)

        app.start_worker(slow_target)
        app.join_workers(timeout_each=2.0)
        assert results == [1]

    def test_join_workers_logs_warning_on_timeout(self):
        app = self._make_app()
        blocking = threading.Event()

        def never_finishes():
            blocking.wait(timeout=10)

        app.start_worker(never_finishes)
        with mock.patch("src.ui.app.get_logger") as mock_logger:
            app.join_workers(timeout_each=0.01)
            mock_logger.return_value.warning.assert_called_once()
        blocking.set()

    def test_start_worker_prunes_dead_threads(self):
        app = self._make_app()
        done = threading.Event()

        dead = app.start_worker(done.set)
        done.wait(timeout=2)
        dead.join(timeout=2)

        blocking = threading.Event()
        app.start_worker(blocking.wait)
        assert dead not in app._workers
        blocking.set()
