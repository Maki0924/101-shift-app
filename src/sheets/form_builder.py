"""Google フォーム自動生成

期間情報とスタッフ名一覧からフォームを作成し、
回答先スプレッドシートを生成・リンクする。

フォーム構造:
  セクション1（共通）: スタッフ名 / 週何回希望 / 備考 / 入力方式（A/B 分岐）
  セクションA（モードA）: 日別開始・終了時刻
  セクションB（モードB）: 日別午前不可・午後不可チェックボックス

セクション分岐は 2 パスで実装する:
  Pass1 — 全アイテムを作成（入力方式にナビなし）
  Pass2 — GET でセクションIDを取得し、入力方式のナビゲーションを更新
"""

import datetime

from src.db.repositories import period_repo
from src.utils.logger import get_logger

# セクションA 完了後はセクションBをスキップして提出する
_SECTION_A_GOTO = "SUBMIT_FORM"


# ── 内部ヘルパー ──────────────────────────────────────────────────────────────

def _date_labels(start_date: str, end_date: str) -> list[str]:
    """MM/DD 形式の日付ラベルリストを返す。"""
    start = datetime.date.fromisoformat(start_date)
    end = datetime.date.fromisoformat(end_date)
    labels = []
    d = start
    while d <= end:
        labels.append(d.strftime("%m/%d"))
        d += datetime.timedelta(days=1)
    return labels


def _create_req(item: dict, index: int) -> dict:
    return {"createItem": {"item": item, "location": {"index": index}}}


def _build_pass1_requests(staff_names: list[str], labels: list[str]) -> list[dict]:
    """Pass1 用リクエストリストを返す。入力方式のナビゲーションは未設定。"""
    reqs = []
    idx = 0

    # ── 共通セクション ────────────────────────────────────────────────────────
    reqs.append(_create_req({
        "title": "スタッフ名",
        "questionItem": {"question": {
            "required": True,
            "choiceQuestion": {
                "type": "DROP_DOWN",
                "options": [{"value": n} for n in staff_names],
            },
        }},
    }, idx))
    idx += 1

    reqs.append(_create_req({
        "title": "週何回希望",
        "questionItem": {"question": {"textQuestion": {}}},
    }, idx))
    idx += 1

    reqs.append(_create_req({
        "title": "備考",
        "questionItem": {"question": {"textQuestion": {"paragraph": True}}},
    }, idx))
    idx += 1

    # 入力方式（Pass2 でナビゲーションを追記する）
    reqs.append(_create_req({
        "title": "入力方式",
        "questionItem": {"question": {
            "required": True,
            "choiceQuestion": {
                "type": "RADIO",
                "options": [{"value": "mode_a"}, {"value": "mode_b"}],
            },
        }},
    }, idx))
    idx += 1

    # ── セクションA（モードA）────────────────────────────────────────────────
    reqs.append(_create_req({
        "title": "モードA: 入れる日時を入力",
        "pageBreakItem": {"goToAction": _SECTION_A_GOTO},
    }, idx))
    idx += 1

    for label in labels:
        reqs.append(_create_req({
            "title": f"{label}_開始",
            "questionItem": {"question": {"textQuestion": {}}},
        }, idx))
        idx += 1
        reqs.append(_create_req({
            "title": f"{label}_終了",
            "questionItem": {"question": {"textQuestion": {}}},
        }, idx))
        idx += 1

    # ── セクションB（モードB）────────────────────────────────────────────────
    reqs.append(_create_req({
        "title": "モードB: 入れない時間を選ぶ",
        "pageBreakItem": {},
    }, idx))
    idx += 1

    for label in labels:
        reqs.append(_create_req({
            "title": f"{label}_午前不可",
            "questionItem": {"question": {
                "choiceQuestion": {
                    "type": "CHECKBOX",
                    "options": [{"value": "入れない"}],
                },
            }},
        }, idx))
        idx += 1
        reqs.append(_create_req({
            "title": f"{label}_午後不可",
            "questionItem": {"question": {
                "choiceQuestion": {
                    "type": "CHECKBOX",
                    "options": [{"value": "入れない"}],
                },
            }},
        }, idx))
        idx += 1

    return reqs


def _extract_section_ids(form: dict) -> tuple[str | None, str | None]:
    """フォームのアイテムリストからセクションA・Bの itemId を返す。"""
    section_a_id = None
    section_b_id = None
    for item in form.get("items", []):
        title = item.get("title", "")
        if "pageBreakItem" in item:
            if title.startswith("モードA"):
                section_a_id = item["itemId"]
            elif title.startswith("モードB"):
                section_b_id = item["itemId"]
    return section_a_id, section_b_id


