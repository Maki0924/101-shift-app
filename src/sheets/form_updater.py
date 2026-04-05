"""スタッフマスター更新時のフォームプルダウン自動更新

collecting ステータスの期間のフォームのスタッフ名プルダウンを更新する。
一部失敗しても他の期間への更新を継続し、失敗一覧を返す。
"""

from src.db.repositories import period_repo
from src.utils.logger import get_logger


def _extract_form_id(form_url: str) -> str | None:
    """form_url から form_id を抽出する。

    例: https://docs.google.com/forms/d/{form_id}/viewform → form_id
    """
    try:
        return form_url.split("/d/")[1].split("/")[0]
    except (IndexError, AttributeError):
        return None


def _find_staff_question(form: dict) -> tuple[str | None, str | None, int | None]:
    """「スタッフ名」アイテムの (itemId, questionId, index) を返す。"""
    for idx, item in enumerate(form.get("items", [])):
        if item.get("title") == "スタッフ名":
            q_id = item.get("questionItem", {}).get("question", {}).get("questionId")
            return item.get("itemId"), q_id, idx
    return None, None, None


def update_all(staff_names: list[str], forms_service) -> list[dict]:
    """collecting ステータスの全期間のフォームプルダウンを更新する。

    - form_url が未登録の期間はスキップする（正常状態）
    - 1 期間で失敗しても他の期間への更新を継続する

    Args:
        staff_names: 新しいスタッフ名リスト
        forms_service: Forms API v1 サービス

    Returns:
        失敗した期間のリスト。各要素は {"period_id": int, "name": str, "error": str}
    """
    periods = period_repo.get_by_status("collecting")
    failures = []

    for period in periods:
        form_url = period.get("form_url")
        if not form_url:
            continue

        form_id = _extract_form_id(form_url)
        if not form_id:
            get_logger().warning("invalid form_url for period %d: %s", period["id"], form_url)
            continue

        try:
            form = forms_service.forms().get(formId=form_id).execute()
            item_id, q_id, item_idx = _find_staff_question(form)

            if item_id is None or q_id is None or item_idx is None:
                msg = f"staff question not found in form {form_id}"
                get_logger().warning("%s (period %d)", msg, period["id"])
                failures.append({"period_id": period["id"], "name": period["name"], "error": msg})
                continue

            forms_service.forms().batchUpdate(
                formId=form_id,
                body={"requests": [{
                    "updateItem": {
                        "item": {
                            "itemId": item_id,
                            "title": "スタッフ名",
                            "questionItem": {"question": {
                                "questionId": q_id,
                                "required": True,
                                "choiceQuestion": {
                                    "type": "DROP_DOWN",
                                    "options": [{"value": n} for n in staff_names],
                                },
                            }},
                        },
                        "location": {"index": item_idx},
                        "updateMask": "questionItem.question.choiceQuestion.options",
                    },
                }]},
            ).execute()
            get_logger().info(
                "staff choices updated: period %d (form %s)", period["id"], form_id
            )

        except Exception as e:
            get_logger().warning(
                "failed to update form for period %d: %s", period["id"], e, exc_info=True
            )
            failures.append({"period_id": period["id"], "name": period["name"], "error": str(e)})

    return failures
