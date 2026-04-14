"""設定画面（コミット16）

app_settings 全項目編集フォームと custom_day_rules（グローバル）CRUD を提供する。
"""

import tkinter as tk
from tkinter import ttk

from src.db.repositories import custom_day_repo, settings_repo
from src.ui.components.dialogs import ask_confirm, show_error
from src.utils.logger import get_logger


def _parse_float(s: str, min_val: float | None = None) -> float | None:
    """文字列を float に変換する。不正または min_val 未満なら None。"""
    try:
        v = float(s.strip())
        if min_val is not None and v < min_val:
            return None
        return v
    except ValueError:
        return None


def _parse_int(s: str, min_val: int | None = None) -> int | None:
    """文字列を int に変換する。不正または min_val 未満なら None。"""
    try:
        v = int(s.strip())
        if min_val is not None and v < min_val:
            return None
        return v
    except ValueError:
        return None


class SettingsScreen(ttk.Frame):
    def __init__(self, master: tk.Misc, app, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.app = app
        self._build()
        self._load()

    def _build(self) -> None:
        ttk.Label(self, text="設定", font=("", 16)).pack(pady=(20, 8))

        # スタッフ管理ボタン（上部）
        top_frame = ttk.Frame(self)
        top_frame.pack(fill="x", padx=20, pady=(0, 8))
        ttk.Button(top_frame, text="スタッフ管理", command=self._on_staff, width=14).pack(side="left")
        ttk.Button(top_frame, text="戻る", command=self._on_back, width=10).pack(side="right")

        # タブ
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=20, pady=4)

        self._tab_settings = ttk.Frame(nb, padding=16)
        self._tab_custom = ttk.Frame(nb, padding=8)
        nb.add(self._tab_settings, text="アプリ設定")
        nb.add(self._tab_custom, text="特別日設定")

        self._build_settings_tab()
        self._build_custom_tab()

    # ── アプリ設定タブ ───────────────────────────────────────────────────────────

    def _build_settings_tab(self) -> None:
        # スクロール可能なキャンバスでコンテンツを包む
        canvas = tk.Canvas(self._tab_settings, highlightthickness=0)
        vsb = ttk.Scrollbar(self._tab_settings, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )

        self._sv: dict[str, tk.StringVar] = {}

        fields: list[tuple[str, str, str]] = [
            # (セクション区切り用ラベル, フィールドラベル, キー)
            # セクション区切り: フィールドラベルが空文字のときはセクションヘッダ
            ("昼シフト時間帯", "", ""),
            ("", "開始（時間）", "day_shift_start"),
            ("", "終了（時間）", "day_shift_end"),
            ("夜シフト時間帯", "", ""),
            ("", "開始（時間）", "night_shift_start"),
            ("", "終了（時間）", "night_shift_end"),
            ("その他", "", ""),
            ("", "昼夜重複閾値（時間）", "overlap_hours_threshold"),
            ("加算額（円）", "", ""),
            ("", "土曜加算", "saturday_bonus"),
            ("", "日曜加算", "sunday_bonus"),
            ("", "祝日加算", "holiday_bonus"),
            ("最低人数", "", ""),
            ("", "平日・昼", "weekday_day_min_staff"),
            ("", "平日・夜", "weekday_night_min_staff"),
            ("", "土日祝・昼", "weekend_day_min_staff"),
            ("", "土日祝・夜", "weekend_night_min_staff"),
            ("印刷", "", ""),
            ("", "フォントサイズ（pt）", "print_font_size"),
        ]

        self._warn_label = ttk.Label(inner, text="", foreground="orange")
        self._warn_label.pack(anchor="w", pady=(0, 4))

        for section, lbl, key in fields:
            if section:
                ttk.Label(inner, text=section, font=("", 10, "bold")).pack(anchor="w", pady=(10, 2))
            else:
                row = ttk.Frame(inner)
                row.pack(fill="x", pady=2)
                ttk.Label(row, text=lbl, anchor="e", width=22).pack(side="left")
                var = tk.StringVar()
                self._sv[key] = var
                ttk.Entry(row, textvariable=var, width=12).pack(side="left", padx=(8, 0))

        ttk.Button(inner, text="保存", command=self._on_save_settings, width=12).pack(pady=(16, 8))

    # ── 特別日設定タブ ──────────────────────────────────────────────────────────

    def _build_custom_tab(self) -> None:
        tab = self._tab_custom

        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill="x", pady=(0, 8))
        ttk.Button(btn_frame, text="追加", command=self._on_custom_add, width=10).pack(side="left", padx=4)
        self._custom_edit_btn = ttk.Button(
            btn_frame, text="編集", command=self._on_custom_edit, width=10, state="disabled"
        )
        self._custom_edit_btn.pack(side="left", padx=4)
        self._custom_del_btn = ttk.Button(
            btn_frame, text="削除", command=self._on_custom_delete, width=10, state="disabled"
        )
        self._custom_del_btn.pack(side="left", padx=4)

        frame = ttk.Frame(tab)
        frame.pack(fill="both", expand=True)

        cols = ("date", "holiday", "exclude", "bonus", "note")
        self._custom_tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")
        self._custom_tree.heading("date", text="日付")
        self._custom_tree.heading("holiday", text="独自休日")
        self._custom_tree.heading("exclude", text="祝日除外")
        self._custom_tree.heading("bonus", text="加算額")
        self._custom_tree.heading("note", text="メモ")
        self._custom_tree.column("date", width=100, anchor="center")
        self._custom_tree.column("holiday", width=70, anchor="center")
        self._custom_tree.column("exclude", width=70, anchor="center")
        self._custom_tree.column("bonus", width=80, anchor="e")
        self._custom_tree.column("note", width=200)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self._custom_tree.yview)
        self._custom_tree.configure(yscrollcommand=vsb.set)
        self._custom_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._custom_tree.bind("<<TreeviewSelect>>", self._on_custom_select)
        self._custom_tree.bind("<Double-1>", lambda _e: self._on_custom_edit())

    # ── データ読み込み ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        self._load_settings()
        self._load_custom()

    def _load_settings(self) -> None:
        try:
            settings = settings_repo.get()
        except Exception as e:
            get_logger().error("設定の読み込みに失敗: %s", e, exc_info=True)
            show_error(self, "設定の読み込みに失敗しました。")
            return
        if settings is None:
            return
        for key, var in self._sv.items():
            var.set(str(settings[key]))

    def _load_custom(self) -> None:
        self._custom_tree.delete(*self._custom_tree.get_children())
        try:
            rules = custom_day_repo.get_global()
        except Exception as e:
            get_logger().error("特別日設定の読み込みに失敗: %s", e, exc_info=True)
            show_error(self, "特別日設定の読み込みに失敗しました。")
            return
        for r in rules:
            bonus = f"¥{r['wage_bonus']:g}" if r["wage_bonus"] is not None else "—"
            self._custom_tree.insert(
                "",
                "end",
                iid=r["rule_date"],
                values=(
                    r["rule_date"],
                    "○" if r["is_custom_holiday"] else "—",
                    "○" if r["exclude_auto_holiday"] else "—",
                    bonus,
                    r["note_text"] or "",
                ),
            )
        self._on_custom_select()

    # ── アプリ設定保存 ───────────────────────────────────────────────────────────

    def _on_save_settings(self) -> None:
        self._warn_label.configure(text="")

        float_fields = [
            ("day_shift_start", "昼シフト開始", 0.0),
            ("day_shift_end", "昼シフト終了", 0.0),
            ("night_shift_start", "夜シフト開始", 0.0),
            ("night_shift_end", "夜シフト終了", 0.0),
            ("overlap_hours_threshold", "昼夜重複閾値", 0.0),
            ("saturday_bonus", "土曜加算", 0.0),
            ("sunday_bonus", "日曜加算", 0.0),
            ("holiday_bonus", "祝日加算", 0.0),
        ]
        int_fields = [
            ("weekday_day_min_staff", "平日昼最低人数", 0),
            ("weekday_night_min_staff", "平日夜最低人数", 0),
            ("weekend_day_min_staff", "土日祝昼最低人数", 0),
            ("weekend_night_min_staff", "土日祝夜最低人数", 0),
            ("print_font_size", "印刷フォントサイズ", 1),
        ]

        values: dict = {}
        for key, label, min_val in float_fields:
            v = _parse_float(self._sv[key].get(), min_val)
            if v is None:
                show_error(self, f"{label}は{min_val}以上の数値を入力してください。")
                return
            values[key] = v

        for key, label, min_val in int_fields:
            v = _parse_int(self._sv[key].get(), min_val)
            if v is None:
                show_error(self, f"{label}は{min_val}以上の整数を入力してください。")
                return
            values[key] = v

        # 昼シフト整合性チェック
        if values["day_shift_start"] >= values["day_shift_end"]:
            show_error(self, "昼シフトの開始は終了より前の時間を指定してください。")
            return
        # 夜シフト整合性チェック
        if values["night_shift_start"] >= values["night_shift_end"]:
            show_error(self, "夜シフトの開始は終了より前の時間を指定してください。")
            return

        # 昼夜重複警告（保存は許可）
        if (
            values["day_shift_start"] < values["night_shift_end"]
            and values["night_shift_start"] < values["day_shift_end"]
        ):
            self._warn_label.configure(text="昼シフトと夜シフトの時間帯が重複しています（このまま保存も可能）")

        try:
            current = settings_repo.get()
            credentials_filename = current["credentials_filename"] if current else "credentials.json"
            settings_repo.update(
                day_shift_start=values["day_shift_start"],
                day_shift_end=values["day_shift_end"],
                night_shift_start=values["night_shift_start"],
                night_shift_end=values["night_shift_end"],
                overlap_hours_threshold=values["overlap_hours_threshold"],
                saturday_bonus=values["saturday_bonus"],
                sunday_bonus=values["sunday_bonus"],
                holiday_bonus=values["holiday_bonus"],
                weekday_day_min_staff=values["weekday_day_min_staff"],
                weekday_night_min_staff=values["weekday_night_min_staff"],
                weekend_day_min_staff=values["weekend_day_min_staff"],
                weekend_night_min_staff=values["weekend_night_min_staff"],
                print_font_size=values["print_font_size"],
                credentials_filename=credentials_filename,
            )
        except Exception as e:
            get_logger().error("設定の保存に失敗: %s", e, exc_info=True)
            show_error(self, "保存に失敗しました。")
            return

    # ── 特別日 CRUD ─────────────────────────────────────────────────────────────

    def _on_custom_select(self, _event=None) -> None:
        sel = self._custom_tree.selection()
        state = "normal" if sel else "disabled"
        self._custom_edit_btn.configure(state=state)
        self._custom_del_btn.configure(state=state)

    def _on_custom_add(self) -> None:
        _CustomDayDialog(self, on_save=self._save_custom_rule)

    def _on_custom_edit(self) -> None:
        sel = self._custom_tree.selection()
        if not sel:
            return
        rule_date = sel[0]
        rule = custom_day_repo.get_one(0, rule_date)
        if rule is None:
            return
        _CustomDayDialog(self, rule=rule, on_save=self._save_custom_rule)

    def _save_custom_rule(
        self,
        rule_date: str,
        is_custom_holiday: bool,
        exclude_auto_holiday: bool,
        wage_bonus: float | None,
        note_text: str | None,
    ) -> None:
        try:
            custom_day_repo.upsert(
                period_id=0,
                rule_date=rule_date,
                is_custom_holiday=is_custom_holiday,
                exclude_auto_holiday=exclude_auto_holiday,
                wage_bonus=wage_bonus,
                note_text=note_text,
            )
        except Exception as e:
            get_logger().error("特別日設定の保存に失敗: %s", e, exc_info=True)
            show_error(self, "保存に失敗しました。")
            return
        self._load_custom()

    def _on_custom_delete(self) -> None:
        sel = self._custom_tree.selection()
        if not sel:
            return
        rule_date = sel[0]
        if not ask_confirm(self, f"{rule_date} の特別日設定を削除しますか？"):
            return
        try:
            custom_day_repo.delete(0, rule_date)
        except Exception as e:
            get_logger().error("特別日設定の削除に失敗: %s", e, exc_info=True)
            show_error(self, "削除に失敗しました。")
            return
        self._load_custom()

    # ── 画面遷移 ─────────────────────────────────────────────────────────────────

    def _on_staff(self) -> None:
        from src.ui.screens.staff_screen import StaffScreen

        self.app.show_screen(StaffScreen)

    def _on_back(self) -> None:
        from src.ui.screens.start_screen import StartScreen

        self.app.show_screen(StartScreen)


