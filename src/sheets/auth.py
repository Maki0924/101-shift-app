"""Google サービスアカウント認証

credentials.json の存在チェックと認証情報の生成を行う。
ファイル不在・読み込みエラー時は None を返し、呼び出し元が縮退モードに移行する。
"""

from pathlib import Path

from google.oauth2 import service_account

from src.utils.logger import get_logger

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/drive",
]


def load_credentials(creds_path: Path) -> service_account.Credentials | None:
    """サービスアカウント認証情報を返す。

    Args:
        creds_path: credentials.json のパス

    Returns:
        認証情報オブジェクト。ファイル不在または読み込み失敗時は None。
    """
    if not creds_path.exists():
        get_logger().info("credentials.json not found: %s", creds_path)
        return None
    try:
        creds = service_account.Credentials.from_service_account_file(
            str(creds_path), scopes=SCOPES
        )
        get_logger().info("credentials.json loaded: %s", creds_path)
        return creds
    except Exception:
        get_logger().warning("credentials.json load failed: %s", creds_path, exc_info=True)
        return None
