"""period_create_screen のテスト"""

import datetime
from unittest import mock

from src.ui.screens.period_create_screen import (
    PeriodCreateScreen,
    _deadline_day_warning,
    _default_dates,
    _is_archived_period,
    _parse_date,
)


class TestDefaultDates:
    def test_normal(self):
        # 今日: 4月 → 翌月(5月)21日 〜 翌々月(6月)20日
        today = datetime.date(2026, 4, 6)
        start, end, deadline = _default_dates(today)
        assert start == "2026-05-21"
        assert end == "2026-06-20"
        assert deadline == "2026-06-10"

    def test_november(self):
        # 今日: 11月 → 翌月(12月)21日 〜 翌々月(1月)20日
        today = datetime.date(2026, 11, 15)
        start, end, deadline = _default_dates(today)
        assert start == "2026-12-21"
        assert end == "2027-01-20"
        assert deadline == "2027-01-10"

    def test_december_wrap(self):
        # 今日: 12月 → 翌月(1月)21日 〜 翌々月(2月)20日
        today = datetime.date(2026, 12, 1)
        start, end, deadline = _default_dates(today)
        assert start == "2027-01-21"
        assert end == "2027-02-20"
        assert deadline == "2027-02-10"


class TestDeadlineDayWarning:
    def test_day_10_no_warning(self):
        assert _deadline_day_warning("2026-05-10") is False

    def test_day_9_warning(self):
        assert _deadline_day_warning("2026-05-09") is True

    def test_day_11_warning(self):
        assert _deadline_day_warning("2026-05-11") is True

    def test_last_day_warning(self):
        assert _deadline_day_warning("2026-05-31") is True

    def test_invalid_returns_false(self):
        assert _deadline_day_warning("not-a-date") is False
        assert _deadline_day_warning("") is False


class TestParseDate:
    def test_valid(self):
        assert _parse_date("2026-04-21") == datetime.date(2026, 4, 21)

    def test_with_whitespace(self):
        assert _parse_date("  2026-04-21  ") == datetime.date(2026, 4, 21)

    def test_invalid_returns_none(self):
        assert _parse_date("2026/04/21") is None
        assert _parse_date("abc") is None
        assert _parse_date("2026-02-30") is None

    def test_empty_returns_none(self):
        assert _parse_date("") is None


class TestIsArchivedPeriod:
    def test_archived_returns_true(self):
        assert _is_archived_period({"status": "archived"}) is True

    def test_collecting_returns_false(self):
        assert _is_archived_period({"status": "collecting"}) is False

    def test_editing_returns_false(self):
        assert _is_archived_period({"status": "editing"}) is False

    def test_none_returns_false(self):
        assert _is_archived_period(None) is False


class DummyEntry:
    def __init__(self):
        self.insert_calls: list[tuple[int, str]] = []
        self.focused = False

    def insert(self, index: int, value: str) -> None:
        self.insert_calls.append((index, value))

    def focus_set(self) -> None:
        self.focused = True


class TestPeriodCreateScreen:
    def test_fill_defaults_in_edit_mode_sets_focus_to_name(self):
        screen = PeriodCreateScreen.__new__(PeriodCreateScreen)
        name_entry = DummyEntry()
        start_entry = DummyEntry()
        end_entry = DummyEntry()
        deadline_entry = DummyEntry()
        screen._period = {
            "name": "5月後半",
            "start_date": "2026-05-21",
            "end_date": "2026-06-20",
            "submission_deadline": "2026-06-10",
        }
        screen._entries = {
            "name": name_entry,
            "start_date": start_entry,
            "end_date": end_entry,
            "submission_deadline": deadline_entry,
        }
        screen._update_deadline_warning = mock.Mock()

        screen._fill_defaults()

        assert name_entry.insert_calls == [(0, "5月後半")]
        assert start_entry.insert_calls == [(0, "2026-05-21")]
        assert end_entry.insert_calls == [(0, "2026-06-20")]
        assert deadline_entry.insert_calls == [(0, "2026-06-10")]
        assert name_entry.focused is True
        screen._update_deadline_warning.assert_called_once_with()

    def test_fill_defaults_in_create_mode_sets_focus_to_name(self):
        screen = PeriodCreateScreen.__new__(PeriodCreateScreen)
        name_entry = DummyEntry()
        start_entry = DummyEntry()
        end_entry = DummyEntry()
        deadline_entry = DummyEntry()
        screen._period = None
        screen._entries = {
            "name": name_entry,
            "start_date": start_entry,
            "end_date": end_entry,
            "submission_deadline": deadline_entry,
        }
        screen._update_deadline_warning = mock.Mock()

        with mock.patch(
            "src.ui.screens.period_create_screen._default_dates",
            return_value=("2026-05-21", "2026-06-20", "2026-06-10"),
        ):
            screen._fill_defaults()

        assert name_entry.insert_calls == []
        assert start_entry.insert_calls == [(0, "2026-05-21")]
        assert end_entry.insert_calls == [(0, "2026-06-20")]
        assert deadline_entry.insert_calls == [(0, "2026-06-10")]
        assert name_entry.focused is True
        screen._update_deadline_warning.assert_called_once_with()

    def test_on_cancel_returns_to_dashboard_when_back_period_id_exists(self):
        screen = PeriodCreateScreen.__new__(PeriodCreateScreen)
        screen._back_period_id = 42
        screen.app = mock.Mock()

        screen._on_cancel()

        called_screen = screen.app.show_screen.call_args.args[0]
        assert called_screen.__name__ == "PeriodDashboardScreen"
        assert screen.app.show_screen.call_args.kwargs == {"period_id": 42}

    def test_on_cancel_returns_to_start_screen_when_back_period_id_is_none(self):
        screen = PeriodCreateScreen.__new__(PeriodCreateScreen)
        screen._back_period_id = None
        screen.app = mock.Mock()

        screen._on_cancel()

        called_screen = screen.app.show_screen.call_args.args[0]
        assert called_screen.__name__ == "StartScreen"
        assert screen.app.show_screen.call_args.kwargs == {}
