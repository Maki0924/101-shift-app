"""DB初期化

DDLを実行してテーブルを作成し、app_settings の初期行（id=1）を投入する。
"""

from src.db.connection import get_connection, transaction
from src.db.schema import ALL_DDL
from src.utils.logger import get_logger


def init_db() -> None:
    """全テーブルを作成し、app_settings 初期行を投入する。"""
    logger = get_logger()
    conn = get_connection()

    for ddl in ALL_DDL:
        conn.execute(ddl)
    conn.commit()
    logger.info("All tables created (IF NOT EXISTS)")

    _insert_default_settings()


def _insert_default_settings() -> None:
    """app_settings の初期行（id=1）が存在しない場合のみ投入する。"""
    logger = get_logger()
    conn = get_connection()

    exists = conn.execute("SELECT 1 FROM app_settings WHERE id = 1").fetchone()
    if exists:
        logger.info("app_settings id=1 already exists, skipping")
        return

    with transaction() as txn:
        txn.execute(
            """
            INSERT INTO app_settings (
                id, schema_version,
                day_shift_start, day_shift_end,
                night_shift_start, night_shift_end,
                overlap_hours_threshold,
                saturday_bonus, sunday_bonus, holiday_bonus,
                weekday_day_min_staff, weekday_night_min_staff,
                weekend_day_min_staff, weekend_night_min_staff,
                print_font_size,
                created_at, updated_at
            ) VALUES (
                1, 1,
                8, 17,
                17, 22,
                2,
                100, 100, 100,
                2, 2,
                5, 3,
                9,
                datetime('now', 'localtime'), datetime('now', 'localtime')
            )
            """
        )
    logger.info("app_settings id=1 inserted with defaults")