class _CustomDayDialog(tk.Toplevel):
    """特別日ルール追加・編集モーダルダイアログ。"""

    def __init__(
        self,
        parent: tk.Widget,
        on_save,
        rule: dict | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("特別日を追加" if rule is None else "特別日を編集")
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)
        self._rule = rule
        self._on_save = on_save
        self._build()
        self._fill()
        self.wait_visibility()
        self.focus_set()

    def _build(self) -> None:
        form = ttk.Frame(self, padding=20)
        form.pack()

        self._date_var = tk.StringVar()
        self._holiday_var = tk.BooleanVar()
        self._exclude_var = tk.BooleanVar()
        self._bonus_var = tk.StringVar()
        self._note_var = tk.StringVar()

        ttk.Label(form, text="日付 (YYYY-MM-DD)", anchor="e", width=20).grid(row=0, column=0, pady=6, sticky="e")
        self._date_entry = ttk.Entry(form, textvariable=self._date_var, width=16)
        self._date_entry.grid(row=0, column=1, pady=6, padx=(8, 0), sticky="w")

        ttk.Label(form, text="独自休日", anchor="e", width=20).grid(row=1, column=0, pady=6, sticky="e")
        ttk.Checkbutton(form, variable=self._holiday_var).grid(row=1, column=1, pady=6, padx=(8, 0), sticky="w")

        ttk.Label(form, text="祝日除外", anchor="e", width=20).grid(row=2, column=0, pady=6, sticky="e")
        ttk.Checkbutton(form, variable=self._exclude_var).grid(row=2, column=1, pady=6, padx=(8, 0), sticky="w")

        ttk.Label(form, text="加算額（空欄=なし）", anchor="e", width=20).grid(row=3, column=0, pady=6, sticky="e")
        ttk.Entry(form, textvariable=self._bonus_var, width=16).grid(row=3, column=1, pady=6, padx=(8, 0), sticky="w")

        ttk.Label(form, text="メモ", anchor="e", width=20).grid(row=4, column=0, pady=6, sticky="e")
        ttk.Entry(form, textvariable=self._note_var, width=24).grid(row=4, column=1, pady=6, padx=(8, 0), sticky="w")

        btn_frame = ttk.Frame(form)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btn_frame, text="保存", command=self._on_ok, width=10).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="キャンセル", command=self.destroy, width=10).pack(side="left", padx=6)

    def _fill(self) -> None:
        if self._rule is None:
            self._date_entry.focus_set()
            return
        self._date_var.set(self._rule["rule_date"])
        self._holiday_var.set(bool(self._rule["is_custom_holiday"]))
        self._exclude_var.set(bool(self._rule["exclude_auto_holiday"]))
        if self._rule["wage_bonus"] is not None:
            self._bonus_var.set(f"{self._rule['wage_bonus']:g}")
        self._note_var.set(self._rule["note_text"] or "")
        # 編集モードは日付を変更不可
        self._date_entry.configure(state="disabled")

    def _on_ok(self) -> None:
        import datetime

        date_str = self._date_var.get().strip()
        try:
            datetime.date.fromisoformat(date_str)
        except ValueError:
            show_error(self, "日付の形式が不正です（YYYY-MM-DD）。")
            return

        bonus_str = self._bonus_var.get().strip()
        wage_bonus: float | None = None
        if bonus_str:
            try:
                wage_bonus = float(bonus_str)
                if wage_bonus < 0:
                    raise ValueError
            except ValueError:
                show_error(self, "加算額は0以上の数値を入力してください。")
                return

        note_text = self._note_var.get().strip() or None

        self._on_save(
            date_str,
            self._holiday_var.get(),
            self._exclude_var.get(),
            wage_bonus,
            note_text,
        )
        self.destroy()
