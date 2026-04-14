"""回答詳細・採用/保留/却下・手動スタッフ紐付け画面（コミット18）"""

import tkinter as tk
from tkinter import ttk

from src.db.repositories import staff_repo, submission_repo
from src.logic.apply_submission import ApplyError, apply
from src.ui.components.dialogs import ask_confirm, show_error
from src.ui.screens.submission_list_screen import _STATUS_LABELS
from src.utils.logger import get_logger


def _fmt_time(v: float | None) -> str:
    """REAL型の時刻（例: 9.5）を 'h:mm' 形式に変換する。None は '—' を返す。"""
    if v is None:
        return "—"
    h = int(v)
    m = int(round((v - h) * 60))
    return f"{h}:{m:02d}"


class SubmissionDetailScreen(ttk.Frame):
    def __init__(self, master: tk.Misc, app, submission_id: int, period_id: int, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.app = app
        self._submission_id = submission_id
        self._period_id = period_id
        self._is_archived = False  # _load() で上書き
        self._sub: dict | None = None  # _load() 成功後に設定
        self._build()
        self._load()

    def _build(self) -> None:
        # ── ヘッダー ──
        top = ttk.Frame(self)
        top.pack(fill="x", padx=20, pady=(16, 4))
        ttk.Label(top, text="回答詳細", font=("", 15)).pack(side="left")
        ttk.Button(top, text="戻る", command=self._on_back, width=10).pack(side="right")

        # ── 回答サマリー ──
        self._summary_label = ttk.Label(self, text="", justify="left")
        self._summary_label.pack(fill="x", padx=20, pady=(4, 8))

        # ── 操作ボタン ──
        btn_frame = ttk.LabelFrame(self, text="操作", padding=8)
        btn_frame.pack(fill="x", padx=20, pady=(0, 8))

        self._apply_btn = ttk.Button(btn_frame, text="採用", command=self._on_apply, width=10, state="disabled")
        self._apply_btn.pack(side="left", padx=4)
        self._hold_btn = ttk.Button(btn_frame, text="保留", command=self._on_hold, width=10, state="disabled")
        self._hold_btn.pack(side="left", padx=4)
        self._reject_btn = ttk.Button(btn_frame, text="却下", command=self._on_reject, width=10, state="disabled")
        self._reject_btn.pack(side="left", padx=4)
        self._link_btn = ttk.Button(
            btn_frame, text="スタッフを紐付け", command=self._on_link_staff, width=16, state="disabled"
        )
        self._link_btn.pack(side="left", padx=(16, 4))

        # ── 日別希望テーブル ──
        detail_frame = ttk.LabelFrame(self, text="日別希望", padding=8)
        detail_frame.pack(fill="both", expand=True, padx=20, pady=(0, 12))

        cols = ("work_date", "start_time", "end_time")
        self._tree = ttk.Treeview(detail_frame, columns=cols, show="headings", selectmode="none")
        self._tree.heading("work_date", text="日付")
        self._tree.heading("start_time", text="開始")
        self._tree.heading("end_time", text="終了")
        self._tree.column("work_date", width=110, anchor="center")
        self._tree.column("start_time", width=80, anchor="center")
        self._tree.column("end_time", width=80, anchor="center")

        vsb = ttk.Scrollbar(detail_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

    # ── データ読み込み ─────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            sub = submission_repo.get_by_id(self._submission_id)
        except Exception as e:
            get_logger().error("回答の読み込みに失敗: %s", e, exc_info=True)
            show_error(self, "回答の読み込みに失敗しました。")
            return

        if sub is None:
            show_error(self, "回答が見つかりません。")
            return

        try:
            from src.db.repositories import period_repo

            period = period_repo.get_by_id(self._period_id)
            self._is_archived = period["status"] == "archived" if period else False
        except Exception as e:
            get_logger().error("期間ステータスの読み込みに失敗: %s", e, exc_info=True)
            self._is_archived = False

        self._sub = sub
        self._render_summary(sub)
        self._render_entries(sub)
        self._update_buttons(sub)

    def _render_summary(self, sub: dict) -> None:
        linked = sub["staff_id"] is not None
        try:
            staff_name = (staff_repo.get_by_id(sub["staff_id"]) or {}).get("name", "（不明）") if linked else "未紐付け"
        except Exception:
            staff_name = "（取得失敗）"

        weekly = "—"
        if sub["weekly_pref_min"] is not None:
            w_min = sub["weekly_pref_min"]
            w_max = sub["weekly_pref_max"]
            weekly = f"{w_min}〜{w_max}回" if w_max is not None else f"{w_min}回以上"

        latest = "★ 最新" if sub["is_latest_for_staff"] else ""
        status = _STATUS_LABELS.get(sub["apply_status"], sub["apply_status"])

        lines = [
            f"氏名（フォーム）: {sub['raw_staff_name']}　紐付きスタッフ: {staff_name}  {latest}",
            f"回答日時: {sub['submitted_at']}　ステータス: {status}",
            f"週何回希望: {weekly}",
        ]
        if sub.get("note_text"):
            lines.append(f"備考: {sub['note_text']}")

        self._summary_label.configure(text="\n".join(lines))

    def _render_entries(self, sub: dict) -> None:
        self._tree.delete(*self._tree.get_children())
        try:
            entries = submission_repo.get_day_entries(self._submission_id)
        except Exception as e:
            get_logger().error("日別エントリーの読み込みに失敗: %s", e, exc_info=True)
            return

        for entry in entries:
            s = _fmt_time(entry["start_time"])
            e = _fmt_time(entry["end_time"])
            # 両方 None は勤務不可（フォーム未入力）
            if entry["start_time"] is None and entry["end_time"] is None:
                s, e = "勤務不可", ""
            self._tree.insert(
                "",
                "end",
                values=(entry["work_date"], s, e),
            )

    def _update_buttons(self, sub: dict) -> None:
        # アーカイブ期間はすべての操作を禁止
        if self._is_archived:
            for btn in (self._apply_btn, self._hold_btn, self._reject_btn, self._link_btn):
                btn.configure(state="disabled")
            return

        linked = sub["staff_id"] is not None
        status = sub["apply_status"]

        # 未紐付け・採用済みは採用ボタン不要
        self._apply_btn.configure(state="normal" if linked and status != "applied" else "disabled")
        # applied からの保留/却下は wish_shifts の整合性を保てないため禁止
        # 採用取り消しは別の回答を採用する（apply()の旧採用解除フロー）で行う
        self._hold_btn.configure(state="normal" if status not in ("on_hold", "applied") else "disabled")
        self._reject_btn.configure(state="normal" if status not in ("rejected", "applied") else "disabled")
        # 既に紐付け済みでも変更可能（再紐付け）
        self._link_btn.configure(state="normal")

    # ── 採用/保留/却下 ───────────────────────────────────────────────────────

    def _on_apply(self) -> None:
        if self._sub is None:
            return
        sub = self._sub
        if sub["staff_id"] is None:
            show_error(self, "スタッフが未紐付けのため採用できません。")
            return

        # 同スタッフ・同期間の既採用回答があるか確認
        existing = [
            s
            for s in submission_repo.get_by_period(self._period_id)
            if s["staff_id"] == sub["staff_id"] and s["apply_status"] == "applied" and s["id"] != sub["id"]
        ]
        if existing:
            if not ask_confirm(
                self,
                f"「{self._staff_name(sub['staff_id'])}」の採用済み回答（{existing[0]['submitted_at']}）を\n"
                "未処理に戻して、この回答を採用します。よろしいですか？",
            ):
                return

        try:
            apply(sub["id"])
        except ApplyError as e:
            show_error(self, str(e))
            return
        except Exception as e:
            get_logger().error("採用処理に失敗: %s", e, exc_info=True)
            show_error(self, "採用処理に失敗しました。")
            return

        self._load()

    def _on_hold(self) -> None:
        if self._sub is None:
            return
        self._update_status("on_hold")

    def _on_reject(self) -> None:
        if self._sub is None:
            return
        self._update_status("rejected")

    def _update_status(self, status: str) -> None:
        try:
            submission_repo.update_apply_status(self._submission_id, status)
        except Exception as e:
            get_logger().error("ステータス更新に失敗: %s", e, exc_info=True)
            show_error(self, "更新に失敗しました。")
            return
        self._load()

    # ── 手動スタッフ紐付け ──────────────────────────────────────────────────────

    def _on_link_staff(self) -> None:
        if self._sub is None:
            return
        try:
            staff_list = staff_repo.get_all()
        except Exception as e:
            get_logger().error("スタッフ一覧の読み込みに失敗: %s", e, exc_info=True)
            show_error(self, "スタッフ一覧の読み込みに失敗しました。")
            return
        _StaffLinkDialog(self, staff_list=staff_list, on_select=self._save_link)

    def _save_link(self, staff_id: int) -> bool:
        try:
            submission_repo.update_staff_id(self._submission_id, staff_id)
        except Exception as e:
            get_logger().error("スタッフ紐付けに失敗: %s", e, exc_info=True)
            show_error(self, "紐付けに失敗しました。")
            return False
        self._load()
        return True

    # ── ユーティリティ ──────────────────────────────────────────────────────────

    def _staff_name(self, staff_id: int | None) -> str:
        if staff_id is None:
            return "未紐付け"
        try:
            s = staff_repo.get_by_id(staff_id)
            return s["name"] if s else "（不明）"
        except Exception:
            return "（不明）"

    def _on_back(self) -> None:
        from src.ui.screens.submission_list_screen import SubmissionListScreen

        self.app.show_screen(
            SubmissionListScreen,
            period_id=self._period_id,
        )


class _StaffLinkDialog(tk.Toplevel):
    """手動スタッフ紐付けダイアログ。"""

    def __init__(self, parent: tk.Widget, staff_list: list[dict], on_select) -> None:
        super().__init__(parent)
        self.title("スタッフを紐付け")
        self.resizable(False, True)
        self.grab_set()
        self.transient(parent)
        self._staff_list = staff_list
        self._on_select = on_select
        self._build()
        self.wait_visibility()
        self.focus_set()

    def _build(self) -> None:
        ttk.Label(self, text="紐付けるスタッフを選択してください", padding=8).pack()

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        self._lb = tk.Listbox(frame, selectmode="single", width=28, height=16)
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self._lb.yview)
        self._lb.configure(yscrollcommand=vsb.set)
        self._lb.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        for s in self._staff_list:
            label = f"{s['name']}（{'バイト' if s['employment_type'] == 'part_time' else '社員'}）"
            if not s["is_active"]:
                label += "  ※無効"
            self._lb.insert("end", label)

        self._lb.bind("<Double-1>", lambda _e: self._on_ok())

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=(0, 12))
        ttk.Button(btn_frame, text="紐付け", command=self._on_ok, width=10).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="キャンセル", command=self.destroy, width=10).pack(side="left", padx=6)

    def _on_ok(self) -> None:
        sel = self._lb.curselection()
        if not sel:
            show_error(self, "スタッフを選択してください。")
            return
        staff = self._staff_list[sel[0]]
        if self._on_select(staff["id"]):
            self.destroy()
