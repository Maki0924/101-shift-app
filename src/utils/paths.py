"""アプリ実行フォルダの解決

- PyInstaller exe 実行時: exe ファイルのあるフォルダ
- 開発時: main.py のあるプロジェクトルート
"""

import sys
from pathlib import Path


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        # PyInstaller でパッケージされた exe 実行時
        return Path(sys.executable).parent
    # 開発時: このファイルは src/utils/ にあるので3階層上がプロジェクトルート
    return Path(__file__).resolve().parent.parent.parent


APP_DIR = get_app_dir()
