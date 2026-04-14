"""SubmissionListScreen._update_warnings() の表示テスト

- 未紐付け / パース不能 / その他警告 の組み合わせで
  ラベルテキストが正しく組み立てられることを確認する
"""

from src.ui.app import AppWarning
from src.ui.screens.submission_list_screen import SubmissionListScreen


class _FakeLabel:
    def __init__(self) -> None:
        self.text = ""

    def configure(self, **kwargs) -> None:
        if "text" in kwargs:
            self.text = kwargs["text"]


class _FakeApp:
    def __init__(self, warnings: list[AppWarning]) -> None:
        self.warnings = warnings


def _make_screen(
    submissions: list[dict],
    warnings: list[AppWarning],
    period_id: int = 1,
) -> SubmissionListScreen:
    screen = SubmissionListScreen.__new__(SubmissionListScreen)
    screen._period_id = period_id
    screen._all_submissions = submissions
    screen.app = _FakeApp(warnings)
    screen._warn_label = _FakeLabel()
    return screen


def _sub(staff_id: int | None) -> dict:
    return {"staff_id": staff_id}


def _warn(kind: str = "general", period_id: int = 1) -> AppWarning:
    return AppWarning(period_id=period_id, message="テスト警告", kind=kind)


class TestUpdateWarningsEmpty:
    def test_no_warnings_empty_label(self):
        """問題がなければラベルは空になる。"""
        screen = _make_screen([_sub(1), _sub(2)], [])
        screen._update_warnings()
        assert screen._warn_label.text == ""


class TestUpdateWarningsUnlinked:
    def test_unlinked_count_shown(self):
        """未紐付け回答の件数が表示される。"""
        screen = _make_screen([_sub(None), _sub(None), _sub(1)], [])
        screen._update_warnings()
        assert "未紐付け回答: 2件" in screen._warn_label.text

    def test_no_unlinked_hides_label(self):
        """未紐付けが0件なら未紐付けラベルは表示されない。"""
        screen = _make_screen([_sub(1), _sub(2)], [])
        screen._update_warnings()
        assert "未紐付け" not in screen._warn_label.text


class TestUpdateWarningsParseError:
    def test_parse_error_shown_separately(self):
        """parse_error は「パース不能: N件」として表示される。"""
        screen = _make_screen([], [_warn("parse_error"), _warn("parse_error")])
        screen._update_warnings()
        assert "パース不能: 2件" in screen._warn_label.text

    def test_general_warning_not_counted_as_parse_error(self):
        """general 警告はパース不能には含まれない。"""
        screen = _make_screen([], [_warn("general")])
        screen._update_warnings()
        assert "パース不能" not in screen._warn_label.text
        assert "警告: 1件" in screen._warn_label.text

    def test_other_period_warnings_excluded(self):
        """別期間の警告は表示されない。"""
        screen = _make_screen([], [_warn("parse_error", period_id=99)], period_id=1)
        screen._update_warnings()
        assert screen._warn_label.text == ""


class TestUpdateWarningsCombined:
    def test_all_three_categories(self):
        """未紐付け・パース不能・その他警告がすべて存在する場合、3つが | で連結される。"""
        subs = [_sub(None)]
        warns = [_warn("parse_error"), _warn("general")]
        screen = _make_screen(subs, warns)
        screen._update_warnings()
        text = screen._warn_label.text
        assert "未紐付け回答: 1件" in text
        assert "パース不能: 1件" in text
        assert "警告: 1件" in text
        assert text.count("  |  ") == 2

    def test_parse_error_and_general_split(self):
        """parse_error と general が混在しても正しく分離される。"""
        warns = [_warn("parse_error"), _warn("parse_error"), _warn("general")]
        screen = _make_screen([], warns)
        screen._update_warnings()
        assert "パース不能: 2件" in screen._warn_label.text
        assert "警告: 1件" in screen._warn_label.text
