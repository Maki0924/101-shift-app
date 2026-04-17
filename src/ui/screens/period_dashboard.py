"""期間ダッシュボード

期間情報サマリー・進捗カード・ステータス遷移・手動同期・警告インジケーターを提供する。
"""

import threading
import tkinter as tk
from tkinter import ttk

from src.db.repositories import period_repo, settings_repo, staff_repo, submission_repo
from src.sheets import auth, client
from src.sheets import form_builder as form_builder_mod
from src.ui.app import STATUS_LABELS
from src.ui.components.dialogs import ask_confirm, show_error
from src.utils.logger import get_logger
from src.utils.paths import APP_DIR


class PeriodDashboardScreen(ttk.Frame):
    def __init__(self, master: tk.Misc, app, period_id: int, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.app = app
        self._period_id = period_id
        self._period: dict | None = None  # _load() 失敗時でも属性を保証する
        self._build()
        self._load()

    # ── 画面構築 ──────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # ── ヘッダー ──
        header = ttk.Frame(self)
        header.pack(fill="x", padx=20, pady=(16, 0))
        self._title_label = ttk.Label(header, text="", font=("", 16))
        self._title_label.pack(side="left")
        ttk.Button(header, text="← 戻る", command=self._on_back).pack(side="right")
        self._edit_period_btn = ttk.Button(header, text="期間を編集", command=self._on_edit_period)
        self._edit_period_btn.pack(side="right", padx=(0, 8))

        # ── 期間情報 ──
        info = ttk.LabelFrame(self, text="期間情報", padding=10)
        info.pack(fill="x", padx=20, pady=8)
        self._info_label = ttk.Label(info, text="")
        self._info_label.pack(anchor="w")

        # ── 進捗サマリー ──
        progress = ttk.LabelFrame(self, text="進捗", padding=10)
        progress.pack(fill="x", padx=20, pady=4)
        self._progress_label = ttk.Label(progress, text="")
        self._progress_label.pack(anchor="w")

        # ── 警告インジケーター（コンテナを常に pack し、子の表示で高さを制御）──
        warn_container = ttk.Frame(self)
        warn_container.pack(fill="x", padx=20, pady=(0, 4))
        self._warn_btn = ttk.Button(warn_container, text="⚠ 警告があります", command=self._on_show_warnings)

        # ── ステータス遷移ボタン ──
        status_frame = ttk.LabelFrame(self, text="ステータス操作", padding=10)
        status_frame.pack(fill="x", padx=20, pady=4)
        self._start_edit_btn = ttk.Button(status_frame, text="編集開始", command=self._on_start_editing, width=14)
        self._archive_btn = ttk.Button(status_frame, text="アーカイブ", command=self._on_archive, width=14)
        self._unarchive_btn = ttk.Button(status_frame, text="アーカイブ解除", command=self._on_unarchive, width=14)

        # ── アクションボタン ──
        action_frame = ttk.LabelFrame(self, text="操作", padding=10)
        action_frame.pack(fill="x", padx=20, pady=4)

        row1 = ttk.Frame(action_frame)
        row1.pack(fill="x", pady=(0, 4))
        # Sheets同期・フォーム自動生成はスタブ（google-api統合後に有効化）
        self._sync_btn = ttk.Button(row1, text="Sheets同期", command=self._on_manual_sync, width=16)
        self._sync_btn.pack(side="left", padx=(0, 6))
        self._form_btn = ttk.Button(row1, text="フォーム自動生成", command=self._on_create_form, width=16)
        self._form_btn.pack(side="left")

        row2 = ttk.Frame(action_frame)
        row2.pack(fill="x")
        for label, cmd in [
            ("回答受信一覧", self._on_submission_list),
            ("シフト編集", self._on_shift_edit),
            ("印刷", self._on_print),
            ("希望検索", self._on_wish_search),
        ]:
            ttk.Button(row2, text=label, command=cmd, width=14).pack(side="left", padx=(0, 6))

        # ── form_url / spreadsheet_id 手動設定 ──
        url_frame = ttk.LabelFrame(self, text="Google連携設定（手動）", padding=10)
        url_frame.pack(fill="x", padx=20, pady=4)

        for row_idx, (lbl, key) in enumerate(
            [("フォームURL", "form_url"), ("スプレッドシートID", "spreadsheet_id")],
            start=0,
        ):
            ttk.Label(url_frame, text=lbl, width=20, anchor="e").grid(
                row=row_idx, column=0, sticky="e", padx=(0, 6), pady=3
            )
            entry = ttk.Entry(url_frame, width=50)
            entry.grid(row=row_idx, column=1, sticky="w", pady=3)
            setattr(self, f"_{key}_entry", entry)

        ttk.Button(url_frame, text="保存", command=self._on_save_form_info, width=10).grid(
            row=2, column=1, sticky="w", pady=(6, 0)
        )

    # ── データ読み込み・UI更新 ─────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            period = period_repo.get_by_id(self._period_id)
        except Exception as e:
            get_logger().error("期間の読み込みに失敗: %s", e, exc_info=True)
            show_error(self, "期間情報の読み込みに失敗しました。")
            return

        if period is None:
            show_error(self, "期間が見つかりません。")
            return

        self._period = period
        status_label = STATUS_LABELS.get(period["status"], period["status"])
        self._title_label.configure(text=f"{period['name']}  [{status_label}]")
        self._info_label.configure(
            text=f"対象期間: {period['start_date']} 〜 {period['end_date']}　提出期限: {period['submission_deadline']}"
        )

        # 進捗サマリー
        try:
            subs = submission_repo.get_by_period(self._period_id)
            total = len(subs)
            applied = sum(1 for s in subs if s["apply_status"] == "applied")
            unlinked = sum(1 for s in subs if not s["staff_id"])

            part_time = staff_repo.get_all_part_time_active()
            applied_ids = {s["staff_id"] for s in subs if s["staff_id"] and s["apply_status"] == "applied"}
            unsubmitted = sum(1 for s in part_time if s["id"] not in applied_ids)

            self._progress_label.configure(
                text=(
                    f"回答件数: {total}件　採用済み: {applied}件　未提出バイト: {unsubmitted}人　未紐付け: {unlinked}件"
                )
            )
        except Exception as e:
            get_logger().error("進捗読み込みに失敗: %s", e, exc_info=True)
            self._progress_label.configure(text="進捗の読み込みに失敗")

        # 警告インジケーター（コンテナ内で pack/pack_forget するため位置は固定）
        has_warnings = any(w.period_id == self._period_id for w in self.app.warnings)
        if has_warnings:
            self._warn_btn.pack(anchor="w")
        else:
            self._warn_btn.pack_forget()

        # form_url / spreadsheet_id
        self._form_url_entry.delete(0, "end")
        self._form_url_entry.insert(0, period.get("form_url") or "")
        self._spreadsheet_id_entry.delete(0, "end")
        self._spreadsheet_id_entry.insert(0, period.get("spreadsheet_id") or "")

        self._update_buttons(period["status"])

    def _update_buttons(self, status: str) -> None:
        """ステータスに応じてボタンの表示・disabled 状態を更新する。"""
        is_archived = status == "archived"

        # ステータス遷移ボタン
        self._start_edit_btn.pack_forget()
        self._archive_btn.pack_forget()
        self._unarchive_btn.pack_forget()

        if status == "collecting":
            self._start_edit_btn.pack(side="left", padx=(0, 6))
            self._archive_btn.pack(side="left", padx=(0, 6))
        elif status == "editing":
            self._archive_btn.pack(side="left", padx=(0, 6))
        elif status == "archived":
            self._unarchive_btn.pack(side="left", padx=(0, 6))

        # 期間を編集: archived では不許可（データ整合性のため）
        # 正規フロー: アーカイブ解除 → editing で編集 → 再アーカイブ
        self._edit_period_btn.configure(state="disabled" if is_archived else "normal")

        # Sheets同期・フォーム自動生成: credentials がある場合のみ有効
        api_ok = self.app.creds_available and not is_archived
        self._sync_btn.configure(state="disabled")  # 手動同期は引き続きスタブ
        self._form_btn.configure(state="normal" if api_ok else "disabled")

    # ── ステータス遷移 ────────────────────────────────────────────────────────

    def _on_start_editing(self) -> None:
        self._change_status("editing")

    def _on_archive(self) -> None:
        if ask_confirm(self, "この期間をアーカイブしますか？\nアーカイブ後は原則として編集できなくなります。"):
            self._change_status("archived")

    def _on_unarchive(self) -> None:
        self._change_status("editing")

    def _change_status(self, new_status: str) -> None:
        try:
            period_repo.update_status(self._period_id, new_status)
        except Exception as e:
            get_logger().error("ステータス更新に失敗: %s", e, exc_info=True)
            show_error(self, "ステータスの更新に失敗しました。")
            return
        self._load()

    # ── 手動同期（stub）────────────────────────────────────────────────────────

    def _on_manual_sync(self) -> None:
        """手動Sheets同期（stub: no-op）。

        NOTE: 実接続に差し替える際、すべてのUI操作は app.post_to_ui(...) 経由で行うこと。
        ワーカースレッドから after() を直接呼ぶことは禁止（スレッド安全性の問題）。
        """
        self._sync_btn.configure(state="disabled")
        threading.Thread(target=self._sync_worker, daemon=True).start()

    def _sync_worker(self) -> None:
        self.app.post_to_ui(lambda: self.app.status_bar.set_sync_message("同期中…"))
        # TODO: 実接続に差し替える（collecting / editing 全期間を順次同期）
        self.app.post_to_ui(lambda: self.app.status_bar.set_sync_message(""))
        self.app.post_to_ui(self._on_sync_done)

    def _on_sync_done(self) -> None:
        # 同期中に画面遷移が起きると self が破棄されている可能性があるため確認する
        if not self.winfo_exists():
            return
        # _update_buttons() が _sync_btn 状態を上書きするが、_load() 失敗時のフォールバックとして先に設定
        self._sync_btn.configure(state="disabled")  # スタブのため常に disabled
        self._load()

    # ── Google連携設定保存 ────────────────────────────────────────────────────

    def _on_save_form_info(self) -> None:
        form_url = self._form_url_entry.get().strip() or None
        spreadsheet_id = self._spreadsheet_id_entry.get().strip() or None
        try:
            period_repo.update_form_info(self._period_id, form_url, spreadsheet_id)
        except Exception as e:
            get_logger().error("Google連携設定の保存に失敗: %s", e, exc_info=True)
            show_error(self, "保存に失敗しました。")
            return
        self._load()

    # ── フォーム自動生成 ──────────────────────────────────────────────────────

    def _on_create_form(self) -> None:
        """フォーム自動生成ボタン: バックグラウンドスレッドで Google API を呼び出す。"""
        if self._period is None:
            return
        if self._period.get("form_url"):
            if not ask_confirm(
                self,
                "すでにフォームURLが登録されています。\n上書きして新しいフォームを作成しますか？",
            ):
                return

        self._form_btn.configure(state="disabled")
        self.app.status_bar.set_sync_message("フォーム作成中…")
        threading.Thread(target=self._form_worker, daemon=True).start()

    def _form_worker(self) -> None:
        """フォーム作成処理（ワーカースレッド）。UI 操作は post_to_ui 経由のみ。"""
        try:
            # credentials ロード
            app_settings = settings_repo.get()
            creds_filename = (
                app_settings["credentials_filename"]
                if app_settings and app_settings.get("credentials_filename")
                else "credentials.json"
            )
            creds = auth.load_credentials(APP_DIR / creds_filename)
            if creds is None:
                msg = f"{creds_filename} が見つかりません。\nexe と同じフォルダに配置してください。"
                self.app.post_to_ui(lambda: self._on_form_error(msg))
                return

            # API サービス構築
            forms_svc = client.build_forms(creds)
            sheets_svc = client.build_sheets(creds)
            drive_svc = client.build_drive(creds)

            # スタッフ名一覧（並び順通り）
            staff_list = staff_repo.get_for_period(self._period_id)
            staff_names = [s["name"] for s in staff_list]

            # フォーム作成 & DB 登録
            form_builder_mod.create_and_register(self._period_id, staff_names, forms_svc, sheets_svc, drive_svc)

            self.app.post_to_ui(self._on_form_done)

        except Exception as e:
            get_logger().error("フォーム自動生成に失敗: %s", e, exc_info=True)
            msg = str(e)
            self.app.post_to_ui(lambda: self._on_form_error(msg))

    def _on_form_done(self) -> None:
        """フォーム作成成功時の UI 更新（メインスレッド）。"""
        if not self.winfo_exists():
            return
        self.app.status_bar.set_sync_message("")
        self._load()
        # 最新の form_url をダイアログで案内
        period = period_repo.get_by_id(self._period_id)
        url = period.get("form_url") if period else None
        msg = f"フォームを作成しました。\n\nフォームURL:\n{url}" if url else "フォームを作成しました。"
        show_error(self, msg, title="フォーム作成完了")

    def _on_form_error(self, message: str) -> None:
        """フォーム作成失敗時の UI 更新（メインスレッド）。"""
        if not self.winfo_exists():
            return
        self.app.status_bar.set_sync_message("")
        # _load() で期間の現ステータスからボタン状態を再設定する
        # （処理中にアーカイブ等の状態変化があっても正しく反映される）
        self._load()
        show_error(self, f"フォームの作成に失敗しました。\n\n{message}")

    # ── 警告一覧 ────────────────────────────────────────────────────────────

    def _on_show_warnings(self) -> None:
        """全警告一覧をダイアログで表示する（期間名列を含む）。"""
        if not self.app.warnings:
            show_error(self, "警告はありません。", title="警告一覧")
            return

        try:
            all_periods = {p["id"]: p["name"] for p in period_repo.get_all()}
        except Exception as e:
            get_logger().error("警告一覧の期間名取得に失敗: %s", e, exc_info=True)
            all_periods = {}

        lines = []
        for w in self.app.warnings:
            period_name = all_periods.get(w.period_id, "不明") if w.period_id else "—"
            lines.append(f"[{period_name}] {w.message}")

        show_error(self, "\n".join(lines), title="警告一覧")

    # ── 画面遷移 ────────────────────────────────────────────────────────────

    def _on_edit_period(self) -> None:
        if self._period is None:
            return
        from src.ui.screens.period_create_screen import PeriodCreateScreen

        self.app.show_screen(PeriodCreateScreen, period=self._period, back_period_id=self._period_id)

    def _on_back(self) -> None:
        from src.ui.screens.start_screen import StartScreen

        self.app.show_screen(StartScreen)

    def _on_submission_list(self) -> None:
        from src.ui.screens.submission_list_screen import SubmissionListScreen

        self.app.show_screen(SubmissionListScreen, period_id=self._period_id)

    def _on_shift_edit(self) -> None:
        from src.ui.screens.shift_edit_screen import ShiftEditScreen

        self.app.show_screen(ShiftEditScreen, period_id=self._period_id)

    def _on_print(self) -> None:
        from src.ui.screens.print_screen import PrintScreen

        self.app.show_screen(PrintScreen, period_id=self._period_id)

    def _on_wish_search(self) -> None:
        from src.ui.screens.wish_search_screen import WishSearchScreen

        self.app.show_screen(WishSearchScreen, period_id=self._period_id)
