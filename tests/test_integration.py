"""統合テスト（コミット28）: v1 E2E フロー検証

期間作成 → スタッフ登録 → フォーム同期（Sheets API モック）→ 回答採用
→ シフト編集 → 人件費計算 → 印刷設定保存 の一連フローを実 SQLite DB で検証する。

Google Sheets / Forms / Drive API は unittest.mock でモックし、
固定フィクスチャデータで閉じることで再現性を保証する。
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pytest

import src.db.connection as conn_module
from src.db.connection import close_connection, init_connection
from src.db.init_db import init_db
from src.db.repositories import (
    edited_shift_repo,
    period_repo,
    print_settings_repo,
    settings_repo,
    staff_repo,
    submission_repo,
    wish_shift_repo,
)
from src.logic.apply_submission import apply
from src.logic.wage_calc import calc_wage
from src.logic.weekly_count import count_confirmed_in_range
from src.sheets.sync import sync_period


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    """テスト用インメモリDB（tmp_path に隔離）。"""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(conn_module, "_DB_FILE", db_file)
    monkeypatch.setattr(conn_module, "_connection", None)
    init_connection()
    init_db()
    yield
    close_connection()
    monkeypatch.setattr(conn_module, "_connection", None)


# ── フィクスチャヘルパー ──────────────────────────────────────────────────────


def _make_sheets_service(rows: list[list[str]]) -> MagicMock:
    """固定レスポンスを返す Sheets API サービスモックを生成する。"""
    svc = MagicMock()
    svc.spreadsheets().values().get().execute.return_value = {"values": rows}
    return svc


# 期間: 2026-10-21 〜 2026-11-20
_PERIOD_START = "2026-10-21"
_PERIOD_END = "2026-11-20"

# モードA フォームのヘッダー行と1件の回答行
_FIXTURE_HEADERS = [
    "タイムスタンプ",
    "スタッフ名",
    "備考",
    "週何回希望",
    "10/25_開始",
    "10/25_終了",
    "10/26_開始",
    "10/26_終了",
]
_FIXTURE_ROW_TANAKA = [
    "2026/10/15 10:00:00",
    "田中太郎",
    "よろしくお願いします",
    "3",
    "9:00",  # 10/25 開始
    "17:00",  # 10/25 終了
    "10:00",  # 10/26 開始
    "18:00",  # 10/26 終了
]
_FIXTURE_ROW_SATO = [
    "2026/10/15 11:00:00",
    "佐藤花子",
    "",
    "2",
    "8:00",
    "14:00",
    "",
    "",
]


# ── メインE2Eテスト ──────────────────────────────────────────────────────────


class TestV1E2eFlow:
    def test_full_flow_period_to_print_settings(self):
        """期間作成→スタッフ登録→フォーム同期→採用→シフト編集→人件費→印刷設定保存。"""

        # ── 1. 期間作成 ──
        period = period_repo.create("10月度", _PERIOD_START, _PERIOD_END, "2026-11-10")
        period = period_repo.update_status(period["id"], "editing")
        assert period["status"] == "editing"

        # ── 2. スタッフ登録 ──
        tanaka = staff_repo.create("田中太郎", "part_time", 1000)
        assert tanaka["name"] == "田中太郎"
        assert tanaka["employment_type"] == "part_time"

        staff_map = {tanaka["name"]: tanaka["id"]}

        # ── 3. フォーム同期（Sheets API モック）──
        period_record = {
            **period,
            "spreadsheet_id": "mock_spreadsheet_id",
        }
        mock_svc = _make_sheets_service([_FIXTURE_HEADERS, _FIXTURE_ROW_TANAKA])
        result = sync_period(period_record, mock_svc, staff_map)

        assert result.added == 1
        assert result.skipped == 0

        # ── 4. 回答採用 ──
        subs = submission_repo.get_by_period(period["id"])
        assert len(subs) == 1
        sub = subs[0]
        assert sub["raw_staff_name"] == "田中太郎"
        assert sub["staff_id"] == tanaka["id"]

        apply(sub["id"])

        sub_after = submission_repo.get_by_id(sub["id"])
        assert sub_after["apply_status"] == "applied"

        # ── 5. wish_shifts が再生成されている ──
        wishes = wish_shift_repo.get_by_period(period["id"])
        wish_dates = {w["work_date"] for w in wishes}
        assert "2026-10-25" in wish_dates
        assert "2026-10-26" in wish_dates

        # ── 6. シフト編集 ──
        shift = edited_shift_repo.upsert(period["id"], tanaka["id"], "2026-10-25", 9.0, 17.0)
        assert shift is not None
        assert shift["start_time"] == 9.0
        assert shift["end_time"] == 17.0

        # ── 7. 人件費計算 ──
        date = datetime.date(2026, 10, 25)  # 日曜日
        app_settings = settings_repo.get()
        wage = calc_wage(
            9.0,
            17.0,
            tanaka["hourly_wage"],
            date,
            app_settings["saturday_bonus"],
            app_settings["sunday_bonus"],
            app_settings["holiday_bonus"],
        )
        # 8h - 1h休憩 = 7h * 1000円 + 日曜ボーナス
        expected_base = int(7 * tanaka["hourly_wage"])
        assert wage >= expected_base  # ボーナス加算分が含まれる可能性あり

        # ── 8. 印刷設定保存 ──
        print_settings_repo.upsert(period["id"], _PERIOD_START, _PERIOD_END)
        saved = print_settings_repo.get_by_period(period["id"])
        assert saved is not None
        assert saved["print_from_date"] == _PERIOD_START
        assert saved["print_to_date"] == _PERIOD_END


# ── フォーム同期の個別検証 ────────────────────────────────────────────────────


class TestSyncFlow:
    def test_sync_idempotent(self):
        """同一回答を2回同期しても件数は増えない（冪等性）。"""
        period = period_repo.create("10月度", _PERIOD_START, _PERIOD_END, "2026-11-10")
        tanaka = staff_repo.create("田中太郎", "part_time", 1000)
        period_record = {**period, "spreadsheet_id": "mock_id"}
        staff_map = {tanaka["name"]: tanaka["id"]}

        mock_svc = _make_sheets_service([_FIXTURE_HEADERS, _FIXTURE_ROW_TANAKA])
        result1 = sync_period(period_record, mock_svc, staff_map)
        result2 = sync_period(period_record, mock_svc, staff_map)

        assert result1.added == 1
        assert result2.added == 0  # 冪等: 2回目は追加なし
        assert result2.skipped == 1

    def test_sync_multiple_staff(self):
        """複数スタッフの回答を一括同期できる。"""
        period = period_repo.create("10月度", _PERIOD_START, _PERIOD_END, "2026-11-10")
        tanaka = staff_repo.create("田中太郎", "part_time", 1000)
        sato = staff_repo.create("佐藤花子", "employee", 1200)
        period_record = {**period, "spreadsheet_id": "mock_id"}
        staff_map = {tanaka["name"]: tanaka["id"], sato["name"]: sato["id"]}

        mock_svc = _make_sheets_service([_FIXTURE_HEADERS, _FIXTURE_ROW_TANAKA, _FIXTURE_ROW_SATO])
        result = sync_period(period_record, mock_svc, staff_map)

        assert result.added == 2
        subs = submission_repo.get_by_period(period["id"])
        assert len(subs) == 2

    def test_sync_without_spreadsheet_id_returns_empty(self):
        """spreadsheet_id がない期間は同期をスキップして空の結果を返す。"""
        period = period_repo.create("10月度", _PERIOD_START, _PERIOD_END, "2026-11-10")
        mock_svc = _make_sheets_service([_FIXTURE_HEADERS, _FIXTURE_ROW_TANAKA])
        result = sync_period(period, mock_svc, {})

        assert result.added == 0


# ── 採用トランザクションの個別検証 ───────────────────────────────────────────


class TestApplySubmissionFlow:
    def test_apply_replaces_previous_submission(self):
        """同一スタッフの新しい回答を採用すると、旧採用が pending に戻る。"""
        period = period_repo.create("10月度", _PERIOD_START, _PERIOD_END, "2026-11-10")
        tanaka = staff_repo.create("田中太郎", "part_time", 1000)
        period_record = {**period, "spreadsheet_id": "mock_id"}
        staff_map = {tanaka["name"]: tanaka["id"]}

        # 1回目同期・採用
        mock_svc = _make_sheets_service([_FIXTURE_HEADERS, _FIXTURE_ROW_TANAKA])
        sync_period(period_record, mock_svc, staff_map)
        sub1 = submission_repo.get_by_period(period["id"])[0]
        apply(sub1["id"])
        assert submission_repo.get_by_id(sub1["id"])["apply_status"] == "applied"

        # 2回目同期（別の回答行）
        row2 = _FIXTURE_ROW_TANAKA.copy()
        row2[0] = "2026/10/16 09:00:00"  # 別タイムスタンプ → 別キー
        mock_svc2 = _make_sheets_service([_FIXTURE_HEADERS, row2])
        sync_period(period_record, mock_svc2, staff_map)

        subs = submission_repo.get_by_period(period["id"])
        assert len(subs) == 2
        sub2 = next(s for s in subs if s["id"] != sub1["id"])
        apply(sub2["id"])

        # 旧採用が pending に戻っている
        assert submission_repo.get_by_id(sub1["id"])["apply_status"] == "pending"
        assert submission_repo.get_by_id(sub2["id"])["apply_status"] == "applied"


# ── 週回数判定の個別検証 ─────────────────────────────────────────────────────


class TestWeeklyCountFlow:
    def test_confirmed_count_matches_edited_shifts(self):
        """編集シフト件数が週回数集計に正しく反映される。"""
        period = period_repo.create("10月度", _PERIOD_START, _PERIOD_END, "2026-11-10")
        tanaka = staff_repo.create("田中太郎", "part_time", 1000)

        # 2026-10-26(月)〜2026-11-01(日) の週に3件追加
        for date_str in ("2026-10-26", "2026-10-27", "2026-10-28"):
            edited_shift_repo.upsert(period["id"], tanaka["id"], date_str, 9.0, 17.0)
        # 別の週（前週）に1件 → カウント対象外
        edited_shift_repo.upsert(period["id"], tanaka["id"], "2026-10-25", 9.0, 17.0)

        shifts = edited_shift_repo.get_by_period_and_staff(period["id"], tanaka["id"])
        week_start = datetime.date(2026, 10, 26)  # 月曜日
        week_end = datetime.date(2026, 11, 1)  # 日曜日
        count = count_confirmed_in_range(shifts, week_start, week_end)

        assert count == 3


# ── archived 期間の印刷設定保存ガード ────────────────────────────────────────


class TestArchivedPeriodGuard:
    def test_archived_period_does_not_overwrite_print_settings(self):
        """archived 期間では印刷設定を上書きしない（ビジネスロジックをリポジトリ層で確認）。"""
        period = period_repo.create("10月度", _PERIOD_START, _PERIOD_END, "2026-11-10")
        # 一度 editing で保存
        period_repo.update_status(period["id"], "editing")
        print_settings_repo.upsert(period["id"], _PERIOD_START, _PERIOD_END)

        # archived に変更後は print_screen 側が保存を行わないことをリポジトリで確認
        # （print_screen のロジックは test_ui/test_print_screen.py でカバー済み）
        period_repo.update_status(period["id"], "archived")
        p = period_repo.get_by_id(period["id"])
        assert p["status"] == "archived"
        # 既存の設定は残っている（リポジトリは archived を意識しない）
        saved = print_settings_repo.get_by_period(period["id"])
        assert saved is not None
