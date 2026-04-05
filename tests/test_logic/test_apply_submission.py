"""採用処理トランザクションテスト"""

import sqlite3
from contextlib import contextmanager

import pytest

import src.db.connection as conn_module
import src.logic.apply_submission as apply_mod
from src.db.connection import close_connection, get_connection, init_connection
from src.db.init_db import init_db
from src.db.repositories import period_repo, staff_repo, submission_repo, wish_shift_repo
from src.logic.apply_submission import ApplyError, apply


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(conn_module, "_DB_FILE", db_file)
    monkeypatch.setattr(conn_module, "_connection", None)
    init_connection()
    init_db()
    yield
    close_connection()
    monkeypatch.setattr(conn_module, "_connection", None)


# ── ヘルパー ──────────────────────────────────────────────────────────────────

def _make_period():
    return period_repo.create("10月度", "2026-10-21", "2026-11-20", "2026-11-10")


def _make_staff():
    return staff_repo.create("山田太郎", "part_time", 1000)


def _make_submission(period_id: int, staff_id: int | None = None,
                     submitted_at: str = "2026-10-01 10:00:00") -> dict:
    return submission_repo.create(
        period_id=period_id,
        staff_id=staff_id,
        raw_staff_name="山田太郎",
        external_submission_key=f"key_{submitted_at}",
        submitted_at=submitted_at,
        note_text=None,
        weekly_pref_min=None,
        weekly_pref_max=None,
    )


def _add_day_entries(submission_id: int) -> None:
    """2勤務可能日 + 1勤務不可日 を登録する。"""
    submission_repo.upsert_day_entries(submission_id, [
        {"work_date": "2026-10-21", "start_time": 9.0, "end_time": 17.0},
        {"work_date": "2026-10-22", "start_time": None, "end_time": None},  # 勤務不可
        {"work_date": "2026-10-23", "start_time": 10.0, "end_time": 18.0},
    ])


# ── TestApply ─────────────────────────────────────────────────────────────────

class TestApply:
    def test_normal_apply(self):
        """正常採用: apply_status=applied / wish_shifts生成 / is_latest更新。"""
        p = _make_period()
        s = _make_staff()
        sub = _make_submission(p["id"], staff_id=s["id"])
        _add_day_entries(sub["id"])

        apply(sub["id"])

        updated = submission_repo.get_by_id(sub["id"])
        assert updated["apply_status"] == "applied"
        assert updated["is_latest_for_staff"] == 1

        ws = wish_shift_repo.get_by_period_and_staff(p["id"], s["id"])
        # NULL/NULL (10-22) は除外 → 2件
        assert len(ws) == 2
        dates = {r["work_date"] for r in ws}
        assert dates == {"2026-10-21", "2026-10-23"}

    def test_wish_shifts_null_excluded(self):
        """勤務不可日（NULL/NULL）は wish_shifts に含まれない。"""
        p = _make_period()
        s = _make_staff()
        sub = _make_submission(p["id"], staff_id=s["id"])
        submission_repo.upsert_day_entries(sub["id"], [
            {"work_date": "2026-10-21", "start_time": None, "end_time": None},
            {"work_date": "2026-10-22", "start_time": None, "end_time": None},
        ])

        apply(sub["id"])

        ws = wish_shift_repo.get_by_period_and_staff(p["id"], s["id"])
        assert ws == []

    def test_replacement(self):
        """差し替え: 旧採用解除 → 新採用 / wish_shifts更新。"""
        p = _make_period()
        s = _make_staff()
        sub1 = _make_submission(p["id"], staff_id=s["id"], submitted_at="2026-10-01 09:00:00")
        _add_day_entries(sub1["id"])
        apply(sub1["id"])  # sub1 を採用

        sub2 = _make_submission(p["id"], staff_id=s["id"], submitted_at="2026-10-02 10:00:00")
        _add_day_entries(sub2["id"])
        apply(sub2["id"])  # sub2 で差し替え

        assert submission_repo.get_by_id(sub1["id"])["apply_status"] == "pending"
        assert submission_repo.get_by_id(sub2["id"])["apply_status"] == "applied"

        # wish_shifts は sub2 のものに更新
        ws = wish_shift_repo.get_by_period_and_staff(p["id"], s["id"])
        assert len(ws) == 2
        assert all(r["submission_id"] == sub2["id"] for r in ws)

    def test_is_latest_updated_after_replacement(self):
        """差し替え後は新回答のみ is_latest_for_staff=1。"""
        p = _make_period()
        s = _make_staff()
        sub1 = _make_submission(p["id"], staff_id=s["id"], submitted_at="2026-10-01 09:00:00")
        _add_day_entries(sub1["id"])
        apply(sub1["id"])

        sub2 = _make_submission(p["id"], staff_id=s["id"], submitted_at="2026-10-02 10:00:00")
        _add_day_entries(sub2["id"])
        apply(sub2["id"])

        assert submission_repo.get_by_id(sub1["id"])["is_latest_for_staff"] == 0
        assert submission_repo.get_by_id(sub2["id"])["is_latest_for_staff"] == 1

    def test_unlinked_staff_raises(self):
        """staff_id 未解決の回答は ApplyError。"""
        p = _make_period()
        sub = _make_submission(p["id"], staff_id=None)

        with pytest.raises(ApplyError, match="staff_id"):
            apply(sub["id"])

    def test_not_found_raises(self):
        """存在しない submission_id は ApplyError。"""
        with pytest.raises(ApplyError, match="not found"):
            apply(9999)

    def test_rollback_on_error(self, monkeypatch):
        """トランザクション中にエラーが発生した場合、全変更がロールバックされる。"""
        p = _make_period()
        s = _make_staff()
        sub1 = _make_submission(p["id"], staff_id=s["id"], submitted_at="2026-10-01 09:00:00")
        _add_day_entries(sub1["id"])
        apply(sub1["id"])  # sub1 を先に採用

        sub2 = _make_submission(p["id"], staff_id=s["id"], submitted_at="2026-10-02 10:00:00")
        _add_day_entries(sub2["id"])

        # sqlite3.Connection.execute は読み取り専用のためラッパーで代替する
        class _FailAfterN:
            """N 回目以降の execute で OperationalError を発生させるラッパー。"""
            def __init__(self, real_conn, fail_after: int):
                self._conn = real_conn
                self._fail_after = fail_after
                self._count = 0

            def execute(self, sql, params=()):
                self._count += 1
                if self._count >= self._fail_after:
                    raise sqlite3.OperationalError("injected failure")
                return self._conn.execute(sql, params)

            def commit(self):
                return self._conn.commit()

            def rollback(self):
                return self._conn.rollback()

        @contextmanager
        def failing_txn():
            real_conn = get_connection()
            # step1: 旧採用解除 / step2: 新採用 / step3(=fail_after): wish_shifts DELETE で失敗
            wrapper = _FailAfterN(real_conn, fail_after=3)
            try:
                yield wrapper
                real_conn.commit()
            except Exception:
                real_conn.rollback()
                raise

        monkeypatch.setattr(apply_mod, "transaction", failing_txn)

        with pytest.raises(sqlite3.OperationalError):
            apply(sub2["id"])

        # ロールバック確認: sub1 は依然 applied のまま
        assert submission_repo.get_by_id(sub1["id"])["apply_status"] == "applied"
        assert submission_repo.get_by_id(sub2["id"])["apply_status"] == "pending"
        # wish_shifts は sub1 のまま
        ws = wish_shift_repo.get_by_period_and_staff(p["id"], s["id"])
        assert len(ws) == 2
        assert all(r["submission_id"] == sub1["id"] for r in ws)
