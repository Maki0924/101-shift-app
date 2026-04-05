"""週何回希望テキストのパース

テキスト → (min, max) に変換する。パース不能は (None, None) を返す。
"""

import re

from src.utils.logger import get_logger

# 許容パターン（全て半角数字・記号のみ）
_PATTERN_EXACT = re.compile(r"^([0-9]+)$")                   # 例: "3"
_PATTERN_RANGE = re.compile(r"^([0-9]+)[-〜]([0-9]+)$")          # 例: "1-2" / "1〜2"
_PATTERN_MIN_ONLY = re.compile(r"^([0-9]+)(?:以上|\+)$")      # 例: "5以上" / "5+"


def parse(text: str | None) -> tuple[int | None, int | None]:
    """週何回希望テキストをパースして (min, max) を返す。

    Returns:
        (None, None): 空欄またはパース不能
        (n, n):       固定回数（例: "3" → (3, 3)）
        (n, m):       範囲（例: "1-2" → (1, 2)）
        (n, None):    下限のみ（例: "5以上" → (5, None)）
    """
    if text is None:
        return (None, None)

    stripped = text.strip()
    if not stripped:
        return (None, None)

    m = _PATTERN_EXACT.match(stripped)
    if m:
        n = int(m.group(1))
        return (n, n)

    m = _PATTERN_RANGE.match(stripped)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo > hi:
            get_logger().warning("weekly_pref parse: min > max in '%s'", stripped)
            return (None, None)
        return (lo, hi)

    m = _PATTERN_MIN_ONLY.match(stripped)
    if m:
        return (int(m.group(1)), None)

    get_logger().warning("weekly_pref parse: unparseable '%s'", stripped)
    return (None, None)
