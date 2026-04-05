"""起動時DBバックアップ

保存先: {APP_DIR}/backup/shift_app_YYYYMMDD_HHMMSS.db
世代管理: 最新10件を保持し古いものを削除
"""

import shutil
from datetime import datetime
from pathlib import Path

from src.utils.logger import get_logger
from src.utils.paths import APP_DIR

_BACKUP_DIR = APP_DIR / "backup"
_DB_FILE = APP_DIR / "shift_app.db"
_MAX_GENERATIONS = 10


def backup_on_startup() -> Path | None:
    """起動時にDBをバックアップする。DBが存在しない場合は何もしない。

    Returns:
        作成したバックアップファイルのパス。DBが存在しない場合は None。
    """
    logger = get_logger()

    if not _DB_FILE.exists():
        logger.info("No DB file found, skipping backup")
        return None

    _BACKUP_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = _BACKUP_DIR / f"shift_app_{timestamp}.db"

    shutil.copy2(_DB_FILE, dest)
    logger.info("Backup created: %s", dest)

    _rotate_backups()
    return dest


def _rotate_backups() -> None:
    """古いバックアップを削除して最新 _MAX_GENERATIONS 件のみ残す。"""
    logger = get_logger()
    backups = sorted(_BACKUP_DIR.glob("shift_app_*.db"))

    excess = len(backups) - _MAX_GENERATIONS
    for old_file in backups[:excess]:
        try:
            old_file.unlink()
            logger.info("Old backup removed: %s", old_file)
        except OSError as e:
            logger.warning("Failed to remove old backup %s: %s", old_file, e)
