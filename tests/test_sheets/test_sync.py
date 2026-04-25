"""Google Sheets 同期 — 純粋関数テスト

Sheets API を呼び出さない部分（column_mapper / パース / ハッシュ生成）をテストする。
"""

from unittest import mock

from src.sheets.column_mapper import parse_header, resolve_date
from src.sheets.sync import (
    SyncResult,
    _generate_key,
    _norm_str,
    _parse_mode_a,
    _parse_mode_b,
    _parse_time_str,
    sync_period,
)

# ── sync_period cancel_check ──────────────────────────────────────────────────


class TestSyncPeriodCancelCheck:
    _PERIOD = {
        "id": 1,
        "start_date": "2026-10-21",
        "end_date": "2026-10-21",
        "spreadsheet_id": "sheet123",
    }

    def _make_sheets_svc(self, rows=None):
        if rows is None:
            rows = [
                ["タイムスタンプ", "スタッフ名"],
                ["2026/10/01 10:00:00", "田中"],
                ["2026/10/01 11:00:00", "鈴木"],
            ]
        svc = mock.MagicMock()
        svc.spreadsheets().values().get().execute.return_value = {"values": rows}
        return svc

    def test_cancel_before_api_call_skips_api(self):
        svc = self._make_sheets_svc()
        result = sync_period(
            self._PERIOD,
            svc,
            {},
            cancel_check=lambda: True,
        )
        svc.spreadsheets().values().get().execute.assert_not_called()
        assert result.added == 0

    def test_cancel_between_rows_stops_processing(self):
        svc = self._make_sheets_svc()
        call_count = 0

        def cancel_after_first():
            nonlocal call_count
            call_count += 1
            return call_count > 1

        with (
            mock.patch("src.sheets.sync.submission_repo") as mock_repo,
            mock.patch("src.sheets.sync.col_mod.parse_header") as mock_header,
        ):
            mock_repo.exists_by_key.return_value = False
            cm = mock.MagicMock()
            cm.unknown_cols = []
            cm.mode_b_morning = {}
            cm.mode_b_afternoon = {}
            cm.mode_a_start = {"2026-10-21": None}
            cm.mode_a_end = {"2026-10-21": None}
            cm.submitted_at_idx = 0
            cm.staff_name_idx = 1
            cm.note_idx = None
            cm.weekly_pref_idx = None
            cm.mode_idx = None
            mock_header.return_value = cm

            sync_period(
                self._PERIOD,
                svc,
                {},
                cancel_check=cancel_after_first,
            )

        assert mock_repo.create_with_day_entries.call_count == 0

    def test_no_cancel_check_processes_all_rows(self):
        svc = self._make_sheets_svc()
        with (
            mock.patch("src.sheets.sync.submission_repo") as mock_repo,
            mock.patch("src.sheets.sync.col_mod.parse_header") as mock_header,
        ):
            mock_repo.exists_by_key.return_value = True
            cm = mock.MagicMock()
            cm.unknown_cols = []
            cm.mode_b_morning = {}
            cm.mode_b_afternoon = {}
            cm.mode_a_start = {"2026-10-21": None}
            cm.mode_a_end = {"2026-10-21": None}
            cm.submitted_at_idx = 0
            cm.staff_name_idx = 1
            cm.note_idx = None
            cm.weekly_pref_idx = None
            cm.mode_idx = None
            mock_header.return_value = cm

            result = sync_period(self._PERIOD, svc, {})

        assert result.skipped == 2


# ── resolve_date ──────────────────────────────────────────────────────────────


class TestResolveDate:
    def test_normal(self):
        assert resolve_date("10/21", "2026-10-21", "2026-11-20") == "2026-10-21"

    def test_end_of_period(self):
        assert resolve_date("11/20", "2026-10-21", "2026-11-20") == "2026-11-20"

    def test_year_wrap_december(self):
        # 年跨ぎ期間: 12/25 → 2026-12-25
        assert resolve_date("12/25", "2026-12-21", "2027-01-20") == "2026-12-25"

    def test_year_wrap_january(self):
        # 年跨ぎ期間: 01/05 → 2027-01-05
        assert resolve_date("01/05", "2026-12-21", "2027-01-20") == "2027-01-05"

    def test_out_of_range(self):
        # 期間外の日付は None
        assert resolve_date("12/20", "2026-12-21", "2027-01-20") is None

    def test_invalid_format(self):
        assert resolve_date("invalid", "2026-10-21", "2026-11-20") is None

    def test_invalid_date(self):
        # 2月30日など存在しない日付
        assert resolve_date("02/30", "2026-02-01", "2026-03-01") is None


