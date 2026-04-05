"""祝日・土日祝判定

優先順位:
  1. custom_day_rules（期間別ルール、period_id=対象期間ID）
  2. custom_day_rules（グローバルルール、period_id=0）
  3. jpholiday による自動祝日判定
"""

import datetime

import jpholiday


def is_saturday(date: datetime.date) -> bool:
    return date.weekday() == 5


def is_sunday(date: datetime.date) -> bool:
    return date.weekday() == 6


def is_holiday(date: datetime.date, rules: list[dict] | None = None) -> bool:
    """祝日かどうかを返す（土日は含まない）。

    Args:
        date: 判定対象日
        rules: custom_day_rules のレコードリスト（period_id 問わず当該日のもの）
               優先度: 期間別ルール > グローバルルール > jpholiday
               None または空リストの場合は jpholiday のみで判定する
    """
    rule = _resolve_rule(date, rules)

    if rule is not None:
        if rule["is_custom_holiday"]:
            return True
        if rule["exclude_auto_holiday"]:
            return False  # jpholiday を無効化（土日には影響しない）

    return bool(jpholiday.is_holiday(date))


def is_weekend_or_holiday(date: datetime.date, rules: list[dict] | None = None) -> bool:
    """土日祝（人数不足判定・時給加算で使う「土日祝」）かどうかを返す。"""
    return is_saturday(date) or is_sunday(date) or is_holiday(date, rules)


def get_wage_bonus(
    date: datetime.date,
    saturday_bonus: float,
    sunday_bonus: float,
    holiday_bonus: float,
    rules: list[dict] | None = None,
) -> float:
    """適用する加算額を返す（最優先の1つのみ、複数合算しない）。

    優先順位:
      1. custom_day_rules.wage_bonus（特定日個別加算、非NULLの場合）
      2. is_custom_holiday=1 かつ wage_bonus=NULL → holiday_bonus
      3. jpholiday 祝日 → holiday_bonus
      4. 日曜 → sunday_bonus
      5. 土曜 → saturday_bonus
      6. 平日 → 0
    """
    rule = _resolve_rule(date, rules)

    if rule is not None:
        if rule["wage_bonus"] is not None:
            return float(rule["wage_bonus"])
        if rule["is_custom_holiday"]:
            return holiday_bonus

    # exclude_auto_holiday が True なら jpholiday を無効化
    exclude_auto = rule is not None and bool(rule["exclude_auto_holiday"])

    if not exclude_auto and jpholiday.is_holiday(date):
        return holiday_bonus
    if is_sunday(date):
        return sunday_bonus
    if is_saturday(date):
        return saturday_bonus
    return 0.0


def _resolve_rule(date: datetime.date, rules: list[dict] | None) -> dict | None:
    """当該日に適用するルールを返す（期間別 > グローバル）。"""
    if not rules:
        return None

    date_str = date.strftime("%Y-%m-%d")
    period_rule = None
    global_rule = None

    for r in rules:
        if r["rule_date"] != date_str:
            continue
        if r["period_id"] == 0:
            global_rule = r
        else:
            period_rule = r

    return period_rule if period_rule is not None else global_rule
