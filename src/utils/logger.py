"""エラーログ出力ユーティリティ

保存先: {APP_DIR}/logs/app_error_YYYYMMDD.log
形式: YYYY-MM-DD HH:MM:SS [LEVEL] メッセージ
レベル: ERROR / WARNING / INFO
保持: 直近30日分（古いファイルを自動削除）
"""

import logging
from datetime import datetime, timedelta

from src.utils.paths import APP_DIR

_logger: logging.Logger | None = None
_LOG_DIR = APP_DIR / "logs"
_RETENTION_DAYS = 30


def setup_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    _LOG_DIR.mkdir(exist_ok=True)
    _purge_old_logs()

    log_file = _LOG_DIR / f"app_error_{datetime.now().strftime('%Y%m%d')}.log"

    logger = logging.getLogger("shift_app")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        )
        logger.addHandler(handler)

    _logger = logger
    return _logger


def get_logger() -> logging.Logger:
    if _logger is None:
        return setup_logger()
    return _logger


def _purge_old_logs() -> None:
    cutoff = datetime.now() - timedelta(days=_RETENTION_DAYS)
    for log_file in _LOG_DIR.glob("app_error_*.log"):
        try:
            date_str = log_file.stem.replace("app_error_", "")
            file_date = datetime.strptime(date_str, "%Y%m%d")
            if file_date < cutoff:
                log_file.unlink()
        except (ValueError, OSError):
            pass
