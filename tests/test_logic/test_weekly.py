"""週何回希望パース・週回数判定テスト"""

import datetime

import pytest

from src.logic.weekly_count import WeeklyJudgment, judge, judge_total
from src.logic.weekly_pref_parser import parse

# ── weekly_pref_parser ────────────────────────────────────────────────────────

class TestParse:
    # 正常系
    @pytest.mark.parametrize("text,expected", [
        ("3",    (3, 3)),
        ("0",    (0, 0)),
        ("10",   (10, 10)),
        ("1-2",  (1, 2)),
        ("1〜2", (1, 2)),
        ("5以上", (5, None)),
        ("5+",   (5, None)),
        (" 3 ",  (3, 3)),      # 前後空白はトリム
        (" 1-2 ", (1, 2)),
        (" 5+ ",  (5, None)),
    ])
    def test_valid(self, text, expected):
        assert parse(text) == expected

    # 空欄・NULL
    @pytest.mark.parametrize("text", [None, "", "  "])
    def test_empty(self, text):
        assert parse(text) == (None, None)

    # パース不能
    @pytest.mark.parametrize("text", [
        "3回",       # 単位付き
        "週3",       # 接頭語
        "週3回",
        "3 回",      # 途中の空白
        "3~4",       # 半角チルダ（許可外区切り）
        "３",        # 全角数字
        "abc",
        "1-",        # 末尾ハイフン
        "-2",        # 先頭ハイフン
        "1-2-3",     # 多重範囲
        "以上5",     # 順序逆
    ])
    def test_unparseable(self, text):
        assert parse(text) == (None, None)

    def test_min_gt_max_unparseable(self):
        """min > max はパース不能。"""
        assert parse("5-3") == (None, None)


# ── weekly_count ──────────────────────────────────────────────────────────────

def _shift(work_date: str, start: float | None = 9.0, end: float | None = 17.0) -> dict:
    return {"work_date": work_date, "start_time": start, "end_time": end}


class TestJudgeWeek:
    def test_no_pref(self):
        """希望なし → NO_PREF。"""
        results = judge(
            datetime.date(2026, 10, 19), datetime.date(2026, 10, 25),
            None, None,
            [_shift("2026-10-21"), _shift("2026-10-22")],
        )
        assert all(j == WeeklyJudgment.NO_PREF for _, _, j in results)

    def test_under(self):
        """確定回数 < min → UNDER。"""
        results = judge(
            datetime.date(2026, 10, 19), datetime.date(2026, 10, 25),
            3, 5,
            [_shift("2026-10-21"), _shift("2026-10-22")],  # 2回
        )
        assert results[0][2] == WeeklyJudgment.UNDER

    def test_ok(self):
        """min <= 確定回数 <= max → OK。"""
        results = judge(
            datetime.date(2026, 10, 19), datetime.date(2026, 10, 25),
            2, 4,
            [_shift("2026-10-21"), _shift("2026-10-22"), _shift("2026-10-23")],  # 3回
        )
        assert results[0][2] == WeeklyJudgment.OK

    def test_over(self):
        """確定回数 > max → OVER。"""
        results = judge(
            datetime.date(2026, 10, 19), datetime.date(2026, 10, 25),
            1, 2,
            [_shift("2026-10-21"), _shift("2026-10-22"), _shift("2026-10-23")],  # 3回
        )
        assert results[0][2] == WeeklyJudgment.OVER

    def test_boundary_min(self):
        """確定回数 == min → OK。"""
        results = judge(
            datetime.date(2026, 10, 19), datetime.date(2026, 10, 25),
            2, 4,
            [_shift("2026-10-21"), _shift("2026-10-22")],  # ちょうど2回
        )
        assert results[0][2] == WeeklyJudgment.OK

    def test_boundary_max(self):
        """確定回数 == max → OK。"""
        results = judge(
            datetime.date(2026, 10, 19), datetime.date(2026, 10, 25),
            2, 4,
            [_shift("2026-10-21"), _shift("2026-10-22"),
             _shift("2026-10-23"), _shift("2026-10-24")],  # ちょうど4回
        )
        assert results[0][2] == WeeklyJudgment.OK

    def test_no_max_never_over(self):
        """max=None（上限なし）は何回でも OVER にならない。"""
        results = judge(
            datetime.date(2026, 10, 19), datetime.date(2026, 10, 25),
            1, None,
            [_shift("2026-10-21"), _shift("2026-10-22"), _shift("2026-10-23"),
             _shift("2026-10-24"), _shift("2026-10-25")],  # 5回
        )
        assert results[0][2] == WeeklyJudgment.OK

    def test_null_null_shift_not_counted(self):
        """勤務なし（NULL/NULL）は確定回数にカウントしない。"""
        results = judge(
            datetime.date(2026, 10, 19), datetime.date(2026, 10, 25),
            2, 3,
            [_shift("2026-10-21"), _shift("2026-10-22", None, None)],  # 確定1回
        )
        assert results[0][1] == 1
        assert results[0][2] == WeeklyJudgment.UNDER

    def test_monday_week_start(self):
        """月曜起算で週が分割される。"""
        # 2026-10-19(月)〜10-25(日) と 2026-10-26(月)〜11-01(日)
        results = judge(
            datetime.date(2026, 10, 19), datetime.date(2026, 11, 1),
            2, 3,
            [
                _shift("2026-10-21"), _shift("2026-10-22"),  # 1週目 2回
                _shift("2026-10-27"), _shift("2026-10-28"), _shift("2026-10-29"),  # 2週目 3回
            ],
        )
        assert len(results) == 2
        assert results[0][1] == 2
        assert results[1][1] == 3


class TestPrevPeriodReference:
    def test_prev_period_shifts_counted_in_first_week(self):
        """前期間の確定シフトが先頭週に含まれる。"""
        # 現期間: 2026-10-21(水)〜11-20 → 先頭週の月曜は10-19
        # 前期間末日: 2026-10-20(火)
        prev_shifts = [_shift("2026-10-19"), _shift("2026-10-20")]  # 月・火 2回
        current_shifts = [_shift("2026-10-21"), _shift("2026-10-22")]  # 水・木 2回

        results = judge(
            datetime.date(2026, 10, 21), datetime.date(2026, 10, 25),
            4, 5,
            current_shifts,
            prev_edited_shifts=prev_shifts,
            prev_period_end=datetime.date(2026, 10, 20),
        )
        # 先頭週: 10-19〜10-25, 合計4回 → OK
        assert results[0][1] == 4
        assert results[0][2] == WeeklyJudgment.OK

    def test_no_prev_period(self):
        """前期間なしでも正常に動作する。"""
        results = judge(
            datetime.date(2026, 10, 21), datetime.date(2026, 10, 25),
            2, 3,
            [_shift("2026-10-21"), _shift("2026-10-22")],
        )
        assert results[0][1] == 2


class TestJudgeTotal:
    def test_worst_is_under(self):
        """UNDER が最も優先度高。"""
        result = judge_total(
            datetime.date(2026, 10, 19), datetime.date(2026, 11, 1),
            3, 5,
            [
                _shift("2026-10-21"),  # 1週目: 1回 → UNDER
                _shift("2026-10-26"), _shift("2026-10-27"),
                _shift("2026-10-28"), _shift("2026-10-29"),  # 2週目: 4回 → OK
            ],
        )
        assert result == WeeklyJudgment.UNDER

    def test_no_pref_when_no_min_max(self):
        result = judge_total(
            datetime.date(2026, 10, 19), datetime.date(2026, 10, 25),
            None, None,
            [_shift("2026-10-21")],
        )
        assert result == WeeklyJudgment.NO_PREF
