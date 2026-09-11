# JD搜索UI窗口
# 搜索BOSS直聘职位 → 选择 → 自动获取JD全文 → 回调填充到智能简历窗口

import tkinter as tk
from tkinter import ttk
from threading import Thread

# Google Material Design 配色
PRIMARY = '#1a73e8'
SUCCESS = '#43a047'
WARNING = '#ff9800'
LIGHT = '#f8f9fa'
BORDER = '#e0e0e0'
TEXT = '#333333'
TEXT_LIGHT = '#666666'


class JDSearchWindow:
    """BOSS直聘JD搜索窗口"""

    def __init__(self, parent=None, callback=None):
        """
        :param parent: 父窗口
        :param callback: 选择JD后的回调函数，签名为 callback(jd_text, job_info)
        """
        self.callback = callback
        self.searcher = None
        self._jobs = []

        self.top = tk.Toplevel(parent)
        self.top.title("搜索BOSS职位JD")
        self.top.geometry("680x560")
        self.top.resizable(True, True)
        self.top.minsize(550, 450)
        self.top.lift()
        self.top.focus_force()

        self._build_ui()

    def _build_ui(self):
        style = ttk.Style()
        style.layout('Card.TLabelframe', style.layout('TLabelframe'))
        style.configure('Card.TLabelframe', background='white', bordercolor=BORDER,
                        relief='solid', font=('Microsoft YaHei', 9, 'bold'), foreground=TEXT)
        style.configure('Primary.TButton', background=PRIMARY, foreground='white',
                        font=('Microsoft YaHei', 9), padding=(8, 4))
        style.map('Primary.TButton', background=[('active', '#1557b0')])
        style.configure('Success.TButton', background=SUCCESS, foreground='white',
                        font=('Microsoft YaHei', 9), padding=(8, 4))
        style.configure('Light.TButton', background='#e0e0e0', foreground=TEXT,
                        font=('Microsoft YaHei', 9), padding=(8, 4))

        self.top.configure(bg=LIGHT)

        # ====== 搜索区 ======
        search_card = ttk.LabelFrame(self.top, text="搜索条件", style='Card.TLabelframe')
        search_card.pack(fill='x', padx=12, pady=(8, 6))
        search_card.configure(padding=10)

        input_row = ttk.Frame(search_card)
        input_row.pack(fill='x')

        ttk.Label(input_row, text="关键词:", font=('Microsoft YaHei', 9)).pack(side='left')
        self.kw_var = tk.StringVar(value="AI产品经理")
        ttk.Entry(input_row, textvariable=self.kw_var, width=18).pack(side='left', padx=(4, 10))

        ttk.Label(input_row, text="城市:", font=('Microsoft YaHei', 9)).pack(side='left')
        from config import CITY_OPTIONS
        self.city_var = tk.StringVar(value="北京")
        ttk.Combobox(input_row, textvariable=self.city_var,
                     values=list(CITY_OPTIONS.keys()),
                     state='readonly', width=8).pack(side='left', padx=(4, 10))

        self.intern_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(input_row, text="只搜实习", variable=self.intern_var).pack(side='left', padx=(0, 10))

        self.search_btn = ttk.Button(input_row, text="搜索", command=self._do_search,
                                     style='Primary.TButton')
        self.search_btn.pack(side='left')

        # ====== 结果列表 ======
        list_card = ttk.LabelFrame(self.top, text="搜索结果（双击选择）", style='Card.TLabelframe')
        list_card.pack(fill='both', expand=True, padx=12, pady=(0, 6))
        list_card.configure(padding=10)

        columns = ("name", "company", "salary")
        self.tree = ttk.Treeview(list_card, columns=columns, show='headings', height=12)
        self.tree.heading("name", text="职位名")
        self.tree.heading("company", text="公司")
        self.tree.heading("salary", text="薪资")
        self.tree.column("name", width=220)
        self.tree.column("company", width=220)
        self.tree.column("salary", width=100)

        tree_scroll = ttk.Scrollbar(list_card, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side='left', fill='both', expand=True)
        tree_scroll.pack(side='right', fill='y')

        self.tree.bind('<Double-1>', lambda e: self._on_select_btn())

        # ====== 操作区 ======
        btn_row = ttk.Frame(self.top)
        btn_row.pack(fill='x', padx=12, pady=(0, 8))

        ttk.Button(btn_row, text="选择此JD", command=self._on_select_btn,
                   style='Success.TButton').pack(side='left')
        ttk.Button(btn_row, text="关闭", command=self._close,
                   style='Light.TButton').pack(side='right')

        # ====== 状态栏 ======
        self.status_var = tk.StringVar(value="输入关键词，点击搜索BOSS直聘职位")
        ttk.Label(self.top, textvariable=self.status_var, foreground=TEXT_LIGHT,
                  font=('Microsoft YaHei', 8)).pack(fill='x', padx=12, pady=(0, 8))

    def _do_search(self):
        """执行搜索"""
        keyword = self.kw_var.get().strip()
        if not keyword:
            return

        from config import CITY_OPTIONS
        city_code = CITY_OPTIONS.get(self.city_var.get(), "101010100")
        intern_only = self.intern_var.get()

        def _run():
            try:
                from resume.jd_searcher import JDSearcher
                if self.searcher is None:
                    self.searcher = JDSearcher()

                self.top.after(0, lambda: self.status_var.set("正在搜索，请稍候..."))
                self.top.after(0, lambda: self.search_btn.config(state='disabled'))

                jobs = self.searcher.search(keyword, city_code, intern_only)
                self._jobs = jobs

                def _update():
                    for item in self.tree.get_children():
                        self.tree.delete(item)
                    for i, job in enumerate(jobs):
                        self.tree.insert('', 'end', iid=str(i),
                                         values=(job.get('name', ''),
                                                 job.get('company', ''),
                                                 job.get('salary', '')))
                    self.status_var.set(f"找到 {len(jobs)} 个职位，双击或选中后点击「选择此JD」")
                    self.search_btn.config(state='normal')

                self.top.after(0, _update)
            except Exception as e:
                err_msg = str(e)
                self.top.after(0, lambda: self.status_var.set(f"搜索失败: {err_msg}"))
                self.top.after(0, lambda: self.search_btn.config(state='normal'))

        Thread(target=_run, daemon=True).start()

    def _on_select_btn(self):
        """选择当前JD"""
        sel = self.tree.selection()
        if not sel:
            self.status_var.set("请先选择一个职位")
            return

        idx = int(sel[0])
        if idx >= len(self._jobs):
            return

        job = self._jobs[idx]
        job_name = job.get('name', '')

        def _run():
            try:
                self.top.after(0, lambda: self.status_var.set(f"正在获取JD: {job_name}..."))

                jd_text = self.searcher.fetch_jd(job_name)

                if not jd_text:
                    self.top.after(0, lambda: self.status_var.set("JD获取失败，可手动粘贴"))
                    return

                if self.callback:
                    self.callback(jd_text, job)

                self.top.after(0, lambda: self.status_var.set(f"已获取JD: {job_name}"))
                self.top.after(0, self._close)
            except Exception as e:
                err_msg = str(e)
                self.top.after(0, lambda: self.status_var.set(f"获取JD失败: {err_msg}"))

        Thread(target=_run, daemon=True).start()

    def _close(self):
        if self.searcher:
            self.searcher.close()
        self.top.destroy()
