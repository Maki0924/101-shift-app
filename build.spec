# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller ビルド設定（コミット27）

ビルド手順:
    pip install pyinstaller
    pyinstaller build.spec

出力: dist/shift_app.exe（Windows）/ dist/shift_app（macOS/Linux）

注意:
  - credentials.json は同梱しない（配布後にユーザーが手動配置する）
  - shift_app.db / backup / logs も同梱しない（初回起動時に自動生成される）
"""

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# Google API クライアントライブラリは動的インポートが多いため明示的に指定
_google_hidden = (
    collect_submodules("google.auth")
    + collect_submodules("google.oauth2")
    + collect_submodules("googleapiclient")
    + collect_submodules("httplib2")
)

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        # アイコン（実行時には使用しないが assets ごと同梱してもよい）
        # credentials.json は同梱しない（ユーザーが exe と同じフォルダに手動配置）
    ],
    hiddenimports=[
        "tkinter",
        "tkinter.ttk",
        "tkinter.messagebox",
        "tkinter.filedialog",
        "jpholiday",
        "pkg_resources",
        *_google_hidden,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 不要な大型ライブラリを除外してサイズ削減
        "matplotlib",
        "numpy",
        "pandas",
        "PIL",
        "scipy",
        "PyQt5",
        "PyQt6",
        "wx",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="shift_app",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # コンソールウィンドウを表示しない
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",  # Windows exe アイコン
)
