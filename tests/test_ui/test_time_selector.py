"""TimeSelector のユニットテスト（コミット21）"""

from src.ui.components.time_selector import float_to_str, str_to_float


class TestStrToFloat:
    def test_empty_returns_none(self):
        assert str_to_float("") is None
        assert str_to_float("  ") is None

    def test_hh_mm_format(self):
        assert str_to_float("9:00") == 9.0
        assert str_to_float("9:30") == 9.5
        assert str_to_float("22:30") == 22.5

    def test_integer_format(self):
        assert str_to_float("9") == 9.0
        assert str_to_float("17") == 17.0

    def test_invalid_returns_none(self):
        assert str_to_float("abc") is None

    def test_9_60_converts_to_10(self):
        # "9:60" は int(9) + 60/60 = 10.0 に変換される
        # 範囲バリデーション（is_valid_time）は TimeSelector._commit が行う
        assert str_to_float("9:60") == 10.0


class TestFloatToStr:
    def test_none_returns_empty(self):
        assert float_to_str(None) == ""

    def test_on_hour(self):
        assert float_to_str(9.0) == "9:00"
        assert float_to_str(17.0) == "17:00"

    def test_half_hour(self):
        assert float_to_str(9.5) == "9:30"
        assert float_to_str(22.5) == "22:30"

    def test_zero(self):
        assert float_to_str(0.0) == "0:00"

    def test_midnight(self):
        assert float_to_str(24.0) == "24:00"
