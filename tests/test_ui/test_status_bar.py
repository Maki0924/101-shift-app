"""StatusBar の時限クリア管理テスト

Tk を起動せず __new__ + mock でインスタンスを生成し、
タイマー予約・キャンセル・上書き保護を検証する。
"""

from __future__ import annotations

from unittest import mock

from src.ui.components.status_bar import StatusBar


def _make_bar() -> StatusBar:
    """StatusBar を Tk なしで生成する。"""
    bar = StatusBar.__new__(StatusBar)
    bar._clear_after_id = None
    bar._sync_label = mock.Mock()
    bar.after = mock.Mock(return_value="after_id_1")
    bar.after_cancel = mock.Mock()
    return bar


class TestSetTimedSyncMessage:
    def test_schedules_clear_timer(self):
        """set_timed_sync_message はメッセージを表示し after タイマーを予約する。"""
        bar = _make_bar()
        bar.set_timed_sync_message("エラー発生", ms=8000)

        bar._sync_label.configure.assert_called_with(text="エラー発生")
        bar.after.assert_called_once_with(8000, mock.ANY)
        assert bar._clear_after_id == "after_id_1"

    def test_new_sync_message_cancels_old_timer(self):
        """set_sync_message が呼ばれると古いタイマー予約がキャンセルされる。"""
        bar = _make_bar()
        bar.set_timed_sync_message("古いエラー", ms=8000)
        old_id = bar._clear_after_id  # "after_id_1"

        bar.set_sync_message("同期中…")

        bar.after_cancel.assert_called_once_with(old_id)
        assert bar._clear_after_id is None

    def test_old_timer_does_not_clear_new_message(self):
        """古いタイマーの clear 予約が新しいメッセージを消さない。

        set_timed_sync_message("エラー") → set_sync_message("同期中…") の順で
        呼ばれた場合、エラー用タイマーはキャンセル済みなので "同期中…" は残る。
        """
        bar = _make_bar()
        bar.set_timed_sync_message("古いエラー", ms=8000)

        # 同期開始で新メッセージが来る（古いタイマーがキャンセルされる）
        bar.set_sync_message("同期中…")

        # after_cancel が呼ばれ、新しい after は予約されていない
        assert bar.after_cancel.call_count == 1
        # 新メッセージ表示後に追加の after 予約がないことを確認
        assert bar.after.call_count == 1  # set_timed_sync_message の1回だけ

    def test_second_timed_message_cancels_first_timer(self):
        """2回目の set_timed_sync_message は1回目のタイマーをキャンセルする。"""
        bar = _make_bar()
        bar.after.side_effect = ["after_id_1", "after_id_2"]

        bar.set_timed_sync_message("1回目", ms=8000)
        bar.set_timed_sync_message("2回目", ms=8000)

        bar.after_cancel.assert_called_once_with("after_id_1")
        assert bar._clear_after_id == "after_id_2"
