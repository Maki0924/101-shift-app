"""回答受信一覧画面（コミット17）

期間内の回答一覧を表示し、詳細・採用操作・手動紐付けへ誘導する。
"""

import tkinter as tk
from tkinter import ttk

from src.db.repositories import staff_repo, submission_repo
from src.ui.app import STATUS_LABELS
from src.ui.components.dialogs import show_error
from src.utils.logger import get_logger

_STATUS_LABELS = {
    "pending": "未処理",
    "applied": "採用済",
    "on_hold": "保留",
    "rejected": "却下",
}

_ALL_STATUSES = "すべて"


class SubmissionListScreen(ttk.Frame):
    def __init__(self, master: tk.Misc, app, period_id: int, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.app = app
        self._period_id = period_id
        self._all_submissions: list[dict] = []
        self._staff_map: dict[int, str] = {}  # staff_id -> name
        self._build()
        self._load()

    def _build(self) -> None:
        # ── タイトルバー ──
        top = ttk.Frame(self)
        top.pack(fill="x", padx=20, pady=(16, 4))
        self._title_label = ttk.Label(top, text="回答受信一覧", font=("", 15))
        self._title_label.pack(side="left")
        ttk.Button(top, text="戻る", command=self._on_back, width=10).pack(side="right")
        self._open_btn = ttk.Button(top, text="詳細を開く", command=self._on_open, width=12, state="disabled")
        self._open_btn.pack(side="right", padx=(0, 8))

        # ── 警告エリア ──
        self._warn_label = ttk.Label(self, text="", foreground="orange")
        self._warn_label.pack(fill="x", padx=20, pady=(0, 4))

        # ── フィルターバー ──
        filter_frame = ttk.Frame(self)
        filter_frame.pack(fill="x", padx=20, pady=(0, 6))

        ttk.Label(filter_frame, text="ステータス:").pack(side="left")
        self._status_var = tk.StringVar(value=_ALL_STATUSES)
        status_cb = ttk.Combobox(
            filter_frame,
            textvariable=self._status_var,
            values=[_ALL_STATUSES] + list(_STATUS_LABELS.values()),
            state="readonly",
            width=10,
        )
        status_cb.pack(side="left", padx=(4, 12))
        status_cb.bind("<<ComboboxSelected>>", lambda _e: self._apply_filter())

        ttk.Label(filter_frame, text="スタッフ:").pack(side="left")
        self._staff_var = tk.StringVar(value=_ALL_STATUSES)
        self._staff_cb = ttk.Combobox(
            filter_frame,
            textvariable=self._staff_var,
            state="readonly",
            width=14,
        )
        self._staff_cb.pack(side="left", padx=(4, 0))
        self._staff_cb.bind("<<ComboboxSelected>>", lambda _e: self._apply_filter())

        # ── 一覧 ──
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=20, pady=(0, 8))

        cols = ("submitted_at", "raw_name", "staff_name", "status", "latest", "linked")
        self._tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")
        self._tree.heading("submitted_at", text="回答日時")
        self._tree.heading("raw_name", text="氏名（フォーム）")
        self._tree.heading("staff_name", text="紐付きスタッフ")
        self._tree.heading("status", text="ステータス")
        self._tree.heading("latest", text="最新")
        self._tree.heading("linked", text="紐付け")

        self._tree.column("submitted_at", width=140, anchor="center")
        self._tree.column("raw_name", width=130)
        self._tree.column("staff_name", width=130)
        self._tree.column("status", width=70, anchor="center")
        self._tree.column("latest", width=50, anchor="center")
        self._tree.column("linked", width=60, anchor="center")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-1>", lambda _e: self._on_open())

        # tag 設定
        self._tree.tag_configure("unlinked", foreground="orange")

    # ── データ読み込み ─────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            from src.db.repositories import period_repo

            period = period_repo.get_by_id(self._period_id)
            if period:
                status_label = STATUS_LABELS.get(period["status"], period["status"])
                self._title_label.configure(text=f"回答受信一覧  —  {period['name']} [{status_label}]")

            self._all_submissions = submission_repo.get_by_period(self._period_id)
            staff_list = staff_repo.get_all()
            self._staff_map = {s["id"]: s["name"] for s in staff_list}
        except Exception as e:
            get_logger().error("回答一覧の読み込みに失敗: %s", e, exc_info=True)
            show_error(self, "回答一覧の読み込みに失敗しました。")
            return

        self._update_filter_choices()
        self._apply_filter()
        self._update_warnings()

    def _update_filter_choices(self) -> None:
        names = sorted(
            {s["raw_staff_name"] for s in self._all_submissions},
            key=lambda n: n.lower(),
        )
        self._staff_cb.configure(values=[_ALL_STATUSES] + names)
        if self._staff_var.get() not in ([_ALL_STATUSES] + names):
            self._staff_var.set(_ALL_STATUSES)

    def _apply_filter(self) -> None:
        status_filter = self._status_var.get()
        staff_filter = self._staff_var.get()

        # ステータスラベル→キー逆引き
        label_to_key = {v: k for k, v in _STATUS_LABELS.items()}

        filtered = self._all_submissions
        if status_filter != _ALL_STATUSES:
            key = label_to_key.get(status_filter)
            if key:
                filtered = [s for s in filtered if s["apply_status"] == key]
        if staff_filter != _ALL_STATUSES:
            filtered = [s for s in filtered if s["raw_staff_name"] == staff_filter]

        self._render(filtered)
        self._on_select()

    def _render(self, submissions: list[dict]) -> None:
        self._tree.delete(*self._tree.get_children())
        for sub in submissions:
            linked = sub["staff_id"] is not None
            staff_name = self._staff_map.get(sub["staff_id"], "（不明）") if linked else "未紐付け"
            tags = () if linked else ("unlinked",)
            self._tree.insert(
                "",
                "end",
                iid=str(sub["id"]),
                values=(
                    sub["submitted_at"],
                    sub["raw_staff_name"],
                    staff_name,
                    _STATUS_LABELS.get(sub["apply_status"], sub["apply_status"]),
                    "★" if sub["is_latest_for_staff"] else "",
                    "○" if linked else "✗",
                ),
                tags=tags,
            )

    def _update_warnings(self) -> None:
        unlinked = sum(1 for s in self._all_submissions if s["staff_id"] is None)
        period_warnings = [w for w in self.app.warnings if w.period_id == self._period_id]
        parts = []
        if unlinked:
            parts.append(f"未紐付け回答: {unlinked}件")
        if period_warnings:
            parts.append(f"警告: {len(period_warnings)}件")
        self._warn_label.configure(text="  |  ".join(parts) if parts else "")

    # ── イベント ───────────────────────────────────────────────────────────────

    def _on_select(self, _event=None) -> None:
        sel = self._tree.selection()
        state = "normal" if sel else "disabled"
        # open_btn は top フレームの right 側2番目
        self._open_btn.configure(state=state)

    def _on_open(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        submission_id = int(sel[0])
        from src.ui.screens.submission_detail import SubmissionDetailScreen

        self.app.show_screen(
            SubmissionDetailScreen,
            submission_id=submission_id,
            period_id=self._period_id,
        )

    def _on_back(self) -> None:
        from src.ui.screens.period_dashboard import PeriodDashboardScreen

        self.app.show_screen(PeriodDashboardScreen, period_id=self._period_id)
