"""Google API サービスオブジェクト生成ラッパー

認証済み Credentials から Sheets / Forms / Drive の API サービスを生成する。
"""

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


def build_sheets(creds: Credentials):
    """Sheets API v4 サービスを返す。"""
    return build("sheets", "v4", credentials=creds)


def build_forms(creds: Credentials):
    """Forms API v1 サービスを返す。"""
    return build("forms", "v1", credentials=creds)


def build_drive(creds: Credentials):
    """Drive API v3 サービスを返す。"""
    return build("drive", "v3", credentials=creds)
