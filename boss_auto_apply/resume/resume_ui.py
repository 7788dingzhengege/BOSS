# 智能简历GUI窗口
# 上传简历 → 粘贴JD → 匹配分析 → 优化建议 → 生成打招呼语

import os
import sys
import logging
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from threading import Thread

logger = logging.getLogger("boss_applier")

# Google Material Design 配色
PRIMARY = '#1a73e8'
SUCCESS = '#43a047'
WARNING = '#ff9800'
DANGER = '#e53935'
LIGHT = '#f8f9fa'
BORDER = '#e0e0e0'
TEXT = '#333333'
TEXT_LIGHT = '#666666'


class ResumeWindow:
    """智能简历窗口"""

    def __init__(self, parent=None):
        self.top = tk.Toplevel(parent)
        self.top.title("智能简历助手")
        self.top.geometry("700x720")
        self.top.resizable(True, True)
        self.top.minsize(600, 600)
        self.top.lift()
        self.top.focus_force()

        self._resume_text = None
        self._resume_path = None
        self._match_result = None
        self._jd_text = None

        self._build_ui()

    def _build_ui(self):
        # 颜色样式
        style = ttk.Style()
        style.layout('Card.TLabelframe', style.layout('TLabelframe'))
        style.configure('Card.TLabelframe', background='white', bordercolor=BORDER,
                        relief='solid', font=('Microsoft YaHei', 9, 'bold'), foreground=TEXT)
        style.configure('Primary.TButton', background=PRIMARY, foreground='white',
                        font=('Microsoft YaHei', 9), padding=(8, 4))
        style.map('Primary.TButton', background=[('active', '#1557b0')])
        style.configure('Success.TButton', background=SUCCESS, foreground='white',
                        font=('Microsoft YaHei', 9), padding=(8, 4))
        style.configure('Warning.TButton', background=WARNING, foreground='white',
                        font=('Microsoft YaHei', 9), padding=(8, 4))
        style.configure('Light.TButton', background='#e0e0e0', foreground=TEXT,
                        font=('Microsoft YaHei', 9), padding=(8, 4))

        self.top.configure(bg=LIGHT)

        # ====== 简历上传区 ======
        upload_card = ttk.LabelFrame(self.top, text="简历上传", style='Card.TLabelframe')
        upload_card.pack(fill='x', padx=12, pady=(8, 6))
        upload_card.configure(padding=10)

        row = ttk.Frame(upload_card)
        row.pack(fill='x')
        self.resume_label = ttk.Label(row, text="未选择文件", foreground=TEXT_LIGHT)
        self.resume_label.pack(side='left')
        ttk.Button(row, text="选择PDF/DOCX", command=self._select_resume,
                   style='Primary.TButton').pack(side='right')

        # ====== JD输入区 ======
        jd_card = ttk.LabelFrame(self.top, text="目标岗位JD", style='Card.TLabelframe')
        jd_card.pack(fill='both', expand=True, padx=12, pady=(0, 6))
        jd_card.configure(padding=10)

        # JD搜索按钮行（新增，不影响原有逻辑）
        jd_btn_row = ttk.Frame(jd_card)
        jd_btn_row.pack(fill='x', pady=(0, 4))
        ttk.Button(jd_btn_row, text="搜索BOSS职位JD", command=self._open_jd_search,
                   style='Primary.TButton').pack(side='left')
        ttk.Label(jd_btn_row, text="或手动粘贴JD ↓", foreground=TEXT_LIGHT,
                  font=('Microsoft YaHei', 8)).pack(side='left', padx=(8, 0))

        self.jd_text = tk.Text(jd_card, height=8, font=('Microsoft YaHei', 9),
                               wrap='word', relief='solid', bd=1,
                               bg='white', fg=TEXT)
        jd_scroll = ttk.Scrollbar(jd_card, command=self.jd_text.yview)
        self.jd_text.configure(yscrollcommand=jd_scroll.set)
        self.jd_text.pack(side='left', fill='both', expand=True)
        jd_scroll.pack(side='right', fill='y')

        # ====== 操作按钮区 ======
        btn_card = ttk.LabelFrame(self.top, text="智能分析", style='Card.TLabelframe')
        btn_card.pack(fill='x', padx=12, pady=(0, 6))
        btn_card.configure(padding=8)

        btn_row = ttk.Frame(btn_card)
        btn_row.pack(fill='x')
        ttk.Button(btn_row, text="匹配分析", command=self._do_match,
                   style='Primary.TButton').pack(side='left', padx=(0, 6))
        ttk.Button(btn_row, text="优化建议", command=self._do_optimize,
                   style='Warning.TButton').pack(side='left', padx=(0, 6))
        ttk.Button(btn_row, text="生成打招呼语", command=self._do_greeting,
                   style='Success.TButton').pack(side='left', padx=(0, 6))
        ttk.Button(btn_row, text="一键全做", command=self._do_all,
                   style='Light.TButton').pack(side='left')

        # ====== 结果展示区 ======
        result_card = ttk.LabelFrame(self.top, text="分析结果", style='Card.TLabelframe')
        result_card.pack(fill='both', expand=True, padx=12, pady=(0, 6))
        result_card.configure(padding=10)

        # 用Canvas+Frame实现滚动
        canvas = tk.Canvas(result_card, bg='white', highlightthickness=0)
        scrollbar = ttk.Scrollbar(result_card, command=canvas.yview)
        self.scroll_frame = ttk.Frame(canvas)

        self.scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas_window = canvas.create_window((0, 0), window=self.scroll_frame, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind('<Configure>', _on_canvas_configure)

        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # 默认提示
        self._result_label = ttk.Label(self.scroll_frame, text="上传简历并粘贴JD后，点击上方按钮开始分析",
                                       foreground=TEXT_LIGHT, wraplength=600)
        self._result_label.pack(anchor='w', pady=10)

        # ====== 状态栏 ======
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self.top, textvariable=self.status_var, foreground=TEXT_LIGHT,
                  font=('Microsoft YaHei', 8)).pack(fill='x', padx=12, pady=(0, 8))

    def _select_resume(self):
        """选择简历文件"""
        path = filedialog.askopenfilename(
            title="选择简历文件",
            filetypes=[("PDF文件", "*.pdf"), ("Word文件", "*.docx"), ("所有文件", "*.*")]
        )
        if not path:
            return

        self._resume_path = path
        filename = os.path.basename(path)
        self.resume_label.config(text=f"已选择: {filename}")

        # 解析简历
        def _parse():
            try:
                if path.lower().endswith('.pdf'):
                    from resume.parser import ResumeParser
                    parser = ResumeParser()
                    result = parser.parse(path)
                    if result:
                        self._resume_text = result["raw_text"]
                        skills = result.get("skills", [])
                        self.top.after(0, lambda: self.status_var.set(
                            f"简历解析成功: {result['char_count']}字符, 技能: {', '.join(skills[:5])}"))
                    else:
                        self.top.after(0, lambda: self.status_var.set("简历解析失败"))
                elif path.lower().endswith('.docx'):
                    from docx import Document
                    doc = Document(path)
                    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
                    self._resume_text = text
                    self.top.after(0, lambda: self.status_var.set(f"简历解析成功: {len(text)}字符"))
                else:
                    self.top.after(0, lambda: self.status_var.set("不支持的文件格式"))
            except Exception as e:
                err_msg = str(e)
                self.top.after(0, lambda: self.status_var.set(f"解析失败: {err_msg}"))

        self.status_var.set("解析简历中...")
        Thread(target=_parse, daemon=True).start()

    def _get_jd_text(self):
        """获取JD文本"""
        text = self.jd_text.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("提示", "请先粘贴目标岗位的JD")
            return None
        return text

    def _check_ready(self):
        """检查前置条件"""
        if not self._resume_text:
            messagebox.showwarning("提示", "请先上传简历")
            return False
        jd = self._get_jd_text()
        if not jd:
            return False
        self._jd_text = jd
        return True

    def _get_config(self):
        """获取DeepSeek配置"""
        from config import AGENT_FILTER_CONFIG
        return AGENT_FILTER_CONFIG

    def _clear_results(self):
        """清空结果区"""
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

    def _add_result_section(self, title, content):
        """添加一个结果段落"""
        ttk.Label(self.scroll_frame, text=title, font=('Microsoft YaHei', 10, 'bold'),
                  foreground=PRIMARY).pack(anchor='w', pady=(8, 2))
        ttk.Label(self.scroll_frame, text=content, font=('Microsoft YaHei', 9),
                  foreground=TEXT, wraplength=620, justify='left').pack(anchor='w', pady=(0, 4))

    def _do_match(self):
        """匹配分析"""
        if not self._check_ready():
            return

        def _run():
            try:
                from resume.matcher import ResumeMatcher
                matcher = ResumeMatcher(self._get_config())
                result = matcher.match(self._resume_text, self._jd_text)

                if not result:
                    self.top.after(0, lambda: self.status_var.set("匹配分析失败"))
                    return

                self._match_result = result
                score = result.get("overall_score", 0)
                matched = result.get("skill_match", {}).get("matched", [])
                missing = result.get("skill_match", {}).get("missing", [])
                strengths = result.get("strengths", [])
                weaknesses = result.get("weaknesses", [])

                def _update():
                    self._clear_results()
                    score_color = SUCCESS if score >= 70 else (WARNING if score >= 50 else DANGER)
                    score_label = tk.Label(self.scroll_frame, text=f"匹配度: {score}/100",
                                           font=('Microsoft YaHei', 14, 'bold'),
                                           fg=score_color, bg='white')
                    score_label.pack(anchor='w', pady=(4, 8))

                    if matched:
                        self._add_result_section("✓ 匹配技能", ", ".join(matched))
                    if missing:
                        self._add_result_section("✗ 缺失技能", ", ".join(missing))
                    if strengths:
                        self._add_result_section("★ 亮点", "\n".join(f"• {s}" for s in strengths))
                    if weaknesses:
                        self._add_result_section("⚠ 短板", "\n".join(f"• {w}" for w in weaknesses))

                    self.status_var.set(f"匹配分析完成: {score}分")

                self.top.after(0, _update)
            except Exception as e:
                err_msg = str(e)
                self.top.after(0, lambda: self.status_var.set(f"匹配分析出错: {err_msg}"))

        self.status_var.set("匹配分析中...")
        Thread(target=_run, daemon=True).start()

    def _do_optimize(self):
        """优化建议"""
        if not self._check_ready():
            return

        def _run():
            try:
                from resume.optimizer import ResumeOptimizer
                optimizer = ResumeOptimizer(self._get_config())
                result = optimizer.optimize(self._resume_text, self._jd_text, self._match_result)

                if not result:
                    self.top.after(0, lambda: self.status_var.set("优化建议生成失败"))
                    return

                mods = result.get("modifications", [])
                summary = result.get("summary", "")
                improvement = result.get("estimated_score_improvement", 0)

                def _update():
                    self._clear_results()
                    self._add_result_section("整体建议", summary)
                    self._add_result_section("预计提升", f"+{improvement} 分")

                    for i, mod in enumerate(mods, 1):
                        action_map = {"add": "新增", "modify": "修改", "reorder": "调序", "highlight": "突出"}
                        action = action_map.get(mod.get("action", ""), mod.get("action", ""))
                        section = mod.get("section", "")
                        suggested = mod.get("suggested", "")
                        reason = mod.get("reason", "")
                        original = mod.get("original", "")

                        ttk.Label(self.scroll_frame,
                                  text=f"{i}. [{action}] {section}",
                                  font=('Microsoft YaHei', 9, 'bold'),
                                  foreground=TEXT).pack(anchor='w', pady=(6, 1))
                        if original:
                            ttk.Label(self.scroll_frame, text=f"   原文: {original[:80]}",
                                      foreground=TEXT_LIGHT, wraplength=600,
                                      font=('Microsoft YaHei', 8)).pack(anchor='w')
                        if suggested:
                            ttk.Label(self.scroll_frame, text=f"   建议: {suggested[:80]}",
                                      foreground=SUCCESS, wraplength=600,
                                      font=('Microsoft YaHei', 8)).pack(anchor='w')
                        ttk.Label(self.scroll_frame, text=f"   原因: {reason}",
                                  foreground=TEXT_LIGHT, wraplength=600,
                                  font=('Microsoft YaHei', 8)).pack(anchor='w')

                    self.status_var.set(f"优化建议完成: {len(mods)}条修改")

                self.top.after(0, _update)
            except Exception as e:
                err_msg = str(e)
                self.top.after(0, lambda: self.status_var.set(f"优化建议出错: {err_msg}"))

        self.status_var.set("生成优化建议中...")
        Thread(target=_run, daemon=True).start()

    def _do_greeting(self):
        """生成打招呼语"""
        if not self._check_ready():
            return

        def _run():
            try:
                from resume.greeting import GreetingGenerator
                gen = GreetingGenerator(self._get_config())
                result = gen.generate(self._resume_text, self._jd_text)

                if not result:
                    self.top.after(0, lambda: self.status_var.set("打招呼语生成失败"))
                    return

                greeting = result.get("greeting", "")
                highlights = result.get("highlights", [])

                def _update():
                    self._clear_results()
                    self._add_result_section("打招呼语", greeting)

                    # 复制按钮
                    def _copy():
                        self.top.clipboard_clear()
                        self.top.clipboard_append(greeting)
                        self.status_var.set("已复制到剪贴板")

                    ttk.Button(self.scroll_frame, text="复制打招呼语",
                               command=_copy, style='Success.TButton').pack(anchor='w', pady=(6, 4))

                    if highlights:
                        self._add_result_section("突出要点", "\n".join(f"• {h}" for h in highlights))

                    self.status_var.set("打招呼语生成完成")

                self.top.after(0, _update)
            except Exception as e:
                err_msg = str(e)
                self.top.after(0, lambda: self.status_var.set(f"打招呼语生成出错: {err_msg}"))

        self.status_var.set("生成打招呼语中...")
        Thread(target=_run, daemon=True).start()

    def _open_jd_search(self):
        """打开JD搜索窗口"""
        from resume.jd_search_ui import JDSearchWindow
        JDSearchWindow(self.top, callback=self._on_jd_selected)

    def _on_jd_selected(self, jd_text, job_info):
        """JD搜索回调：自动填充JD到文本框"""
        self.jd_text.delete("1.0", "end")
        self.jd_text.insert("1.0", jd_text)
        self.status_var.set(f"已加载JD: {job_info.get('name', '')} | {job_info.get('company', '')}")

    def _do_all(self):
        """一键全做：匹配分析 → 优化建议 → 打招呼语"""
        if not self._check_ready():
            return

        def _run():
            try:
                from resume.matcher import ResumeMatcher
                from resume.optimizer import ResumeOptimizer
                from resume.greeting import GreetingGenerator

                config = self._get_config()

                # 1. 匹配分析
                self.top.after(0, lambda: self.status_var.set("[1/3] 匹配分析中..."))
                matcher = ResumeMatcher(config)
                match_result = matcher.match(self._resume_text, self._jd_text)
                self._match_result = match_result

                # 2. 优化建议
                self.top.after(0, lambda: self.status_var.set("[2/3] 生成优化建议中..."))
                optimizer = ResumeOptimizer(config)
                optimize_result = optimizer.optimize(self._resume_text, self._jd_text, match_result)

                # 3. 打招呼语
                self.top.after(0, lambda: self.status_var.set("[3/3] 生成打招呼语中..."))
                gen = GreetingGenerator(config)
                greeting_result = gen.generate(self._resume_text, self._jd_text)

                def _update():
                    self._clear_results()

                    # 匹配度
                    if match_result:
                        score = match_result.get("overall_score", 0)
                        matched = match_result.get("skill_match", {}).get("matched", [])
                        missing = match_result.get("skill_match", {}).get("missing", [])
                        score_color = SUCCESS if score >= 70 else (WARNING if score >= 50 else DANGER)
                        tk.Label(self.scroll_frame, text=f"匹配度: {score}/100",
                                 font=('Microsoft YaHei', 14, 'bold'),
                                 fg=score_color, bg='white').pack(anchor='w', pady=(4, 4))
                        if matched:
                            self._add_result_section("✓ 匹配技能", ", ".join(matched))
                        if missing:
                            self._add_result_section("✗ 缺失技能", ", ".join(missing))

                    # 优化建议
                    if optimize_result:
                        summary = optimize_result.get("summary", "")
                        mods = optimize_result.get("modifications", [])
                        improvement = optimize_result.get("estimated_score_improvement", 0)
                        self._add_result_section("优化建议", f"{summary} (预计提升+{improvement}分)")
                        for i, mod in enumerate(mods[:5], 1):  # 只显示前5条
                            action_map = {"add": "新增", "modify": "修改", "reorder": "调序", "highlight": "突出"}
                            action = action_map.get(mod.get("action", ""), mod.get("action", ""))
                            ttk.Label(self.scroll_frame,
                                      text=f"  {i}. [{action}] {mod.get('section', '')}: {mod.get('suggested', '')[:60]}",
                                      font=('Microsoft YaHei', 8), foreground=TEXT,
                                      wraplength=620).pack(anchor='w', pady=(2, 0))

                    # 打招呼语
                    if greeting_result:
                        greeting = greeting_result.get("greeting", "")
                        self._add_result_section("打招呼语", greeting)

                        def _copy():
                            self.top.clipboard_clear()
                            self.top.clipboard_append(greeting)
                            self.status_var.set("已复制到剪贴板")

                        ttk.Button(self.scroll_frame, text="复制打招呼语",
                                   command=_copy, style='Success.TButton').pack(anchor='w', pady=(6, 4))

                    self.status_var.set("全部分析完成!")

                self.top.after(0, _update)
            except Exception as e:
                err_msg = str(e)
                self.top.after(0, lambda: self.status_var.set(f"分析出错: {err_msg}"))

        Thread(target=_run, daemon=True).start()
