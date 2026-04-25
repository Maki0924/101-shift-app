"""スタッフマスター管理画面（コミット15）"""

import math
import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from src.db.repositories import settings_repo, staff_repo
from src.sheets import auth, client
from src.sheets import form_updater as form_updater_mod
from src.ui.app import AppWarning
from src.ui.components.dialogs import ask_confirm, show_error
from src.utils.logger import get_logger
from src.utils.paths import APP_DIR

_EMPLOYMENT_LABELS = {
    "part_time": "バイト",
    "employee": "社員",
}
_EMPLOYMENT_VALUES = ["バイト", "社員"]
_LABEL_TO_TYPE = {v: k for k, v in _EMPLOYMENT_LABELS.items()}


class StaffScreen(ttk.Frame):
    def __init__(self, master: tk.Misc, app, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.app = app
        self._build()
        self._load()

    def _build(self) -> None:
        ttk.Label(self, text="スタッフ管理", font=("", 16)).pack(pady=(20, 8))

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=20, pady=(0, 8))
        ttk.Button(btn_frame, text="追加", command=self._on_add, width=10).pack(side="left", padx=4)
        self._edit_btn = ttk.Button(btn_frame, text="編集", command=self._on_edit, width=10, state="disabled")
        self._edit_btn.pack(side="left", padx=4)
        self._toggle_btn = ttk.Button(
            btn_frame, text="無効化", command=self._on_toggle_active, width=10, state="disabled"
        )
        self._toggle_btn.pack(side="left", padx=4)
        ttk.Button(btn_frame, text="戻る", command=self._on_back, width=10).pack(side="right", padx=4)

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=20, pady=4)

        cols = ("name", "type", "wage", "sort_order", "active")
        self._tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")
        self._tree.heading("name", text="名前")
        self._tree.heading("type", text="雇用区分")
        self._tree.heading("wage", text="時給")
        self._tree.heading("sort_order", text="並び順")
        self._tree.heading("active", text="有効")
        self._tree.column("name", width=200)
        self._tree.column("type", width=80, anchor="center")
        self._tree.column("wage", width=80, anchor="e")
        self._tree.column("sort_order", width=60, anchor="center")
        self._tree.column("active", width=60, anchor="center")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-1>", lambda _e: self._on_edit())

    def _load(self) -> None:
        self._tree.delete(*self._tree.get_children())
        try:
            staff_list = staff_repo.get_all()
        except Exception as e:
            get_logger().error("スタッフ一覧の読み込みに失敗: %s", e, exc_info=True)
            show_error(self, "スタッフ一覧の読み込みに失敗しました。")
            return
        for s in staff_list:
            self._tree.insert(
                "",
                "end",
                iid=str(s["id"]),
                values=(
                    s["name"],
                    _EMPLOYMENT_LABELS.get(s["employment_type"], s["employment_type"]),
                    f"¥{s['hourly_wage']:g}",
                    s["sort_order"],
                    "有効" if s["is_active"] else "無効",
                ),
                tags=() if s["is_active"] else ("inactive",),
            )
        self._tree.tag_configure("inactive", foreground="gray")
        self._on_select()

    def _on_select(self, _event=None) -> None:
        sel = self._tree.selection()
        if not sel:
            self._edit_btn.configure(state="disabled")
            self._toggle_btn.configure(state="disabled", text="無効化")
            return
        self._edit_btn.configure(state="normal")
        staff = staff_repo.get_by_id(int(sel[0]))
        if staff:
            label = "有効化" if not staff["is_active"] else "無効化"
            self._toggle_btn.configure(state="normal", text=label)

    def _on_add(self) -> None:
        def on_save(name, employment_type, hourly_wage, sort_order) -> bool:
            try:
                staff_repo.create(name, employment_type, hourly_wage, sort_order)
            except Exception as e:
                get_logger().error("スタッフ作成に失敗: %s", e, exc_info=True)
                show_error(self, "保存に失敗しました。")
                return False
            self._trigger_form_update()
            self._load()
            return True

        _StaffDialog(self, title="スタッフを追加", on_save=on_save)

    def _on_edit(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        staff = staff_repo.get_by_id(int(sel[0]))
        if staff is None:
            return

        def on_save(name, employment_type, hourly_wage, sort_order) -> bool:
            try:
                staff_repo.update(staff["id"], name, employment_type, hourly_wage, sort_order)
            except Exception as e:
                get_logger().error("スタッフ更新に失敗: %s", e, exc_info=True)
                show_error(self, "保存に失敗しました。")
                return False
            self._trigger_form_update()
            self._load()
            return True

        _StaffDialog(self, title="スタッフを編集", staff=staff, on_save=on_save)

    def _on_toggle_active(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        staff = staff_repo.get_by_id(int(sel[0]))
        if staff is None:
            return
        action = "有効化" if not staff["is_active"] else "無効化"
        if not ask_confirm(self, f"「{staff['name']}」を{action}しますか？"):
            return
        try:
            staff_repo.set_active(staff["id"], not staff["is_active"])
        except Exception as e:
            get_logger().error("スタッフ有効フラグ更新に失敗: %s", e, exc_info=True)
            show_error(self, "更新に失敗しました。")
            return
        self._trigger_form_update()
        self._load()

    def _trigger_form_update(self) -> None:
        """スタッフ更新後に collecting 期間のフォームプルダウンを自動更新する。

        credentials 不在時はスキップ（縮退モード）。
        API 呼び出しはバックグラウンドスレッドで実行しUIをブロックしない。
        """
        if not self.app.creds_available:
            return
        threading.Thread(target=self._form_update_worker, daemon=True).start()

    def _form_update_worker(self) -> None:
        """フォームプルダウン更新（ワーカースレッド）。"""
        if self.app.is_shutting_down():
            return
        try:
            app_settings = settings_repo.get()
            creds_filename = (
                app_settings["credentials_filename"]
                if app_settings and app_settings.get("credentials_filename")
                else "credentials.json"
            )
            creds = auth.load_credentials(APP_DIR / creds_filename)
            if creds is None:
                return  # credentials 不在は縮退モードとして無視

            forms_svc = client.build_forms(creds)
            all_staff = staff_repo.get_all()
            staff_names = [s["name"] for s in all_staff if s.get("is_active")]
            failures = form_updater_mod.update_all(staff_names, forms_svc)
            for f in failures:
                get_logger().warning("フォームプルダウン更新失敗: %s", f)
            new_warnings = [
                AppWarning(
                    period_id=f["period_id"],
                    message=f"フォームプルダウン更新失敗: {f['error']}",
                    kind="form_update",
                )
                for f in failures
            ]

            def _apply_form_update() -> None:
                if self.app.is_shutting_down():
                    return
                # update_all は全 collecting 期間を対象にまとめて実行するため、
                # 実行完了時点の最新結果だけを残す（古い form_update 警告は全置換）
                self.app.warnings = [w for w in self.app.warnings if w.kind != "form_update"]
                self.app.warnings.extend(new_warnings)
                if new_warnings:
                    self.app.status_bar.set_timed_sync_message(f"フォーム更新警告: {len(new_warnings)}件")

            self.app.post_to_ui(_apply_form_update)

        except Exception as e:
            get_logger().error("フォームプルダウン更新に失敗: %s", e, exc_info=True)
            err_msg = f"フォーム自動更新失敗: {e}"

            def _on_error() -> None:
                if self.app.is_shutting_down():
                    return
                self.app.status_bar.set_timed_sync_message(err_msg)

            self.app.post_to_ui(_on_error)

    def _on_back(self) -> None:
        from src.ui.screens.settings_screen import SettingsScreen

        self.app.show_screen(SettingsScreen)


class _StaffDialog(tk.Toplevel):
    """スタッフ追加・編集モーダルダイアログ。"""

    #: on_save(name, employment_type, hourly_wage, sort_order) -> bool
    def __init__(
        self,
        parent: tk.Widget,
        title: str,
        on_save: Callable[[str, str, float, int], bool],
        staff: dict | None = None,
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)
        self._staff = staff
        self._on_save: Callable[[str, str, float, int], bool] = on_save
        self._build()
        self._fill()
        self.wait_visibility()
        self.focus_set()

    def _build(self) -> None:
        form = ttk.Frame(self, padding=20)
        form.pack()

        self._name_var = tk.StringVar()
        self._type_var = tk.StringVar()
        self._wage_var = tk.StringVar()
        self._sort_var = tk.StringVar()

        rows = [
            ("名前", ttk.Entry(form, textvariable=self._name_var, width=20)),
            (
                "雇用区分",
                ttk.Combobox(
                    form,
                    textvariable=self._type_var,
                    values=_EMPLOYMENT_VALUES,
                    state="readonly",
                    width=18,
                ),
            ),
            ("時給（円）", ttk.Entry(form, textvariable=self._wage_var, width=20)),
            ("並び順", ttk.Entry(form, textvariable=self._sort_var, width=20)),
        ]
        self._name_entry = rows[0][1]

        for i, (lbl, widget) in enumerate(rows):
            ttk.Label(form, text=lbl, anchor="e", width=10).grid(row=i, column=0, pady=6, sticky="e")
            widget.grid(row=i, column=1, pady=6, padx=(8, 0), sticky="w")

        btn_frame = ttk.Frame(form)
        btn_frame.grid(row=len(rows), column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btn_frame, text="保存", command=self._on_ok, width=10).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="キャンセル", command=self.destroy, width=10).pack(side="left", padx=6)

    def _fill(self) -> None:
        if self._staff is None:
            self._type_var.set("バイト")
            self._sort_var.set("0")
            self._wage_var.set("0")
        else:
            self._name_var.set(self._staff["name"])
            self._type_var.set(_EMPLOYMENT_LABELS.get(self._staff["employment_type"], "バイト"))
            self._wage_var.set(f"{self._staff['hourly_wage']:g}")
            self._sort_var.set(str(self._staff["sort_order"]))
        self._name_entry.focus_set()

    def _on_ok(self) -> None:
        name = self._name_var.get().strip()
        if not name:
            show_error(self, "名前を入力してください。")
            return

        existing = staff_repo.get_by_name(name)
        if existing and (self._staff is None or existing["id"] != self._staff["id"]):
            show_error(
                self,
                f"「{name}」はすでに登録されています。\n"
                "v1では同姓同名のスタッフは登録できません。\n"
                "姓名の表記を変えて区別してください。",
            )
            return

        employment_type = _LABEL_TO_TYPE.get(self._type_var.get(), "part_time")

        try:
            hourly_wage = float(self._wage_var.get().strip())
            if not math.isfinite(hourly_wage) or hourly_wage < 0:
                raise ValueError
        except ValueError:
            show_error(self, "時給は0以上の数値を入力してください。")
            return

        try:
            sort_order = int(self._sort_var.get().strip())
        except ValueError:
            show_error(self, "並び順は整数を入力してください。")
            return

        if self._on_save(name, employment_type, hourly_wage, sort_order):
            self.destroy()
