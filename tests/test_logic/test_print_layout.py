"""print_layout モジュールの単体テスト（コミット24）"""

import datetime

from src.logic.print_layout import (
    _CONTENT_H_MM,
    _CONTENT_W_MM,
    MIN_COL_W_MM,
    MIN_FONT_PT,
    MIN_ROW_H_MM,
    N_SUMMARY_ROWS,
    calc_layout,
)


def _make_dates(n: int, start: str = "2026-10-01") -> list[str]:
    base = datetime.date.fromisoformat(start)
    return [(base + datetime.timedelta(days=i)).isoformat() for i in range(n)]


def _make_staff(n: int) -> list[dict]:
    return [{"id": i, "name": f"Staff{i}"} for i in range(n)]


# ── 空入力 ────────────────────────────────────────────────────────────────────


class TestEmpty:
    def test_empty_dates_returns_no_pages(self):
        result = calc_layout([], _make_staff(5))
        assert result.pages == []

    def test_empty_staff_returns_no_pages(self):
        result = calc_layout(_make_dates(10), [])
        assert result.pages == []

    def test_page_count_zero(self):
        result = calc_layout([], [])
        assert result.page_count == 0


# ── 1ページ優先（≤30 スタッフ） ────────────────────────────────────────────────


class TestOnePage:
    def test_small_input_fits_on_one_page(self):
        dates = _make_dates(10)
        staff = _make_staff(5)
        result = calc_layout(dates, staff)
        assert result.page_count == 1

    def test_one_page_includes_all_dates(self):
        dates = _make_dates(10)
        staff = _make_staff(5)
        page = calc_layout(dates, staff).pages[0]
        assert page.dates == dates

    def test_one_page_includes_all_staff(self):
        dates = _make_dates(10)
        staff = _make_staff(5)
        page = calc_layout(dates, staff).pages[0]
        assert page.staff == staff

    def test_30_staff_is_within_limit(self):
        """30人はちょうど1ページ優先の境界。"""
        dates = _make_dates(5)
        staff = _make_staff(30)
        result = calc_layout(dates, staff)
        assert result.page_count == 1

    def test_col_w_above_minimum(self):
        dates = _make_dates(10)
        staff = _make_staff(5)
        page = calc_layout(dates, staff).pages[0]
        assert page.col_w_mm >= MIN_COL_W_MM

    def test_row_h_above_minimum(self):
        dates = _make_dates(10)
        staff = _make_staff(5)
        page = calc_layout(dates, staff).pages[0]
        assert page.row_h_mm >= MIN_ROW_H_MM

    def test_font_size_above_minimum(self):
        dates = _make_dates(10)
        staff = _make_staff(5)
        page = calc_layout(dates, staff).pages[0]
        assert page.font_size >= MIN_FONT_PT


# ── 閾値下回り → ページ分割 ────────────────────────────────────────────────────


class TestSplit:
    def test_many_dates_splits_pages(self):
        """日付数が多すぎると列方向に分割される。

        date_area_w = 252mm, MIN_COL_W_MM = 12mm → 1ページ最大21列。
        22日以上の場合は2ページ以上になる。
        """
        dates = _make_dates(22)
        staff = _make_staff(5)
        result = calc_layout(dates, staff)
        assert result.page_count >= 2

    def test_31_staff_may_split(self):
        """31人は1ページ優先の対象外になる（ページ分割か縮小）。"""
        dates = _make_dates(1)
        staff = _make_staff(31)
        result = calc_layout(dates, staff)
        assert result.page_count >= 1

    def test_all_dates_covered_after_col_split(self):
        """分割後もすべての日付が少なくとも1ページに含まれる。"""
        dates = _make_dates(25)
        staff = _make_staff(5)
        result = calc_layout(dates, staff)
        covered = set()
        for p in result.pages:
            covered.update(p.dates)
        assert covered == set(dates)

    def test_all_staff_covered_after_row_split(self):
        """分割後もすべてのスタッフが少なくとも1ページに含まれる。"""
        dates = _make_dates(5)
        staff = _make_staff(35)
        result = calc_layout(dates, staff)
        covered = set()
        for p in result.pages:
            covered.add(s["id"] for s in p.staff)
        covered_ids = set()
        for p in result.pages:
            for s in p.staff:
                covered_ids.add(s["id"])
        assert covered_ids == {s["id"] for s in staff}

    def test_split_col_w_above_minimum(self):
        """分割後の列幅は最小値以上。"""
        dates = _make_dates(25)
        staff = _make_staff(5)
        result = calc_layout(dates, staff)
        for p in result.pages:
            assert p.col_w_mm >= MIN_COL_W_MM - 0.001

    def test_split_row_h_above_minimum(self):
        """分割後の行高は最小値以上。"""
        dates = _make_dates(5)
        staff = _make_staff(35)
        result = calc_layout(dates, staff)
        for p in result.pages:
            assert p.row_h_mm >= MIN_ROW_H_MM - 0.001


# ── Page プロパティ ────────────────────────────────────────────────────────────


class TestPageProperties:
    def test_n_data_rows_equals_staff_count(self):
        """印刷ではサマリー行なし（N_SUMMARY_ROWS == 0）。"""
        assert N_SUMMARY_ROWS == 0
        dates = _make_dates(5)
        staff = _make_staff(10)
        page = calc_layout(dates, staff).pages[0]
        assert page.n_data_rows == len(staff)

    def test_total_w_mm_consistent(self):
        dates = _make_dates(10)
        staff = _make_staff(5)
        page = calc_layout(dates, staff).pages[0]
        expected = page.name_w_mm + len(page.dates) * page.col_w_mm
        assert abs(page.total_w_mm - expected) < 0.001

    def test_total_h_mm_consistent(self):
        dates = _make_dates(10)
        staff = _make_staff(5)
        page = calc_layout(dates, staff).pages[0]
        expected = page.hdr_h_mm + len(page.staff) * page.row_h_mm
        assert abs(page.total_h_mm - expected) < 0.001

    def test_total_w_within_content_area(self):
        """1ページに収まる場合、幅がコンテンツ領域内に収まる。"""
        dates = _make_dates(5)
        staff = _make_staff(5)
        page = calc_layout(dates, staff).pages[0]
        assert page.total_w_mm <= _CONTENT_W_MM + 0.001

    def test_total_h_within_content_area(self):
        """1ページに収まる場合、高さがコンテンツ領域内に収まる。"""
        dates = _make_dates(5)
        staff = _make_staff(5)
        page = calc_layout(dates, staff).pages[0]
        assert page.total_h_mm <= _CONTENT_H_MM + 0.001
