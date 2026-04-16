"""printer._write_preview_html のユニットテスト

専用一時ディレクトリへの書き出し・古いファイルの掃除・
OSError 耐性の3ケースを押さえる。
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

import pytest

from src.logic.printer import _PREVIEW_DIR_NAME, _write_preview_html


@pytest.fixture()
def preview_dir(tmp_path, monkeypatch):
    """_write_preview_html が使う一時ディレクトリを tmp_path 以下に差し替える。"""
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    return tmp_path / _PREVIEW_DIR_NAME


class TestWritePreviewHtml:
    def test_new_file_is_created(self, preview_dir):
        """呼び出し後に preview.html が生成され、内容とパスが一致する。"""
        result = _write_preview_html("<html>test</html>")

        out = preview_dir / "preview.html"
        assert out.exists()
        assert out.read_text(encoding="utf-8") == "<html>test</html>"
        assert str(out) == result

    def test_old_html_files_are_deleted(self, preview_dir):
        """既存の *.html が掃除されてから新ファイルが書き出される。"""
        preview_dir.mkdir(parents=True, exist_ok=True)
        old1 = preview_dir / "old1.html"
        old2 = preview_dir / "old2.html"
        old1.write_text("old1")
        old2.write_text("old2")

        _write_preview_html("<html>new</html>")

        assert not old1.exists()
        assert not old2.exists()
        assert (preview_dir / "preview.html").read_text(encoding="utf-8") == "<html>new</html>"

    def test_oserror_on_delete_does_not_abort_write(self, preview_dir):
        """古いファイルの削除で OSError が出ても書き込みは継続される。"""
        preview_dir.mkdir(parents=True, exist_ok=True)
        old = preview_dir / "locked.html"
        old.write_text("locked")

        with mock.patch.object(Path, "unlink", side_effect=OSError("locked")):
            result = _write_preview_html("<html>safe</html>")

        out = preview_dir / "preview.html"
        assert out.exists()
        assert out.read_text(encoding="utf-8") == "<html>safe</html>"
        assert str(out) == result