# ── parse_header ──────────────────────────────────────────────────────────────


class TestParseHeader:
    START, END = "2026-10-21", "2026-11-20"

    def test_basic_columns(self):
        headers = ["タイムスタンプ", "スタッフ名", "備考", "週何回希望", "入力方式"]
        cm = parse_header(headers, self.START, self.END)
        assert cm.submitted_at_idx == 0
        assert cm.staff_name_idx == 1
        assert cm.note_idx == 2
        assert cm.weekly_pref_idx == 3
        assert cm.mode_idx == 4

    def test_mode_a_columns(self):
        headers = ["タイムスタンプ", "スタッフ名", "10/21_開始", "10/21_終了"]
        cm = parse_header(headers, self.START, self.END)
        assert cm.mode_a_start["2026-10-21"] == 2
        assert cm.mode_a_end["2026-10-21"] == 3

    def test_mode_b_columns(self):
        headers = ["タイムスタンプ", "スタッフ名", "10/21_午前不可", "10/21_午後不可"]
        cm = parse_header(headers, self.START, self.END)
        assert cm.mode_b_morning["2026-10-21"] == 2
        assert cm.mode_b_afternoon["2026-10-21"] == 3

    def test_unknown_columns(self):
        headers = ["タイムスタンプ", "謎の列"]
        cm = parse_header(headers, self.START, self.END)
        assert "謎の列" in cm.unknown_cols

    def test_out_of_period_date_column(self):
        # 期間外の日付列は unknown_cols に入る
        headers = ["12/25_開始"]  # 期間外
        cm = parse_header(headers, self.START, self.END)
        assert "12/25_開始" in cm.unknown_cols

    def test_year_wrap_columns(self):
        headers = ["12/25_開始", "01/05_開始"]
        cm = parse_header(headers, "2026-12-21", "2027-01-20")
        assert "2026-12-25" in cm.mode_a_start
        assert "2027-01-05" in cm.mode_a_start


# ── _parse_time_str ───────────────────────────────────────────────────────────


class TestParseTimeStr:
    def test_hour_zero_minute(self):
        assert _parse_time_str("09:00") == 9.0

    def test_half_hour(self):
        assert _parse_time_str("17:30") == 17.5

    def test_leading_zero(self):
        assert _parse_time_str("08:00") == 8.0

    def test_no_leading_zero(self):
        assert _parse_time_str("9:00") == 9.0

    def test_non_half_hour_returns_none(self):
        assert _parse_time_str("09:15") is None
        assert _parse_time_str("17:45") is None

    def test_invalid_format_returns_none(self):
        assert _parse_time_str("9時") is None
        assert _parse_time_str("9.0") is None
        assert _parse_time_str("abc") is None

    def test_empty_returns_none(self):
        assert _parse_time_str("") is None
        assert _parse_time_str(None) is None
        assert _parse_time_str("  ") is None


# ── _parse_mode_b ─────────────────────────────────────────────────────────────


class TestParseModeB:
    def test_neither_checked(self):
        assert _parse_mode_b(None, None) == (11.0, 22.0)

    def test_neither_checked_empty_str(self):
        assert _parse_mode_b("", "") == (11.0, 22.0)

    def test_morning_only(self):
        # 午前不可のみ → 午後だけ入れる
        assert _parse_mode_b("入れない", None) == (18.0, 22.0)

    def test_afternoon_only(self):
        # 午後不可のみ → 午前だけ入れる
        assert _parse_mode_b(None, "入れない") == (11.0, 16.0)

    def test_both_checked(self):
        # 両方不可 → 勤務不可
        assert _parse_mode_b("入れない", "入れない") == (None, None)

    def test_any_nonempty_string_is_checked(self):
        # 非空文字列ならチェックあり扱い（値に依存しない）
        assert _parse_mode_b("TRUE", "TRUE") == (None, None)


# ── _generate_key ─────────────────────────────────────────────────────────────


