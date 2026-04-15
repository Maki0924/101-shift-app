"""印刷レイアウト計算（コミット24）

A4横レイアウト。スタッフ30人以下の場合は1ページ優先で自動縮小。
最小閾値（8pt / 12mm / 6mm）を下回る場合はページ分割。
"""

from __future__ import annotations

from dataclasses import dataclass

# A4横 全体サイズ (mm)
A4_W_MM = 297.0
A4_H_MM = 210.0

# 印刷マージン (mm)
MARGIN_MM = 10.0

# 有効印刷領域 (mm)
_CONTENT_W_MM = A4_W_MM - 2 * MARGIN_MM  # 277mm
_CONTENT_H_MM = A4_H_MM - 2 * MARGIN_MM  # 190mm

# 固定列幅・行高
_NAME_W_MM = 25.0  # スタッフ名列幅
_HDR_H_MM = 10.0  # 日付ヘッダー行高

# 可読性最小閾値
MIN_COL_W_MM = 12.0
MIN_ROW_H_MM = 6.0
MIN_FONT_PT = 8

# 1ページ優先が適用されるスタッフ数上限
_ONE_PAGE_STAFF_LIMIT = 30

# サマリー行数（印刷では人件費非表示のため 0）
N_SUMMARY_ROWS = 0

# 縮小前のターゲットサイズ
_TARGET_COL_W_MM = 15.0
_TARGET_ROW_H_MM = 7.0


@dataclass
class Page:
    """1印刷ページ分のレイアウト情報。"""

    dates: list[str]  # このページの日付リスト（YYYY-MM-DD）
    staff: list[dict]  # このページのスタッフリスト
    col_w_mm: float  # 日付列幅 (mm)
    row_h_mm: float  # データ行高 (mm)
    name_w_mm: float = _NAME_W_MM
    hdr_h_mm: float = _HDR_H_MM
    font_size: int = 10

    @property
    def n_data_rows(self) -> int:
        """データ行数（スタッフ行 + サマリー行）。"""
        return len(self.staff) + N_SUMMARY_ROWS

    @property
    def total_w_mm(self) -> float:
        return self.name_w_mm + len(self.dates) * self.col_w_mm

    @property
    def total_h_mm(self) -> float:
        return self.hdr_h_mm + self.n_data_rows * self.row_h_mm


@dataclass
class PageLayout:
    """全ページのレイアウト情報。"""

    pages: list[Page]

    @property
    def page_count(self) -> int:
        return len(self.pages)


def calc_layout(
    dates: list[str],
    staff_list: list[dict],
    font_size: int = 10,
) -> PageLayout:
    """印刷ページレイアウトを計算して返す。

    Args:
        dates: 印刷対象日付リスト（YYYY-MM-DD）
        staff_list: スタッフリスト
        font_size: ターゲットフォントサイズ（pt）

    Returns:
        PageLayout（dates/staff が空のときは空ページリスト）
    """
    if not dates or not staff_list:
        return PageLayout(pages=[])

    n_dates = len(dates)
    n_staff = len(staff_list)
    n_rows = n_staff + N_SUMMARY_ROWS

    date_area_w = _CONTENT_W_MM - _NAME_W_MM  # 252mm
    row_area_h = _CONTENT_H_MM - _HDR_H_MM  # 180mm

    # ── 1ページ優先（スタッフ30人以下）─────────────────────────────────────
    if n_staff <= _ONE_PAGE_STAFF_LIMIT:
        scale_w = date_area_w / (n_dates * _TARGET_COL_W_MM)
        scale_h = row_area_h / (n_rows * _TARGET_ROW_H_MM)
        scale = min(scale_w, scale_h, 1.0)

        col_w = _TARGET_COL_W_MM * scale
        row_h = _TARGET_ROW_H_MM * scale
        fs = max(MIN_FONT_PT, round(font_size * scale))

        if col_w >= MIN_COL_W_MM and row_h >= MIN_ROW_H_MM:
            return PageLayout(
                pages=[
                    Page(
                        dates=dates,
                        staff=list(staff_list),
                        col_w_mm=col_w,
                        row_h_mm=row_h,
                        font_size=fs,
                    )
                ]
            )

    # ── ページ分割 ───────────────────────────────────────────────────────────
    # 1ページに収まる最大列数・最大スタッフ行数
    cols_per_page = max(1, int(date_area_w / MIN_COL_W_MM))  # 252/12 = 21
    rows_per_page = max(1, int(row_area_h / MIN_ROW_H_MM) - N_SUMMARY_ROWS)

    # 分割後の実際のセルサイズ（ページ内に収まる範囲で可能な限り広く）
    col_w = date_area_w / min(n_dates, cols_per_page)
    row_h = row_area_h / (min(n_staff, rows_per_page) + N_SUMMARY_ROWS)

    pages: list[Page] = []
    for col_start in range(0, n_dates, cols_per_page):
        date_slice = dates[col_start : col_start + cols_per_page]
        for row_start in range(0, n_staff, rows_per_page):
            staff_slice = staff_list[row_start : row_start + rows_per_page]
            pages.append(
                Page(
                    dates=date_slice,
                    staff=list(staff_slice),
                    col_w_mm=col_w,
                    row_h_mm=row_h,
                    font_size=font_size,
                )
            )

    return PageLayout(pages=pages)
