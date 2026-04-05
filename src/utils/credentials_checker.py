"""credentials.json 起動時チェック・縮退フラグ管理

アプリ起動時に credentials.json の有無を確認し、
Google API が利用可能かどうかを CredentialsStatus として返す。
UI 側はこのフラグを参照して Google 連携ボタンの有効/無効を切り替える。
"""

from dataclasses import dataclass
from pathlib import Path

from src.db.repositories import settings_repo
from src.sheets.auth import load_credentials
from src.utils.paths import APP_DIR

_DEFAULT_CREDS_FILENAME = "credentials.json"


@dataclass(frozen=True)
class CredentialsStatus:
    """credentials ファイルの検証結果。

    Attributes:
        available: True = Google API 利用可能 / False = 縮退モード（ローカル機能のみ）
    """
    available: bool


def check(creds_path: Path | None = None) -> CredentialsStatus:
    """credentials ファイルの存在と読み込み可能性を確認する。

    ファイル名は app_settings.credentials_filename から取得する。
    creds_path を明示した場合はそのパスを優先する（テスト用）。

    Args:
        creds_path: 検証するパス。省略時は APP_DIR/<settings.credentials_filename> を使用。

    Returns:
        CredentialsStatus（available=True なら Google API 利用可能）
    """
    if creds_path is None:
        settings = settings_repo.get()
        filename = (
            settings["credentials_filename"]
            if settings and settings.get("credentials_filename")
            else _DEFAULT_CREDS_FILENAME
        )
        creds_path = APP_DIR / filename

    creds = load_credentials(creds_path)
    return CredentialsStatus(available=creds is not None)