class TestGenerateKey:
    _BASE = dict(
        submitted_at_raw="2026-10-01 10:00:00",
        raw_staff_name="山田太郎",
        period_id=1,
        note_raw=None,
        weekly_pref_raw="3",
        mode_raw="mode_a",
        date_time_values=[("09:00", "17:00")],
    )

    def test_consistent(self):
        k1 = _generate_key(**self._BASE)
        k2 = _generate_key(**self._BASE)
        assert k1 == k2

    def test_sha256_hex_length(self):
        k = _generate_key(**self._BASE)
        assert len(k) == 64

    def test_different_staff_different_key(self):
        k1 = _generate_key(**self._BASE)
        k2 = _generate_key(**{**self._BASE, "raw_staff_name": "鈴木花子"})
        assert k1 != k2

    def test_time_normalization_9_vs_9_0(self):
        """9:00 と 09:00 は同一キーになる。"""
        k1 = _generate_key(**{**self._BASE, "date_time_values": [("9:00", "17:00")]})
        k2 = _generate_key(**{**self._BASE, "date_time_values": [("09:00", "17:00")]})
        assert k1 == k2

    def test_null_vs_empty_same_key(self):
        """None と空文字列は __NULL__ として同一視する。"""
        k1 = _generate_key(**{**self._BASE, "note_raw": None})
        k2 = _generate_key(**{**self._BASE, "note_raw": ""})
        assert k1 == k2

    def test_different_mode_different_key(self):
        """入力方式が異なれば異なるキーになる。"""
        k1 = _generate_key(**{**self._BASE, "mode_raw": "mode_a"})
        k2 = _generate_key(**{**self._BASE, "mode_raw": "mode_b"})
        assert k1 != k2


# ── _parse_mode_a ────────────────────────────────────────────────────────────


class TestParseModeA:
    DATE = "2026-10-21"

    def _result(self):
        return SyncResult(period_id=1)

    def test_normal(self):
        r = self._result()
        assert _parse_mode_a("09:00", "17:00", self.DATE, r, "ctx") == (9.0, 17.0)
        assert r.warnings == []

    def test_both_none(self):
        """開始・終了ともに空 → NULL/NULL（警告なし）。"""
        r = self._result()
        assert _parse_mode_a(None, None, self.DATE, r, "ctx") == (None, None)
        assert r.warnings == []

    def test_start_only_invalid_format(self):
        """開始が不正フォーマット → 両方 None + 警告。"""
        r = self._result()
        assert _parse_mode_a("9時", "17:00", self.DATE, r, "ctx") == (None, None)
        assert len(r.warnings) == 1
        assert "開始" in r.warnings[0]

    def test_end_only_invalid_format(self):
        """終了が不正フォーマット → 両方 None + 警告。"""
        r = self._result()
        assert _parse_mode_a("09:00", "17:15", self.DATE, r, "ctx") == (None, None)
        assert len(r.warnings) == 1
        assert "終了" in r.warnings[0]

    def test_start_gte_end(self):
        """start >= end → 両方 None + 警告。"""
        r = self._result()
        assert _parse_mode_a("17:00", "09:00", self.DATE, r, "ctx") == (None, None)
        assert len(r.warnings) == 1

    def test_start_equal_end(self):
        """start == end も異常扱い。"""
        r = self._result()
        assert _parse_mode_a("09:00", "09:00", self.DATE, r, "ctx") == (None, None)
        assert len(r.warnings) == 1

    def test_start_only(self):
        """開始のみ入力（終了空欄）→ NULL/NULL + 警告。"""
        r = self._result()
        assert _parse_mode_a("09:00", None, self.DATE, r, "ctx") == (None, None)
        assert len(r.warnings) == 1
        assert "片側" in r.warnings[0]

    def test_end_only(self):
        """終了のみ入力（開始空欄）→ NULL/NULL + 警告。"""
        r = self._result()
        assert _parse_mode_a(None, "17:00", self.DATE, r, "ctx") == (None, None)
        assert len(r.warnings) == 1
        assert "片側" in r.warnings[0]


# ── _norm_str ─────────────────────────────────────────────────────────────────


class TestNormStr:
    def test_none_returns_null_token(self):
        assert _norm_str(None) == "__NULL__"

    def test_empty_returns_null_token(self):
        assert _norm_str("") == "__NULL__"
        assert _norm_str("  ") == "__NULL__"

    def test_trims_whitespace(self):
        assert _norm_str("  hello  ") == "hello"

    def test_normalizes_newlines(self):
        assert _norm_str("a\r\nb") == "a\nb"
        assert _norm_str("a\rb") == "a\nb"
