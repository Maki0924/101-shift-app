"""SubmissionDetailScreen._update_buttons() のボタン状態テスト

- archived 期間では全ボタンが disabled になる
- applied 状態では 保留/却下ボタンが disabled になる
"""

from src.ui.screens.submission_detail import SubmissionDetailScreen


class _FakeBtn:
    """ttk.Button の最小スタブ。configure(state=...) を記録する。"""

    def __init__(self) -> None:
        self.state = "normal"

    def configure(self, **kwargs) -> None:
        if "state" in kwargs:
            self.state = kwargs["state"]


def _make_screen(is_archived: bool) -> SubmissionDetailScreen:
    """SubmissionDetailScreen を Tk 初期化なしで生成する。"""
    screen = SubmissionDetailScreen.__new__(SubmissionDetailScreen)
    screen._is_archived = is_archived
    screen._apply_btn = _FakeBtn()
    screen._hold_btn = _FakeBtn()
    screen._reject_btn = _FakeBtn()
    screen._link_btn = _FakeBtn()
    return screen


def _sub(status: str, staff_id: int | None = 1) -> dict:
    return {"apply_status": status, "staff_id": staff_id}


class TestArchivedPeriodGuard:
    def test_all_buttons_disabled_when_archived(self):
        """archived 期間ではすべてのボタンが disabled になる。"""
        screen = _make_screen(is_archived=True)
        screen._update_buttons(_sub("pending"))

        assert screen._apply_btn.state == "disabled"
        assert screen._hold_btn.state == "disabled"
        assert screen._reject_btn.state == "disabled"
        assert screen._link_btn.state == "disabled"

    def test_archived_applies_regardless_of_submission_status(self):
        """archived ガードは回答ステータスによらず全ボタンを disabled にする。"""
        for status in ("applied", "on_hold", "rejected"):
            screen = _make_screen(is_archived=True)
            screen._update_buttons(_sub(status))

            assert screen._apply_btn.state == "disabled", f"status={status}"
            assert screen._hold_btn.state == "disabled", f"status={status}"
            assert screen._reject_btn.state == "disabled", f"status={status}"
            assert screen._link_btn.state == "disabled", f"status={status}"


class TestAppliedStatusGuard:
    def test_hold_and_reject_disabled_when_applied(self):
        """applied 状態では wish_shifts 不整合を防ぐため 保留/却下 を disabled にする。"""
        screen = _make_screen(is_archived=False)
        screen._update_buttons(_sub("applied", staff_id=1))

        assert screen._hold_btn.state == "disabled"
        assert screen._reject_btn.state == "disabled"

    def test_apply_disabled_when_already_applied(self):
        """採用済みの回答は再採用できない。"""
        screen = _make_screen(is_archived=False)
        screen._update_buttons(_sub("applied", staff_id=1))

        assert screen._apply_btn.state == "disabled"

    def test_link_disabled_when_applied(self):
        """applied は wish_shifts 整合性を保てないため再紐付けを禁止。"""
        screen = _make_screen(is_archived=False)
        screen._update_buttons(_sub("applied", staff_id=1))

        assert screen._link_btn.state == "disabled"


class TestNormalStatusButtons:
    def test_pending_linked_enables_apply(self):
        """紐付け済み・未処理は採用ボタンが有効。"""
        screen = _make_screen(is_archived=False)
        screen._update_buttons(_sub("pending", staff_id=1))

        assert screen._apply_btn.state == "normal"
        assert screen._hold_btn.state == "normal"
        assert screen._reject_btn.state == "normal"

    def test_unlinked_disables_apply(self):
        """未紐付けは採用ボタンが無効。"""
        screen = _make_screen(is_archived=False)
        screen._update_buttons(_sub("pending", staff_id=None))

        assert screen._apply_btn.state == "disabled"

    def test_on_hold_disables_hold_btn(self):
        """保留中は保留ボタンが disabled（重複操作防止）。"""
        screen = _make_screen(is_archived=False)
        screen._update_buttons(_sub("on_hold", staff_id=1))

        assert screen._hold_btn.state == "disabled"
        assert screen._reject_btn.state == "normal"

    def test_rejected_disables_reject_btn(self):
        """却下済みは却下ボタンが disabled（重複操作防止）。"""
        screen = _make_screen(is_archived=False)
        screen._update_buttons(_sub("rejected", staff_id=1))

        assert screen._reject_btn.state == "disabled"
        assert screen._hold_btn.state == "normal"