def _extract_mode_item(form: dict) -> tuple[str | None, str | None, int | None]:
    """「入力方式」アイテムの (itemId, questionId, index) を返す。"""
    for idx, item in enumerate(form.get("items", [])):
        if item.get("title") == "入力方式":
            q_id = item.get("questionItem", {}).get("question", {}).get("questionId")
            return item.get("itemId"), q_id, idx
    return None, None, None


# ── 公開 API ──────────────────────────────────────────────────────────────────

def build(
    period: dict,
    staff_names: list[str],
    forms_service,
    sheets_service,
    drive_service,
) -> tuple[str, str]:
    """フォームを作成して (form_url, spreadsheet_id) を返す。

    Args:
        period: periods レコード（name / start_date / end_date を使用）
        staff_names: プルダウン候補のスタッフ名リスト
        forms_service: Forms API v1 サービス
        sheets_service: Sheets API v4 サービス
        drive_service: Drive API v3 サービス

    Returns:
        (form_url, spreadsheet_id)

    Raises:
        googleapiclient.errors.HttpError: API エラー時
    """
    title = f"シフト希望【{period['name']}】"
    labels = _date_labels(period["start_date"], period["end_date"])

    # 1. フォーム作成
    form = forms_service.forms().create(body={"info": {"title": title}}).execute()
    form_id = form["formId"]
    form_url = f"https://docs.google.com/forms/d/{form_id}/viewform"
    get_logger().info("form created: %s", form_id)

    # Pass1: 全アイテムを追加
    requests = _build_pass1_requests(staff_names, labels)
    forms_service.forms().batchUpdate(
        formId=form_id,
        body={"requests": requests},
    ).execute()

    # Pass2: セクションIDを取得し、入力方式のナビゲーションを更新
    form_detail = forms_service.forms().get(formId=form_id).execute()
    section_a_id, section_b_id = _extract_section_ids(form_detail)
    item_id, q_id, item_idx = _extract_mode_item(form_detail)

    if section_a_id and section_b_id and item_id and q_id and item_idx is not None:
        forms_service.forms().batchUpdate(
            formId=form_id,
            body={"requests": [{
                "updateItem": {
                    "item": {
                        "itemId": item_id,
                        "title": "入力方式",
                        "questionItem": {"question": {
                            "questionId": q_id,
                            "required": True,
                            "choiceQuestion": {
                                "type": "RADIO",
                                "options": [
                                    {"value": "mode_a", "goToSectionId": section_a_id},
                                    {"value": "mode_b", "goToSectionId": section_b_id},
                                ],
                            },
                        }},
                    },
                    "location": {"index": item_idx},
                    "updateMask": "questionItem.question.choiceQuestion.options",
                },
            }]},
        ).execute()
        get_logger().info("section navigation updated (form %s)", form_id)
    else:
        get_logger().warning("section navigation skipped: section IDs not found (form %s)", form_id)

    # 2. 回答先スプレッドシートを生成
    # NOTE: Forms API v1 の updateSettings は quizSettings のみ対応しており、
    # 回答先スプレッドシートのプログラム的リンクは現時点で非対応。
    # フォーム作成後に Google Forms UI から手動でスプレッドシートをリンクするか、
    # 将来的な API 対応を待って実装を追加すること。
    sheet_title = f"シフト希望回答【{period['name']}】"
    spreadsheet = sheets_service.spreadsheets().create(
        body={"properties": {"title": sheet_title}}
    ).execute()
    spreadsheet_id = spreadsheet["spreadsheetId"]
    get_logger().info("response spreadsheet created: %s", spreadsheet_id)

    # サービスアカウントがスプレッドシートの作成者のためオーナー権限を既に保有している。
    # 自身への permissions().create() は不要。

    return form_url, spreadsheet_id


def create_and_register(
    period_id: int,
    staff_names: list[str],
    forms_service,
    sheets_service,
    drive_service,
) -> None:
    """フォームを作成し、form_url / spreadsheet_id を期間レコードに登録する。

    失敗時は例外を呼び出し元に伝播させる（ローカルDBはロールバックしない）。

    Args:
        period_id: 対象期間ID
        staff_names: プルダウン候補のスタッフ名リスト
        forms_service: Forms API v1 サービス
        sheets_service: Sheets API v4 サービス
        drive_service: Drive API v3 サービス

    Raises:
        ValueError: 期間が見つからない場合
        googleapiclient.errors.HttpError: API エラー時
    """
    period = period_repo.get_by_id(period_id)
    if period is None:
        raise ValueError(f"period {period_id} not found")

    form_url, spreadsheet_id = build(
        period, staff_names, forms_service, sheets_service, drive_service
    )
    period_repo.update_form_info(period_id, form_url, spreadsheet_id)
    get_logger().info("form registered to period %d: %s", period_id, form_url)
