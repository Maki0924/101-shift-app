"""printer._write_preview_html のユニットテスト

- uuid ファイル名で一意になること
- 連続2回呼ぶと別ファイルになること
- mtime が古いファイルだけ掃除され、新しいファイルは残ること
- 削除で OSError が出ても書き込みは継続されること
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from unittest import mock

import pytest

from src.logic.printer import _PREVIEW_DIR_NAME, _PREVIEW_MAX_AGE_SECONDS, _write_preview_html


@pytest.fixture()
def preview_dir(tmp_path, monkeypatch):
    """_write_preview_html が使う一時ディレクトリを tmp_path 以下に差し替える。"""
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    return tmp_path / _PREVIEW_DIR_NAME


def _set_mtime_old(path: Path, age_seconds: int = _PREVIEW_MAX_AGE_SECONDS + 1) -> None:
    """ファイルの mtime を age_seconds 秒前に設定する。"""
    old_time = time.time() - age_seconds
    os.utime(path, (old_time, old_time))


class TestWritePreviewHtml:
    def test_new_file_is_created(self, preview_dir):
        """呼び出し後にプレビュー HTML が生成され、内容とパスが一致する。"""
        result = _write_preview_html("<html>test</html>")

        out = Path(result)
        assert out.exists()
        assert out.read_text(encoding="utf-8") == "<html>test</html>"
        assert out.parent == preview_dir

    def test_two_calls_produce_different_files(self, preview_dir):
        """連続2回呼ぶと uuid の異なる別ファイルが生成される。"""
        path1 = _write_preview_html("<html>first</html>")
        path2 = _write_preview_html("<html>second</html>")

        assert path1 != path2
        # どちらも mtime が新しいため掃除されず両方残る
        assert Path(path1).exists()
        assert Path(path2).exists()

    def test_only_old_files_are_deleted(self, preview_dir):
        """mtime が古いファイルだけ掃除され、新しいファイルは残る。"""
        preview_dir.mkdir(parents=True, exist_ok=True)

        old_file = preview_dir / "old_preview.html"
        old_file.write_text("old")
        _set_mtime_old(old_file)  # 閾値超えに設定

        recent_file = preview_dir / "recent_preview.html"
        recent_file.write_text("recent")
        # recent_file は mtime を変更しない（現在時刻のまま）

        _write_preview_html("<html>new</html>")

        assert not old_file.exists()  # 古いファイルは削除
        assert recent_file.exists()  # 新しいファイルは残る

    def test_oserror_on_delete_does_not_abort_write(self, preview_dir):
        """削除で OSError が出ても書き込みは継続される。"""
        preview_dir.mkdir(parents=True, exist_ok=True)

        old_file = preview_dir / "locked.html"
        old_file.write_text("locked")
        _set_mtime_old(old_file)  # 掃除対象になる mtime に設定

        with mock.patch.object(Path, "unlink", side_effect=OSError("locked")):
            result = _write_preview_html("<html>safe</html>")

        out = Path(result)
        assert out.exists()
        assert out.read_text(encoding="utf-8") == "<html>safe</html>"
