"""credentials.json 起動時チェック・縮退フラグ管理

アプリ起動時に credentials.json の有無を確認し、
Google API が利用可能かどうかを CredentialsStatus として返す。
UI 側はこのフラグを参照して Google 連携ボタンの有効/無効を切り替える。
"""

from dataclasses import dataclass
from pathlib import Path

from src.sheets.auth import load_credentials
from src.utils.paths import APP_DIR

_CREDS_FILENAME = "credentials.json"


@dataclass(frozen=True)
class CredentialsStatus:
    """credentials.json の検証結果。

    Attributes:
        available: True = Google API 利用可能 / False = 縮退モード（ローカル機能のみ）
    """
    available: bool


def check(creds_path: Path | None = None) -> CredentialsStatus:
    """credentials.json の存在と読み込み可能性を確認する。

    Args:
        creds_path: 検証するパス。省略時は APP_DIR/credentials.json を使用。

    Returns:
        CredentialsStatus（available=True なら Google API 利用可能）
    """
    path = creds_path if creds_path is not None else APP_DIR / _CREDS_FILENAME
    creds = load_credentials(path)
    return CredentialsStatus(available=creds is not None)
