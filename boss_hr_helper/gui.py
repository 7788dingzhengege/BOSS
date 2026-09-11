# BOSS直聘HR助手 - GUI界面

import sys
import os
import json
import threading
import logging
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from config import (
    API_CONFIG, DEFAULT_POSITION, COMPANY_INFO,
    RESUME_FILTER_CONFIG, AUTO_REPLY_CONFIG,
    SETTINGS_FILE, REPLY_MODE, REPLY_TEMPLATES,
)
from message_handler import MessageHandler

logger = logging.getLogger("boss_hr")

# 颜色常量（Material Design）
PRIMARY = "#1a73e8"
SUCCESS = "#43a047"
WARNING = "#fb8c00"
DANGER = "#e53935"
INFO = "#00acc1"
LIGHT = "#f5f5f5"
DARK = "#333333"
TEXT_PRIMARY = "#202124"
TEXT_SECONDARY = "#5f6368"
TEXT_LIGHT = "#ffffff"
BG_COLOR = "#f8f9fa"
CARD_BG = "#ffffff"


class HRHelperGUI:
    """HR助手主窗口"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("BOSS直聘 HR助手 v0.1")
        self.root.geometry("700x750")
        self.root.configure(bg=BG_COLOR)
        self.root.resizable(True, True)

        self.handler = None
        self._running = False
        self._settings = self._load_settings()

        self._setup_styles()
        self._build_ui()

    def _load_settings(self):
        """加载设置"""
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_settings(self):
        """保存设置"""
        os.makedirs(os.path.dirname(SETTINGS_FILE) or '.', exist_ok=True)
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _setup_styles(self):
        """设置样式"""
        style = ttk.Style()
        style.theme_use('clam')

        # 字体
        default_font = ("Microsoft YaHei", 9)
        title_font = ("Microsoft YaHei", 12, "bold")
        small_font = ("Microsoft YaHei", 8)

        style.configure('.', font=default_font, background=BG_COLOR, foreground=TEXT_PRIMARY)

        # LabelFrame
        style.layout('Card.TLabelframe', style.layout('TLabelframe'))
        style.configure('Card.TLabelframe', background=CARD_BG, relief='flat', borderwidth=1)
        style.configure('Card.TLabelframe.Label', font=("Microsoft YaHei", 10, "bold"),
                        background=CARD_BG, foreground=PRIMARY)

        # 按钮样式
        style.configure('Primary.TButton', font=default_font, background=PRIMARY,
                        foreground=TEXT_LIGHT, padding=(15, 8), borderwidth=0)
        style.map('Primary.TButton', background=[('active', '#1557b0')])

        style.configure('Success.TButton', font=default_font, background=SUCCESS,
                        foreground=TEXT_LIGHT, padding=(15, 8), borderwidth=0)
        style.map('Success.TButton', background=[('active', '#2e7d32')])

        style.configure('Warning.TButton', font=default_font, background=WARNING,
                        foreground=TEXT_LIGHT, padding=(15, 8), borderwidth=0)
        style.map('Warning.TButton', background=[('active', '#ef6c00')])

        style.configure('Danger.TButton', font=default_font, background=DANGER,
                        foreground=TEXT_LIGHT, padding=(15, 8), borderwidth=0)
        style.map('Danger.TButton', background=[('active', '#c62828')])

        style.configure('Info.TButton', font=default_font, background=INFO,
                        foreground=TEXT_LIGHT, padding=(15, 8), borderwidth=0)
        style.map('Info.TButton', background=[('active', '#00838f')])

        style.configure('Light.TButton', font=default_font, background=LIGHT,
                        foreground=TEXT_PRIMARY, padding=(12, 6), borderwidth=0)
        style.map('Light.TButton', background=[('active', '#e0e0e0')])

        # Entry
        style.configure('TEntry', fieldbackground='white', padding=5)

        # Combobox
        style.configure('TCombobox', fieldbackground='white', padding=3)

        # Notebook
        style.configure('TNotebook', background=BG_COLOR, borderwidth=0)
        style.configure('TNotebook.Tab', padding=(20, 10), font=("Microsoft YaHei", 9, "bold"))
        style.map('TNotebook.Tab', background=[('selected', CARD_BG), ('!selected', '#e8eaed')],
                  foreground=[('selected', PRIMARY), ('!selected', TEXT_SECONDARY)])

    def _build_ui(self):
        """构建界面"""
        # 顶部状态栏
        top_bar = tk.Frame(self.root, bg=PRIMARY, height=50)
        top_bar.pack(fill='x')
        top_bar.pack_propagate(False)

        title_label = tk.Label(top_bar, text="🤖 BOSS直聘 HR助手",
                               font=("Microsoft YaHei", 13, "bold"),
                               bg=PRIMARY, fg=TEXT_LIGHT)
        title_label.pack(side='left', padx=15)

        self.status_label = tk.Label(top_bar, text="⏸ 未启动",
                                     font=("Microsoft YaHei", 9),
                                     bg=PRIMARY, fg="#bbdefb")
        self.status_label.pack(side='right', padx=15)

        # 主内容区（Notebook）
        main_frame = tk.Frame(self.root, bg=BG_COLOR)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)

        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill='both', expand=True)

        # Tab1: 简历筛选
        tab_filter = ttk.Frame(notebook, style='Card.TLabelframe')
        notebook.add(tab_filter, text="📄 简历筛选")
        self._build_filter_tab(tab_filter)

        # Tab2: 自动回复
        tab_reply = ttk.Frame(notebook, style='Card.TLabelframe')
        notebook.add(tab_reply, text="💬 自动回复")
        self._build_reply_tab(tab_reply)

        # Tab3: 岗位设置
        tab_settings = ttk.Frame(notebook, style='Card.TLabelframe')
        notebook.add(tab_settings, text="⚙️ 岗位设置")
        self._build_settings_tab(tab_settings)

        # Tab4: 候选人列表
        tab_candidates = ttk.Frame(notebook, style='Card.TLabelframe')
        notebook.add(tab_candidates, text="👥 候选人")
        self._build_candidates_tab(tab_candidates)

    def _build_filter_tab(self, parent):
        """简历筛选Tab"""
        # 岗位信息卡片
        pos_frame = ttk.LabelFrame(parent, text=" 当前岗位 ", style='Card.TLabelframe', padding=10)
        pos_frame.pack(fill='x', padx=10, pady=(10, 5))

        pos_info = f"{DEFAULT_POSITION['name']} | {COMPANY_INFO['name']}"
        tk.Label(pos_frame, text=pos_info, font=("Microsoft YaHei", 10, "bold"),
                 bg=CARD_BG, fg=PRIMARY).pack(anchor='w')

        # 简历输入区
        input_frame = ttk.LabelFrame(parent, text=" 粘贴简历文本 ", style='Card.TLabelframe', padding=10)
        input_frame.pack(fill='both', expand=True, padx=10, pady=5)

        self.resume_text = scrolledtext.ScrolledText(
            input_frame, height=10, font=("Microsoft YaHei", 9),
            wrap='word', relief='flat', bg='#fafafa'
        )
        self.resume_text.pack(fill='both', expand=True)

        # 按钮区
        btn_frame = tk.Frame(parent, bg=BG_COLOR)
        btn_frame.pack(fill='x', padx=10, pady=8)

        ttk.Button(btn_frame, text="🔍 开始筛选", style='Primary.TButton',
                   command=self._on_filter_resume).pack(side='left', padx=(0, 10))
        ttk.Button(btn_frame, text="🗑 清空", style='Light.TButton',
                   command=self._on_clear_resume).pack(side='left')

        # 筛选结果
        result_frame = ttk.LabelFrame(parent, text=" 筛选结果 ", style='Card.TLabelframe', padding=10)
        result_frame.pack(fill='both', expand=True, padx=10, pady=(5, 10))

        # 评分行
        score_row = tk.Frame(result_frame, bg=CARD_BG)
        score_row.pack(fill='x', pady=(0, 8))

        tk.Label(score_row, text="评分:", font=("Microsoft YaHei", 9),
                 bg=CARD_BG, fg=TEXT_SECONDARY).pack(side='left')
        self.score_label = tk.Label(score_row, text="--",
                                    font=("Microsoft YaHei", 20, "bold"),
                                    bg=CARD_BG, fg=PRIMARY)
        self.score_label.pack(side='left', padx=8)
        self.level_label = tk.Label(score_row, text="",
                                    font=("Microsoft YaHei", 10, "bold"),
                                    bg=CARD_BG, fg=WARNING)
        self.level_label.pack(side='left', padx=10)

        # 结果详情
        self.result_text = scrolledtext.ScrolledText(
            result_frame, height=8, font=("Microsoft YaHei", 9),
            wrap='word', relief='flat', bg='#fafafa'
        )
        self.result_text.pack(fill='both', expand=True)

    def _build_reply_tab(self, parent):
        """自动回复Tab"""
        # 自动回复控制
        control_frame = ttk.LabelFrame(parent, text=" 自动回复控制 ", style='Card.TLabelframe', padding=10)
        control_frame.pack(fill='x', padx=10, pady=(10, 5))

        btn_row = tk.Frame(control_frame, bg=CARD_BG)
        btn_row.pack(fill='x', pady=3)
        self.start_reply_btn = ttk.Button(btn_row, text="▶️ 启动自动回复", style='Success.TButton',
                                          command=self._on_start_auto_reply)
        self.start_reply_btn.pack(side='left', padx=(0, 8))
        self.stop_reply_btn = ttk.Button(btn_row, text="⏹ 停止", style='Danger.TButton',
                                       command=self._on_stop_auto_reply, state='disabled')
        self.stop_reply_btn.pack(side='left')

        self.reply_status_var = tk.StringVar(value="未启动")
        tk.Label(control_frame, textvariable=self.reply_status_var,
                 font=("Microsoft YaHei", 9), bg=CARD_BG, fg=TEXT_SECONDARY).pack(anchor='w', pady=(5, 0))

        # 回复设置卡片
        config_frame = ttk.LabelFrame(parent, text=" 回复设置 ", style='Card.TLabelframe', padding=10)
        config_frame.pack(fill='x', padx=10, pady=5)

        self.auto_reply_var = tk.BooleanVar(value=AUTO_REPLY_CONFIG.get("enabled", False))
        tk.Checkbutton(config_frame, text="启用自动回复", variable=self.auto_reply_var,
                       font=("Microsoft YaHei", 9), bg=CARD_BG, fg=TEXT_PRIMARY,
                       activebackground=CARD_BG).pack(anchor='w', pady=2)

        self.working_hours_var = tk.BooleanVar(value=AUTO_REPLY_CONFIG.get("working_hours_only", True))
        tk.Checkbutton(config_frame, text="仅工作时间回复 (9:00-19:00)", variable=self.working_hours_var,
                       font=("Microsoft YaHei", 9), bg=CARD_BG, fg=TEXT_PRIMARY,
                       activebackground=CARD_BG).pack(anchor='w', pady=2)

        # 回复模式
        mode_row = tk.Frame(config_frame, bg=CARD_BG)
        mode_row.pack(fill='x', pady=2)
        tk.Label(mode_row, text="回复模式:", bg=CARD_BG, font=("Microsoft YaHei", 9)).pack(side='left')
        self.reply_mode_var = tk.StringVar(value="固定模板模式")
        mode_combo = ttk.Combobox(mode_row, textvariable=self.reply_mode_var, state='readonly',
                                  values=["固定模板模式", "AI生成模式"], width=15)
        mode_combo.pack(side='left', padx=8)

        # 运行日志
        log_frame = ttk.LabelFrame(parent, text=" 运行日志 ", style='Card.TLabelframe', padding=8)
        log_frame.pack(fill='both', expand=True, padx=10, pady=5)

        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=6, font=("Consolas", 8),
            wrap='word', relief='flat', bg='#1e1e1e', fg='#d4d4d4',
            insertbackground='white'
        )
        self.log_text.pack(fill='both', expand=True)

        # 场景选择 + 模板编辑
        template_frame = ttk.LabelFrame(parent, text=" 回复模板编辑 ", style='Card.TLabelframe', padding=10)
        template_frame.pack(fill='x', padx=10, pady=(5, 10))

        scene_row = tk.Frame(template_frame, bg=CARD_BG)
        scene_row.pack(fill='x', pady=(0, 8))
        tk.Label(scene_row, text="选择场景:", bg=CARD_BG, font=("Microsoft YaHei", 9, "bold")).pack(side='left')

        self.template_scene_var = tk.StringVar(value="收到新投递（初筛通过，邀请沟通）")
        template_scene_combo = ttk.Combobox(template_frame, textvariable=self.template_scene_var, state='readonly',
                                            values=list(REPLY_TEMPLATES.keys()))
        template_scene_combo.pack(fill='x', pady=(0, 8))
        template_scene_combo.bind('<<ComboboxSelected>>', lambda e: self._on_template_scene_change())

        tk.Label(template_frame, text="回复内容:", bg=CARD_BG, font=("Microsoft YaHei", 9, "bold")).pack(anchor='w')
        self.template_text = scrolledtext.ScrolledText(
            template_frame, height=5, font=("Microsoft YaHei", 9),
            wrap='word', relief='flat', bg='#fafafa'
        )
        self.template_text.pack(fill='x', pady=3)

        btn_row = tk.Frame(template_frame, bg=CARD_BG)
        btn_row.pack(fill='x', pady=(5, 0))
        ttk.Button(btn_row, text="💾 保存此模板", style='Success.TButton',
                   command=self._on_save_template).pack(side='left')
        ttk.Button(btn_row, text="📋 用此模板测试", style='Info.TButton',
                   command=self._on_test_template).pack(side='left', padx=8)

        # 测试结果
        test_frame = ttk.LabelFrame(parent, text=" 测试效果 ", style='Card.TLabelframe', padding=10)
        test_frame.pack(fill='both', expand=True, padx=10, pady=(5, 10))

        self.test_result_text = scrolledtext.ScrolledText(
            test_frame, height=6, font=("Microsoft YaHei", 9),
            wrap='word', relief='flat', bg='#fafafa'
        )
        self.test_result_text.pack(fill='both', expand=True)

    def _build_settings_tab(self, parent):
        """岗位设置Tab"""
        # 公司信息
        company_frame = ttk.LabelFrame(parent, text=" 公司信息 ", style='Card.TLabelframe', padding=10)
        company_frame.pack(fill='x', padx=10, pady=(10, 5))

        row1 = tk.Frame(company_frame, bg=CARD_BG)
        row1.pack(fill='x', pady=3)
        tk.Label(row1, text="公司名称:", width=10, bg=CARD_BG, font=("Microsoft YaHei", 9)).pack(side='left')
        self.company_name_var = tk.StringVar(value=COMPANY_INFO.get("name", ""))
        tk.Entry(row1, textvariable=self.company_name_var, font=("Microsoft YaHei", 9)).pack(side='left', fill='x', expand=True)

        row2 = tk.Frame(company_frame, bg=CARD_BG)
        row2.pack(fill='x', pady=3)
        tk.Label(row2, text="公司行业:", width=10, bg=CARD_BG, font=("Microsoft YaHei", 9)).pack(side='left')
        self.company_industry_var = tk.StringVar(value=COMPANY_INFO.get("industry", ""))
        tk.Entry(row2, textvariable=self.company_industry_var, font=("Microsoft YaHei", 9)).pack(side='left', fill='x', expand=True)

        # 岗位信息
        pos_frame = ttk.LabelFrame(parent, text=" 招聘岗位 ", style='Card.TLabelframe', padding=10)
        pos_frame.pack(fill='x', padx=10, pady=5)

        row3 = tk.Frame(pos_frame, bg=CARD_BG)
        row3.pack(fill='x', pady=3)
        tk.Label(row3, text="岗位名称:", width=10, bg=CARD_BG, font=("Microsoft YaHei", 9)).pack(side='left')
        self.position_name_var = tk.StringVar(value=DEFAULT_POSITION.get("name", ""))
        tk.Entry(row3, textvariable=self.position_name_var, font=("Microsoft YaHei", 9)).pack(side='left', fill='x', expand=True)

        row4 = tk.Frame(pos_frame, bg=CARD_BG)
        row4.pack(fill='x', pady=3)
        tk.Label(row4, text="所属部门:", width=10, bg=CARD_BG, font=("Microsoft YaHei", 9)).pack(side='left')
        self.position_dept_var = tk.StringVar(value=DEFAULT_POSITION.get("department", ""))
        tk.Entry(row4, textvariable=self.position_dept_var, font=("Microsoft YaHei", 9)).pack(side='left', fill='x', expand=True)

        # JD内容
        jd_frame = ttk.LabelFrame(parent, text=" 岗位JD ", style='Card.TLabelframe', padding=10)
        jd_frame.pack(fill='both', expand=True, padx=10, pady=5)

        self.jd_text = scrolledtext.ScrolledText(
            jd_frame, height=6, font=("Microsoft YaHei", 9),
            wrap='word', relief='flat', bg='#fafafa'
        )
        self.jd_text.pack(fill='both', expand=True)
        self.jd_text.insert('1.0', DEFAULT_POSITION.get("jd", ""))

        # 保存按钮
        btn_frame = tk.Frame(parent, bg=BG_COLOR)
        btn_frame.pack(fill='x', padx=10, pady=(5, 10))

        ttk.Button(btn_frame, text="💾 保存设置", style='Success.TButton',
                   command=self._on_save_settings).pack(side='right')

    def _build_candidates_tab(self, parent):
        """候选人Tab"""
        # 工具栏
        toolbar = tk.Frame(parent, bg=BG_COLOR)
        toolbar.pack(fill='x', padx=10, pady=(10, 5))

        ttk.Button(toolbar, text="🔄 刷新列表", style='Light.TButton',
                   command=self._refresh_candidates).pack(side='left')

        tk.Label(toolbar, text="  筛选:", bg=BG_COLOR, font=("Microsoft YaHei", 9)).pack(side='left')
        self.candidate_filter_var = tk.StringVar(value="全部")
        ttk.Combobox(toolbar, textvariable=self.candidate_filter_var, state='readonly',
                     values=["全部", "强烈推荐", "推荐", "待定", "不推荐"],
                     width=10).pack(side='left')

        # 候选人列表
        list_frame = ttk.LabelFrame(parent, text=" 候选人列表 ", style='Card.TLabelframe', padding=10)
        list_frame.pack(fill='both', expand=True, padx=10, pady=(5, 10))

        # Treeview
        columns = ("name", "position", "score", "level", "date")
        self.candidates_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=10)

        self.candidates_tree.heading("name", text="候选人")
        self.candidates_tree.heading("position", text="应聘岗位")
        self.candidates_tree.heading("score", text="评分")
        self.candidates_tree.heading("level", text="等级")
        self.candidates_tree.heading("date", text="日期")

        self.candidates_tree.column("name", width=120)
        self.candidates_tree.column("position", width=150)
        self.candidates_tree.column("score", width=60, anchor='center')
        self.candidates_tree.column("level", width=80, anchor='center')
        self.candidates_tree.column("date", width=100, anchor='center')

        self.candidates_tree.pack(fill='both', expand=True)

        # 候选人详情
        detail_frame = ttk.LabelFrame(parent, text=" 候选人详情 ", style='Card.TLabelframe', padding=10)
        detail_frame.pack(fill='both', expand=True, padx=10, pady=(0, 10))

        self.candidate_detail = scrolledtext.ScrolledText(
            detail_frame, height=6, font=("Microsoft YaHei", 9),
            wrap='word', relief='flat', bg='#fafafa'
        )
        self.candidate_detail.pack(fill='both', expand=True)

    # ================== 事件处理 ==================

    def _get_handler(self):
        """获取消息处理器（延迟初始化）"""
        if self.handler is None:
            self.handler = MessageHandler()
        return self.handler

    def _on_filter_resume(self):
        """筛选简历"""
        resume_text = self.resume_text.get('1.0', 'end').strip()
        if not resume_text:
            messagebox.showwarning("提示", "请先粘贴简历文本")
            return

        self.status_label.config(text="⏳ 筛选中...", fg="#bbdefb")

        def _do_filter():
            try:
                handler = self._get_handler()
                result = handler.process_candidate_resume(
                    candidate_id=f"manual_{int(__import__('time').time())}",
                    resume_text=resume_text,
                )
                self.root.after(0, lambda: self._show_filter_result(result))
            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda: self._show_filter_error(err_msg))

        threading.Thread(target=_do_filter, daemon=True).start()

    def _show_filter_result(self, result):
        """显示筛选结果"""
        filter_result = result.get("filter_result", {})
        score = filter_result.get("score", 0)
        level = filter_result.get("level", "")

        self.score_label.config(text=str(score))
        self.level_label.config(text=f"「{level}」")

        # 颜色
        if level == "强烈推荐":
            self.level_label.config(fg=SUCCESS)
            self.score_label.config(fg=SUCCESS)
        elif level == "推荐":
            self.level_label.config(fg=PRIMARY)
            self.score_label.config(fg=PRIMARY)
        elif level == "待定":
            self.level_label.config(fg=WARNING)
            self.score_label.config(fg=WARNING)
        else:
            self.level_label.config(fg=DANGER)
            self.score_label.config(fg=DANGER)

        # 详情
        self.result_text.delete('1.0', 'end')
        self.result_text.insert('end', f"总评: {filter_result.get('summary', '')}\n\n")

        matched = filter_result.get("matched_points", [])
        if matched:
            self.result_text.insert('end', "✅ 匹配点:\n")
            for p in matched:
                self.result_text.insert('end', f"  • {p}\n")
            self.result_text.insert('end', "\n")

        concerns = filter_result.get("concerns", [])
        if concerns:
            self.result_text.insert('end', "⚠️ 顾虑点:\n")
            for c in concerns:
                self.result_text.insert('end', f"  • {c}\n")
            self.result_text.insert('end', "\n")

        questions = filter_result.get("interview_questions", [])
        if questions:
            self.result_text.insert('end', "❓ 建议面试提问:\n")
            for q in questions:
                self.result_text.insert('end', f"  • {q}\n")

        reply_suggestion = filter_result.get("reply_suggestion", "")
        if reply_suggestion:
            self.result_text.insert('end', f"\n💬 回复建议: {reply_suggestion}")

        self.status_label.config(text="✅ 筛选完成", fg="#a5d6a7")

    def _show_filter_error(self, err_msg):
        """显示筛选错误"""
        self.status_label.config(text="❌ 筛选失败", fg="#ef9a9a")
        messagebox.showerror("错误", f"筛选失败: {err_msg}")

    def _on_clear_resume(self):
        """清空简历"""
        self.resume_text.delete('1.0', 'end')
        self.result_text.delete('1.0', 'end')
        self.score_label.config(text="--")
        self.level_label.config(text="")
        self.status_label.config(text="⏸ 就绪", fg="#bbdefb")

    def _on_template_scene_change(self):
        """切换模板场景时加载对应模板"""
        scene = self.template_scene_var.get()
        template = REPLY_TEMPLATES.get(scene, {})
        self.template_text.delete('1.0', 'end')
        self.template_text.insert('1.0', template.get("reply_text", ""))

    def _on_save_template(self):
        """保存当前模板"""
        global REPLY_TEMPLATES
        scene = self.template_scene_var.get()
        text = self.template_text.get('1.0', 'end').strip()

        if scene in REPLY_TEMPLATES:
            REPLY_TEMPLATES[scene]["reply_text"] = text
        else:
            REPLY_TEMPLATES[scene] = {
                "reply_text": text,
                "next_action": "继续沟通",
                "urgency": "中",
                "tags": ["自定义"],
            }

        # 更新handler里的模板
        if self.handler and self.handler._reply_generator:
            self.handler._reply_generator.update_template(scene, REPLY_TEMPLATES[scene])

        # 保存到设置文件
        self._settings["reply_templates"] = REPLY_TEMPLATES
        self._save_settings()

        messagebox.showinfo("成功", f"模板「{scene}」已保存！")
        self.status_label.config(text="✅ 模板已保存", fg="#a5d6a7")

    def _on_test_template(self):
        """用当前模板测试"""
        text = self.template_text.get('1.0', 'end').strip()
        self.test_result_text.delete('1.0', 'end')
        self.test_result_text.insert('end', "=== 预览效果 ===\n\n")
        self.test_result_text.insert('end', text)
        self.test_result_text.insert('end', f"\n\n---\n场景: {self.template_scene_var.get()}")
        self.test_result_text.insert('end', f"\n字数: {len(text)} 字")
        self.status_label.config(text="✅ 模板预览完成", fg="#a5d6a7")

    def _append_log(self, msg):
        """向日志框追加消息"""
        def _do():
            self.log_text.insert('end', msg + '\n')
            self.log_text.see('end')
        self.root.after(0, _do)

    def _update_status(self, text):
        """更新状态文字"""
        def _do():
            self.reply_status_var.set(text)
        self.root.after(0, _do)

    def _on_start_auto_reply(self):
        """启动自动回复"""
        self.start_reply_btn.config(state='disabled')
        self.stop_reply_btn.config(state='normal')
        self._append_log("🚀 正在启动自动回复...")
        self._update_status("正在启动...")

        def _run():
            try:
                # 初始化浏览器
                from browser import BrowserManager
                from hr_browser import HRBrowser

                self._append_log("🌐 正在启动浏览器...")
                self._update_status("启动浏览器中...")

                bm = BrowserManager()
                bm.init_browser()

                hr_browser = HRBrowser(bm)

                # 打开消息页面
                self._append_log("📄 打开BOSS直聘消息页面...")
                self._update_status("打开消息页面...")

                ok = hr_browser.open_chat_page()
                if not ok:
                    # 等待登录
                    self._append_log("⏳ 请在浏览器中扫码登录...")
                    self._update_status("等待扫码登录...")
                    logged_in = hr_browser.wait_for_login(timeout=120)
                    if not logged_in:
                        self._append_log("❌ 登录超时")
                        self._update_status("登录超时")
                        self._reset_buttons()
                        return

                self._append_log("✅ 登录成功，开始自动回复")
                self._update_status("运行中...")

                # 启动自动回复循环
                handler = self._get_handler()
                handler.start_auto_reply(
                    hr_browser,
                    status_callback=self._append_log,
                )

                self._update_status("已停止")
                self._append_log("🏁 自动回复已停止")

            except Exception as e:
                err_msg = str(e)
                self._append_log(f"❌ 错误: {err_msg}")
                self._update_status("出错了")
                logger.exception("自动回复异常")
            finally:
                self._reset_buttons()

        threading.Thread(target=_run, daemon=True).start()

    def _on_stop_auto_reply(self):
        """停止自动回复"""
        self._append_log("⏹  正在停止...")
        self._update_status("停止中...")
        handler = self._get_handler()
        handler.stop()
        self.stop_reply_btn.config(state='disabled')

    def _reset_buttons(self):
        """重置按钮状态"""
        def _do():
            self.start_reply_btn.config(state='normal')
            self.stop_reply_btn.config(state='disabled')
        self.root.after(0, _do)

    def _on_save_settings(self):
        """保存设置"""
        global COMPANY_INFO, DEFAULT_POSITION
        # 收集设置
        company_info = {
            "name": self.company_name_var.get(),
            "industry": self.company_industry_var.get(),
            "size": COMPANY_INFO.get("size", ""),
            "description": COMPANY_INFO.get("description", ""),
            "benefits": COMPANY_INFO.get("benefits", []),
        }

        position_config = {
            "name": self.position_name_var.get(),
            "department": self.position_dept_var.get(),
            "jd": self.jd_text.get('1.0', 'end').strip(),
            "requirements": DEFAULT_POSITION.get("requirements", {}),
        }

        # 更新全局配置
        COMPANY_INFO.update(company_info)
        DEFAULT_POSITION.update(position_config)

        # 更新handler
        if self.handler:
            self.handler.update_position(position_config)
            self.handler.update_company(company_info)

        # 保存到设置文件
        self._settings["company"] = company_info
        self._settings["position"] = position_config
        self._save_settings()

        messagebox.showinfo("成功", "设置已保存！")
        self.status_label.config(text="✅ 设置已保存", fg="#a5d6a7")

    def _refresh_candidates(self):
        """刷新候选人列表"""
        handler = self._get_handler()
        candidates = handler.get_all_candidates()

        # 清空列表
        for item in self.candidates_tree.get_children():
            self.candidates_tree.delete(item)

        # 按评分排序
        candidates_sorted = sorted(
            candidates,
            key=lambda c: c.get("last_filter", {}).get("score", 0),
            reverse=True
        )

        for c in candidates_sorted:
            info = c.get("info", {})
            name = info.get("name", "未知") or "未知"
            position = info.get("position", DEFAULT_POSITION.get("name", ""))
            score = c.get("last_filter", {}).get("score", 0)
            level = c.get("status", "")
            date = c.get("created_at", "")[:10]

            tags = ()
            if level == "强烈推荐":
                tags = ("strong",)
            elif level == "推荐":
                tags = ("good",)
            elif level == "待定":
                tags = ("pending",)
            else:
                tags = ("reject",)

            self.candidates_tree.insert('', 'end', values=(name, position, score, level, date), tags=tags)

        self.status_label.config(text=f"✅ 共 {len(candidates)} 位候选人", fg="#a5d6a7")

    def run(self):
        """运行GUI"""
        # 初始化模板文本
        self.root.after(50, self._on_template_scene_change)
        # 初始化候选人列表
        self.root.after(100, self._refresh_candidates)
        self.root.mainloop()


def main():
    app = HRHelperGUI()
    app.run()


if __name__ == "__main__":
    main()
