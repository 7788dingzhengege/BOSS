# 标注窗口: 投递后人工标注, 分"已投递/被过滤"两组

import tkinter as tk
from tkinter import ttk, messagebox
from . import labeler
from . import metrics

# Google Material Design 配色 (模块级常量, 供所有方法使用)
PRIMARY = '#1a73e8'
SUCCESS = '#43a047'
WARNING = '#ff9800'
DANGER = '#e53935'
LIGHT = '#f8f9fa'
BORDER = '#e0e0e0'
TEXT = '#333333'
TEXT_LIGHT = '#666666'

# 每类最多渲染的卡片数（超过的部分用批量按钮处理，避免上万控件卡死界面）
MAX_CARDS = 150


class LabelWindow:
    """标注窗口"""

    def __init__(self, parent=None):
        self.top = tk.Toplevel(parent)
        self.top.title("飞轮标注")
        self.top.geometry("920x680")
        self.top.resizable(True, True)
        self.top.minsize(800, 500)
        self.top.lift()
        self.top.focus_force()

        style = ttk.Style()
        style.theme_use('clam')

        style.configure('TFrame', background=LIGHT)
        style.configure('TLabel', background=LIGHT, foreground=TEXT, font=('Microsoft YaHei', 9))
        style.configure('Card.TFrame', background='white')
        style.layout('Card.TLabelframe', style.layout('TLabelframe'))
        style.configure('Card.TLabelframe', background='white', bordercolor=BORDER,
                        relief='solid', font=('Microsoft YaHei', 10, 'bold'), foreground=TEXT)
        style.configure('Success.TButton', background=SUCCESS, foreground='white',
                        font=('Microsoft YaHei', 9), padding=(10, 3))
        style.configure('Danger.TButton', background=DANGER, foreground='white',
                        font=('Microsoft YaHei', 9), padding=(10, 3))
        style.configure('Warning.TButton', background=WARNING, foreground='white',
                        font=('Microsoft YaHei', 9), padding=(10, 3))
        style.configure('Info.TButton', background='#546e7a', foreground='white',
                        font=('Microsoft YaHei', 9), padding=(10, 3))
        style.configure('Light.TButton', background='#e0e0e0', foreground=TEXT,
                        font=('Microsoft YaHei', 9), padding=(10, 3))
        style.configure('TEntry', font=('Microsoft YaHei', 9), padding=(6, 3))

        self.top.configure(bg=LIGHT)

        self._build_ui()
        self._refresh()

    def _build_ui(self):
        top = ttk.Frame(self.top)
        top.pack(fill='x', padx=15, pady=(15, 10))

        self.summary_var = tk.StringVar(value="加载中...")
        ttk.Label(top, textvariable=self.summary_var, font=('Microsoft YaHei', 10),
                  justify='left').pack(anchor='w')

        batch = ttk.Frame(self.top)
        batch.pack(fill='x', padx=15, pady=(0, 10))

        ttk.Button(batch, text="全部投了的标为👍对", command=self._batch_applied_ok,
                   style='Success.TButton').pack(side='left', padx=(0, 8))
        ttk.Button(batch, text="全部过滤的标为👎该排", command=self._batch_excluded_reject,
                   style='Danger.TButton').pack(side='left', padx=(0, 8))
        ttk.Button(batch, text="计算指标", command=self._show_metrics,
                   style='Info.TButton').pack(side='left', padx=(0, 8))
        ttk.Button(batch, text="刷新", command=self._refresh,
                   style='Light.TButton').pack(side='left')

        main = ttk.Frame(self.top)
        main.pack(fill='both', expand=True, padx=15, pady=(0, 15))

        canvas = tk.Canvas(main, bg=LIGHT, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main, orient='vertical', command=canvas.yview)
        self.scroll_frame = ttk.Frame(canvas)
        self.scroll_frame.bind('<Configure>',
                               lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        self._canvas_window = canvas.create_window((0, 0), window=self.scroll_frame, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # 让 scroll_frame 宽度跟随 canvas
        def _on_canvas_configure(event):
            canvas.itemconfig(self._canvas_window, width=event.width)
        canvas.bind('<Configure>', _on_canvas_configure)

        def _on_wheel(event):
            if not canvas.winfo_exists():
                return
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
            except tk.TclError:
                pass
        canvas.bind_all('<MouseWheel>', _on_wheel)

        # 窗口销毁时解绑全局滚轮事件, 避免 TclError: invalid command name
        def _cleanup(_e=None):
            try:
                canvas.unbind_all('<MouseWheel>')
            except Exception:
                pass
        self.top.bind('<Destroy>', _cleanup)

    def _refresh(self):
        """刷新列表"""
        for w in self.scroll_frame.winfo_children():
            w.destroy()

        queue = labeler.get_review_queue()
        summary = labeler.get_review_summary()
        self.summary_var.set(
            f"待标注: {summary['pending_count']} 条  |  "
            f"已投待标: {summary['applied_pending']}  |  过滤待标: {summary['excluded_pending']}  |  "
            f"已标: {summary['total_labeled']} (G1投对:{summary['G1']} G2错投:{summary['G2']} "
            f"G3漏投:{summary['G3']} G4拦对:{summary['G4']})"
        )

        row = 0

        # 按时间倒序取最新 N 条渲染（其余用批量按钮处理）
        def _newest(items):
            return sorted(items, key=lambda x: x.get("applied_at", "") or "", reverse=True)[:MAX_CARDS]

        applied_all = queue["applied"]
        excluded_all = queue["excluded"]
        applied = _newest(applied_all)
        excluded = _newest(excluded_all)

        if applied_all:
            hdr1 = ttk.Label(self.scroll_frame,
                            text=f"▼ 已投递的 (最新{len(applied)}/{len(applied_all)}条待标)  — 默认多半投对了",
                            font=('Microsoft YaHei', 10, 'bold'), foreground='#2e7d32',
                            anchor='w')
            hdr1.grid(row=row, column=0, sticky='ew', padx=5, pady=(5, 3))
            row += 1
            for j in applied:
                row = self._add_job_card(j, "applied", row)
            if len(applied_all) > len(applied):
                ttk.Label(self.scroll_frame,
                         text=f"  …还有 {len(applied_all)-len(applied)} 条未显示，用上方批量按钮一键处理",
                         font=('Microsoft YaHei', 8), foreground=TEXT_LIGHT,
                         anchor='w').grid(row=row, column=0, sticky='ew', padx=12)
                row += 1

        if excluded_all:
            hdr2 = ttk.Label(self.scroll_frame,
                            text=f"▼ 被过滤的 (最新{len(excluded)}/{len(excluded_all)}条待标)  — 漏投检查: 该排吗?",
                            font=('Microsoft YaHei', 10, 'bold'), foreground='#e65100',
                            anchor='w')
            hdr2.grid(row=row, column=0, sticky='ew', padx=5, pady=(12, 3))
            row += 1
            for j in excluded:
                row = self._add_job_card(j, "excluded", row)
            if len(excluded_all) > len(excluded):
                ttk.Label(self.scroll_frame,
                         text=f"  …还有 {len(excluded_all)-len(excluded)} 条未显示，用上方批量按钮一键处理",
                         font=('Microsoft YaHei', 8), foreground=TEXT_LIGHT,
                         anchor='w').grid(row=row, column=0, sticky='ew', padx=12)
                row += 1

        if not applied_all and not excluded_all:
            ttk.Label(self.scroll_frame, text="✅ 没有待标注的职位",
                     font=('Microsoft YaHei', 12), foreground=TEXT_LIGHT,
                     padding=(0, 40)).grid(row=row, column=0)

        self.scroll_frame.columnconfigure(0, weight=1)

    def _add_job_card(self, job, status, row):
        """添加单个职位卡片"""
        job_id = job.get("job_id", "")
        name = job.get("job_name", "")
        company = job.get("company", "")
        salary = job.get("salary", "")
        hit = job.get("hit_keyword", "")
        applied_at = job.get("applied_at", "")[:10]

        card = ttk.LabelFrame(self.scroll_frame, text="", relief='solid', borderwidth=1)
        card.grid(row=row, column=0, sticky='ew', padx=5, pady=3)
        row += 1

        info_text = f"{name}  |  {company}  |  {salary}"
        if status == "excluded" and hit:
            info_text += f"  |  命中'{hit}'被排除"
        if applied_at:
            info_text += f"  |  {applied_at}"
        ttk.Label(card, text=info_text, font=('Microsoft YaHei', 9),
                 anchor='w').pack(fill='x', padx=10, pady=(8, 4))

        btn_frame = ttk.Frame(card)
        btn_frame.pack(fill='x', padx=10, pady=(0, 8))

        if status == "applied":
            ok_text, bad_text = "👍 对", "👎 错投"
        else:
            ok_text, bad_text = "👍 该投", "👎 该排"

        ttk.Button(btn_frame, text=ok_text, command=lambda: self._label(job_id, "accepted"),
                   style='Success.TButton').pack(side='left', padx=(0, 8))
        ttk.Button(btn_frame, text=bad_text, command=lambda: self._label(job_id, "rejected"),
                   style='Danger.TButton').pack(side='left', padx=(0, 8))

        note_entry = ttk.Entry(btn_frame, width=35)
        note_entry.pack(side='left', padx=(8, 0), fill='x', expand=True)
        note_entry.insert(0, "备注(可选)")

        def _on_focus_in(e):
            if note_entry.get() == "备注(可选)":
                note_entry.delete(0, tk.END)
        note_entry.bind("<FocusIn>", _on_focus_in)

        def _on_focus_out(e):
            if not note_entry.get().strip():
                note_entry.insert(0, "备注(可选)")
        note_entry.bind("<FocusOut>", _on_focus_out)

        def _enter_ok(e):
            self._label(job_id, "accepted", note_entry.get())
        def _enter_bad(e):
            self._label(job_id, "rejected", note_entry.get())
        note_entry.bind("<Control-Return>", _enter_ok)
        note_entry.bind("<Shift-Return>", _enter_bad)

        return row

    def _label(self, job_id, label_type, note_entry=None):
        """标注单条"""
        note = ""
        if note_entry and hasattr(note_entry, 'get'):
            val = note_entry.get().strip()
            if val and val != "备注(可选)":
                note = val
        if label_type == "accepted":
            labeler.label_accepted(job_id, note)
        else:
            labeler.label_rejected(job_id, note)
        try:
            metrics.recompute_all_run_metrics()
        except Exception:
            pass
        self._refresh()

    def _batch_applied_ok(self):
        """批量: 已投递的标为投对"""
        queue = labeler.get_review_queue()
        ids = [j["job_id"] for j in queue["applied"]]
        if not ids:
            messagebox.showinfo("提示", "没有待标注的已投递职位")
            return
        if messagebox.askyesno("确认", f"将 {len(ids)} 条已投递职位标记为投对?"):
            labeler.batch_label_applied_accepted(ids)
            try:
                metrics.recompute_all_run_metrics()
            except Exception:
                pass
            self._refresh()

    def _batch_excluded_reject(self):
        """批量: 被过滤的标为拦对"""
        queue = labeler.get_review_queue()
        ids = [j["job_id"] for j in queue["excluded"]]
        if not ids:
            messagebox.showinfo("提示", "没有待标注的被过滤职位")
            return
        if messagebox.askyesno("确认", f"将 {len(ids)} 条被过滤职位标记为拦对?"):
            labeler.batch_label_excluded_rejected(ids)
            try:
                metrics.recompute_all_run_metrics()
            except Exception:
                pass
            self._refresh()

    def _show_metrics(self):
        """显示指标"""
        try:
            metrics.recompute_all_run_metrics()
        except Exception:
            pass
        m = metrics.compute_metrics()
        text = metrics.format_metrics(m)
        health = metrics.flywheel_health()
        win = tk.Toplevel(self.top)
        win.title("飞轮指标")
        win.geometry("600x450")
        text_widget = tk.Text(win, font=('Consolas', 9), wrap='word', bg='white')
        text_widget.pack(fill='both', expand=True, padx=15, pady=15)
        text_widget.insert(tk.END, text + "\n" + health)
        text_widget.config(state='disabled')
