"""アプリ二重起動防止ロックファイル管理

ロックファイル: {APP_DIR}/shift_app.lock
stale lock 判定: PID が存在しないプロセスの場合のみ stale とみなす
"""

import os

from src.utils.logger import get_logger
from src.utils.paths import APP_DIR

_LOCK_FILE = APP_DIR / "shift_app.lock"


class LockError(Exception):
    pass


def acquire_lock() -> None:
    """ロックファイルを取得する。別プロセスが保持している場合は LockError を送出する。"""
    logger = get_logger()

    if _LOCK_FILE.exists():
        if _is_stale_lock():
            logger.warning("Stale lock detected. Removing: %s", _LOCK_FILE)
            _LOCK_FILE.unlink(missing_ok=True)
        else:
            raise LockError(
                "アプリはすでに起動しています。\n"
                f"別のプロセスがロックファイルを保持しています: {_LOCK_FILE}"
            )

    _LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
    logger.info("Lock acquired (PID=%s)", os.getpid())


def release_lock() -> None:
    """ロックファイルを解放する。"""
    _LOCK_FILE.unlink(missing_ok=True)
    get_logger().info("Lock released")


def _is_stale_lock() -> bool:
    """ロックファイル内の PID が存在しないプロセスなら True を返す。

    PermissionError は「プロセスが存在するが権限なし」を意味するため
    stale とはみなさない（False を返す）。
    """
    try:
        pid = int(_LOCK_FILE.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return True

    try:
        os.kill(pid, 0)
        return False  # プロセスが存在する
    except ProcessLookupError:
        return True  # プロセスが存在しない → stale
    except PermissionError:
        return False  # プロセスは存在するが権限なし → stale ではない
