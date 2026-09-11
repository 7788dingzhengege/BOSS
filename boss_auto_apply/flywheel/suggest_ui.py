# 建议确认窗口: 展示挖掘结果, 人工勾选后应用到 rules.json

import tkinter as tk
from tkinter import ttk, messagebox
from . import miner
from . import store

# Google Material Design 配色 (模块级常量, 供所有方法使用)
PRIMARY = '#1a73e8'
SUCCESS = '#43a047'
WARNING = '#ff9800'
DANGER = '#e53935'
LIGHT = '#f8f9fa'
BORDER = '#e0e0e0'
TEXT = '#333333'
TEXT_LIGHT = '#666666'


class SuggestWindow:
    """挖掘建议确认窗口"""

    def __init__(self, parent=None):
        self.top = tk.Toplevel(parent)
        self.top.title("规则挖掘")
        self.top.geometry("750x750")
        self.top.resizable(True, True)
        self.top.minsize(600, 500)
        self.top.lift()
        self.top.focus_force()

        style = ttk.Style()
        style.theme_use('clam')

        style.configure('TFrame', background=LIGHT)
        style.configure('TLabel', background=LIGHT, foreground=TEXT, font=('Microsoft YaHei', 9))
        style.layout('Card.TLabelframe', style.layout('TLabelframe'))
        style.configure('Card.TLabelframe', background='white', bordercolor=BORDER,
                        relief='solid', font=('Microsoft YaHei', 10, 'bold'), foreground=TEXT)
        style.configure('Primary.TButton', background=PRIMARY, foreground='white',
                        font=('Microsoft YaHei', 10), padding=(15, 4))
        style.configure('Light.TButton', background='#e0e0e0', foreground=TEXT,
                        font=('Microsoft YaHei', 9), padding=(10, 3))

        self.top.configure(bg=LIGHT)

        self.suggestions = None
        self.exclude_vars = {}
        self.include_vars = {}
        self.overkill_vars = {}
        self._mine_and_show()

    def _mine_and_show(self):
        """执行挖掘并展示"""
        try:
            self.suggestions = miner.mine_all()
        except Exception as e:
            messagebox.showerror("错误", f"挖掘失败: {e}")
            self.top.destroy()
            return

        self._build_ui()

    def _build_ui(self):
        sug = self.suggestions
        g = sug.get("groups", {})

        top = ttk.Frame(self.top)
        top.pack(fill='x', padx=15, pady=(15, 10))

        ttk.Label(top, text=f"标注总数: {sug.get('total_labels', 0)}  |  "
                          f"G1投对:{g.get('G1',0)} G2错投:{g.get('G2',0)} "
                          f"G3漏投:{g.get('G3',0)} G4拦对:{g.get('G4',0)}",
                 font=('Microsoft YaHei', 10)).pack(anchor='w')
        ttk.Label(top, text="勾选要应用的规则, 点击底部'应用选中'按钮",
                 font=('Microsoft YaHei', 9), foreground=TEXT_LIGHT).pack(anchor='w')

        main = ttk.Frame(self.top)
        main.pack(fill='both', expand=True, padx=15, pady=(0, 10))

        canvas = tk.Canvas(main, bg=LIGHT, highlightthickness=0)
        sb = ttk.Scrollbar(main, orient='vertical', command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas_window = canvas.create_window((0, 0), window=inner, anchor='nw')
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
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

        row = 0

        excl = sug.get("suggested_exclude", [])
        excl_card = ttk.LabelFrame(inner, text=f"建议新增排除词 ({len(excl)}个) — 来自错投样本",
                                   style='Card.TLabelframe')
        excl_card.grid(row=row, column=0, sticky='ew', pady=(0, 8))
        excl_card.configure(padding=10)
        row += 1
        if not excl:
            ttk.Label(excl_card, text="(无)", font=('Microsoft YaHei', 9), foreground=TEXT_LIGHT).pack(pady=5)
        else:
            for s in excl[:20]:
                var = tk.BooleanVar(value=True if s["score"] >= 0.8 else False)
                self.exclude_vars[s["keyword"]] = var
                cb = ttk.Checkbutton(excl_card, text=f"{s['keyword']}  (错投{s['rejected']}次, 投对{s['accepted']}次, 置信度{s['score']})",
                                     variable=var)
                cb.pack(anchor='w', pady=2)

        incl = sug.get("suggested_include", [])
        incl_card = ttk.LabelFrame(inner, text=f"建议新增白名单 ({len(incl)}个) — 来自漏投样本",
                                   style='Card.TLabelframe')
        incl_card.grid(row=row, column=0, sticky='ew', pady=(0, 8))
        incl_card.configure(padding=10)
        row += 1
        if not incl:
            ttk.Label(incl_card, text="(无)", font=('Microsoft YaHei', 9), foreground=TEXT_LIGHT).pack(pady=5)
        else:
            for s in incl[:20]:
                var = tk.BooleanVar(value=True if s["score"] >= 0.8 else False)
                self.include_vars[s["keyword"]] = var
                ttk.Checkbutton(incl_card, text=f"{s['keyword']}  (漏投{s['missed']}次, 拦对{s['blocked']}次, 置信度{s['score']})",
                                variable=var).pack(anchor='w', pady=2)

        alerts = sug.get("overkill_alert", [])
        alert_card = ttk.LabelFrame(inner, text=f"误杀告警 ({len(alerts)}个) — 现有排除词排太宽",
                                   style='Card.TLabelframe')
        alert_card.grid(row=row, column=0, sticky='ew', pady=(0, 8))
        alert_card.configure(padding=10)
        row += 1
        if not alerts:
            ttk.Label(alert_card, text="(无)", font=('Microsoft YaHei', 9), foreground=TEXT_LIGHT).pack(pady=5)
        else:
            for a in alerts:
                var = tk.BooleanVar(value=False)
                self.overkill_vars[a["keyword"]] = var
                samples = ", ".join(a.get("overkill_samples", [])[:3])
                ttk.Checkbutton(alert_card,
                               text=f"移除'{a['keyword']}'  (误杀{a['overkill_count']}次, 样本: {samples})",
                               variable=var).pack(anchor='w', pady=2)

        btn_frame = ttk.Frame(self.top)
        btn_frame.pack(fill='x', padx=15, pady=(0, 15))

        ttk.Button(btn_frame, text="全选", command=self._select_all, style='Light.TButton').pack(side='right', padx=(8, 0))
        ttk.Button(btn_frame, text="应用选中", command=self._apply, style='Primary.TButton').pack(side='right')

        inner.columnconfigure(0, weight=1)

    def _select_all(self):
        for v in self.exclude_vars.values():
            v.set(True)
        for v in self.include_vars.values():
            v.set(True)

    def _apply(self):
        """应用选中的建议"""
        add_excl = [kw for kw, v in self.exclude_vars.items() if v.get()]
        add_incl = [kw for kw, v in self.include_vars.items() if v.get()]
        rm_excl = [kw for kw, v in self.overkill_vars.items() if v.get()]

        if not add_excl and not add_incl and not rm_excl:
            messagebox.showinfo("提示", "未选择任何建议")
            return

        result = miner.apply_suggestions(add_excl, add_incl, rm_excl)
        rules = store.load_rules()
        msg = (f"已应用:\n"
               f"  新增排除词: {result['added_exclude']}\n"
               f"  新增白名单: {result['added_include']}\n"
               f"  移除排除词: {result['removed_exclude']}\n"
               f"  规则版本: v{rules['version']}\n\n"
               f"下次投递将自动加载新规则。")
        messagebox.showinfo("完成", msg)
        self.top.destroy()
