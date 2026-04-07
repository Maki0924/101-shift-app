"""period_create_screen の純粋関数テスト"""

import datetime

from src.ui.screens.period_create_screen import (
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
