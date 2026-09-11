# BOSS直聘自动投递 - GUI 配置界面

import sys
import os
import json
import logging
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from config import (
    KEYWORDS, CITIES, MAX_DAILY_APPLIES,
    FILTER_CONFIG,
    APPLIED_FILE,
    CITY_OPTIONS, SCALE_OPTIONS,
)
from applier import JobApplier

SETTINGS_FILE = "data/gui_settings.json"

# 支持的投递平台（目前仅 BOSS 直聘已实现，其余为后续扩展位）
PLATFORM_OPTIONS = ["BOSS直聘", "前程无忧", "智联招聘", "猎聘", "拉勾", "实习僧"]

# 各平台介绍（平台, 实习, 校招, 社招, 面向人群/特点）—— ✅ 覆盖, — 基本不覆盖
PLATFORM_INFO = [
    ("BOSS直聘",   "✅", "✅", "✅", "全行业覆盖最广，直接聊 HR；主力平台"),
    ("前程无忧",   "—",  "✅", "✅", "传统行业 / 制造业 / 职能岗"),
    ("智联招聘",   "—",  "✅", "✅", "国企、央企、大型企业多"),
    ("猎聘",       "—",  "—",  "✅", "中高端、资深、管理岗，猎头活跃"),
    ("拉勾",       "—",  "—",  "✅", "互联网垂直（技术 / 产品 / 运营）"),
    ("实习僧",     "✅", "✅", "—",  "专注实习 + 校招，在校生首选"),
]

DEFAULTS = {
    "platform": "BOSS直聘",
    "keywords": ", ".join(KEYWORDS[:3]),
    "city": CITIES[0] if CITIES else "北京",
    "count": str(MAX_DAILY_APPLIES),
    "speed": "1",
    "exclude": ", ".join(FILTER_CONFIG.get("exclude_keywords", ["销售", "外包", "电话销售", "客服", "电销", "推广", "中介", "华为", "算法", "剧", "infra", "字节"])),
    "intern": True,
    "login": True,
    "schedule": False,
    "schedule_hour": "09",
    "schedule_minute": "00",
    "scales": ["305", "306"],
    "agent_filter": False,
    "rag_enabled": True,
}


def get_today_count():
    if not os.path.exists(APPLIED_FILE):
        return 0
    try:
        with open(APPLIED_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            today = datetime.now().strftime("%Y-%m-%d")
            return sum(1 for j in data.get("jobs", []) if j.get("date") == today)
    except Exception:
        return 0


def reset_today_count():
    if not os.path.exists(APPLIED_FILE):
        return True
    try:
        with open(APPLIED_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        today = datetime.now().strftime("%Y-%m-%d")
        data["jobs"] = [j for j in data.get("jobs", []) if j.get("date") != today]
        with open(APPLIED_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


class ConfigGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("自动投递")
        self.root.geometry("560x700")
        self.root.resizable(False, False)

        root.eval('tk::PlaceWindow . center')

        style = ttk.Style()
        style.theme_use('clam')

        PRIMARY = '#1a73e8'
        SUCCESS = '#43a047'
        WARNING = '#ff9800'
        DANGER = '#e53935'
        LIGHT = '#f8f9fa'
        BORDER = '#e0e0e0'
        TEXT = '#333333'
        TEXT_LIGHT = '#666666'

        style.configure('TFrame', background=LIGHT)
        style.configure('TLabel', background=LIGHT, foreground=TEXT, font=('Microsoft YaHei', 8))
        style.configure('Card.TFrame', background='white')
        style.layout('Card.TLabelframe', style.layout('TLabelframe'))
        style.configure('Card.TLabelframe', background='white', bordercolor=BORDER,
                        relief='solid', font=('Microsoft YaHei', 9, 'bold'), foreground=TEXT)
        style.configure('Primary.TButton', background=PRIMARY, foreground='white',
                        font=('Microsoft YaHei', 9), padding=(10, 3))
        style.map('Primary.TButton', background=[('active', '#1557b0')])
        style.configure('Success.TButton', background=SUCCESS, foreground='white',
                        font=('Microsoft YaHei', 8), padding=(8, 3))
        style.configure('Warning.TButton', background=WARNING, foreground='white',
                        font=('Microsoft YaHei', 8), padding=(8, 3))
        style.configure('Danger.TButton', background=DANGER, foreground='white',
                        font=('Microsoft YaHei', 8), padding=(8, 3))
        style.configure('Info.TButton', background='#546e7a', foreground='white',
                        font=('Microsoft YaHei', 8), padding=(8, 3))
        style.configure('Light.TButton', background='#e0e0e0', foreground=TEXT,
                        font=('Microsoft YaHei', 8), padding=(8, 3))
        style.configure('TEntry', font=('Microsoft YaHei', 8), padding=(6, 3))
        style.configure('TCombobox', font=('Microsoft YaHei', 8))
        style.configure('TCheckbutton', font=('Microsoft YaHei', 8))
        style.configure('Title.TLabel', font=('Microsoft YaHei', 13, 'bold'),
                        foreground=PRIMARY, background=LIGHT)
        style.configure('Subtitle.TLabel', font=('Microsoft YaHei', 8),
                        foreground=TEXT_LIGHT, background=LIGHT)
        style.configure('Status.TLabel', font=('Microsoft YaHei', 7),
                        foreground=TEXT_LIGHT, background=LIGHT)

        self.root.configure(bg=LIGHT)

        header = ttk.Frame(root)
        header.pack(fill='x', padx=12, pady=(8, 4))

        btn_group = ttk.Frame(header)
        btn_group.pack(side='right')

        save_btn = ttk.Button(btn_group, text="保存", command=self.save_settings, style='Success.TButton')
        save_btn.pack(side='left', padx=(0, 4))
        restore_btn = ttk.Button(btn_group, text="重置", command=self.restore_defaults, style='Light.TButton')
        restore_btn.pack(side='left')

        LBL = ('Microsoft YaHei', 8, 'bold')
        P = 3  # 行间距

        # ====== 主卡片：只留常用的三项 ======
        self.card_frame = ttk.LabelFrame(root, text="快速投递", style='Card.TLabelframe')
        self.card_frame.pack(fill='x', padx=12, pady=(0, 4))
        self.card_frame.configure(padding=7)

        # 行1：投递平台 | 岗位关键词
        ttk.Label(self.card_frame, text="投递平台", font=LBL).grid(row=0, column=0, sticky='w', pady=P)
        self.platform_var = tk.StringVar(value=DEFAULTS["platform"])
        ttk.Combobox(self.card_frame, textvariable=self.platform_var, values=PLATFORM_OPTIONS,
                     state='readonly', width=12).grid(row=0, column=1, sticky='w', pady=P)
        ttk.Label(self.card_frame, text="岗位关键词", font=LBL).grid(row=0, column=2, sticky='w', padx=(10, 6), pady=P)
        self.kw_var = tk.StringVar(value=DEFAULTS["keywords"])
        ttk.Entry(self.card_frame, textvariable=self.kw_var).grid(row=0, column=3, sticky='ew', pady=P)

        # 行2：城市 | 更多设置按钮
        ttk.Label(self.card_frame, text="城市", font=LBL).grid(row=1, column=0, sticky='w', pady=P)
        self.city_var = tk.StringVar(value=DEFAULTS["city"])
        city_names = list(CITY_OPTIONS.keys())
        ttk.Combobox(self.card_frame, textvariable=self.city_var, values=city_names,
                     state='readonly', width=12).grid(row=1, column=1, sticky='w', pady=P)
        btns_frame = ttk.Frame(self.card_frame)
        btns_frame.grid(row=1, column=3, sticky='e', pady=P)
        ttk.Button(btns_frame, text="ⓘ 平台介绍", command=self.open_platform_info,
                   style='Light.TButton').pack(side='left', padx=(0, 4))
        self.more_toggle_btn = ttk.Button(btns_frame, text="更多设置 ▾",
                                          command=self.toggle_more, style='Light.TButton')
        self.more_toggle_btn.pack(side='left')

        self.card_frame.columnconfigure(3, weight=1)

        # ====== 折叠区（默认隐藏，点「更多设置」展开）======
        self.more_container = ttk.Frame(root)
        self._more_open = False

        more_card = ttk.LabelFrame(self.more_container, text="更多设置", style='Card.TLabelframe')
        more_card.pack(fill='x', padx=12, pady=(0, 4))
        more_card.configure(padding=7)

        # 投递数量
        ttk.Label(more_card, text="投递数量", font=LBL).grid(row=0, column=0, sticky='w', pady=P)
        count_frame = ttk.Frame(more_card)
        count_frame.grid(row=0, column=1, columnspan=3, sticky='w', pady=P)
        self.count_var = tk.StringVar(value=DEFAULTS["count"])
        for c in ["20", "40", "60", "100", "130"]:
            ttk.Radiobutton(count_frame, text=c, variable=self.count_var, value=c).pack(side='left', padx=(0, 3))

        # 公司规模
        ttk.Label(more_card, text="公司规模", font=LBL).grid(row=1, column=0, sticky='w', pady=P)
        scale_frame = ttk.Frame(more_card)
        scale_frame.grid(row=1, column=1, columnspan=3, sticky='w', pady=P)
        self.scale_vars = {}
        default_scales = DEFAULTS.get("scales", ["305", "306"])
        for scale_name, scale_code in SCALE_OPTIONS.items():
            var = tk.BooleanVar(value=(scale_code in default_scales))
            self.scale_vars[scale_code] = var
            ttk.Checkbutton(scale_frame, text=scale_name, variable=var).pack(side='left', padx=(0, 10))

        # 排除关键词
        ttk.Label(more_card, text="排除关键词", font=LBL).grid(row=2, column=0, sticky='w', pady=P)
        self.exclude_var = tk.StringVar(value=DEFAULTS["exclude"])
        ttk.Entry(more_card, textvariable=self.exclude_var).grid(
            row=2, column=1, columnspan=3, sticky='ew', pady=P)

        # 操作速度 | 定时投递
        ttk.Label(more_card, text="操作速度", font=LBL).grid(row=3, column=0, sticky='w', pady=P)
        speed_frame = ttk.Frame(more_card)
        speed_frame.grid(row=3, column=1, sticky='w', pady=P)
        self.speed_var = tk.StringVar(value=DEFAULTS["speed"])
        for text, val in [("快", "1"), ("正常", "2"), ("慢", "3")]:
            ttk.Radiobutton(speed_frame, text=text, variable=self.speed_var, value=val).pack(side='left', padx=(0, 8))

        ttk.Label(more_card, text="定时投递", font=LBL).grid(row=3, column=2, sticky='w', padx=(10, 6), pady=P)
        sched_frame = ttk.Frame(more_card)
        sched_frame.grid(row=3, column=3, sticky='w', pady=P)
        self.schedule_var = tk.BooleanVar(value=DEFAULTS["schedule"])
        ttk.Checkbutton(sched_frame, text="", variable=self.schedule_var,
                        command=self._toggle_schedule).pack(side='left')
        self.schedule_hour = tk.StringVar(value=DEFAULTS["schedule_hour"])
        self.schedule_minute = tk.StringVar(value=DEFAULTS["schedule_minute"])
        self.hour_spin = ttk.Spinbox(sched_frame, from_=0, to=23, width=3,
                                     textvariable=self.schedule_hour, format="%02.0f", state='disabled')
        self.hour_spin.pack(side='left', padx=(0, 1))
        ttk.Label(sched_frame, text=":").pack(side='left')
        self.minute_spin = ttk.Spinbox(sched_frame, from_=0, to=59, width=3,
                                       textvariable=self.schedule_minute, format="%02.0f", state='disabled')
        self.minute_spin.pack(side='left', padx=(1, 0))

        # 勾选项
        cb_frame = ttk.Frame(more_card)
        cb_frame.grid(row=4, column=0, columnspan=4, sticky='w', pady=(P, 0))
        self.intern_var = tk.BooleanVar(value=DEFAULTS["intern"])
        ttk.Checkbutton(cb_frame, text="只投实习", variable=self.intern_var).pack(side='left', padx=(0, 12))
        self.login_var = tk.BooleanVar(value=DEFAULTS["login"])
        ttk.Checkbutton(cb_frame, text="已登录", variable=self.login_var).pack(side='left', padx=(0, 12))
        self.rag_var = tk.BooleanVar(value=DEFAULTS["rag_enabled"])
        ttk.Checkbutton(cb_frame, text="RAG召回", variable=self.rag_var).pack(side='left', padx=(0, 12))
        self.agent_var = tk.BooleanVar(value=DEFAULTS["agent_filter"])
        ttk.Checkbutton(cb_frame, text="Agent筛选", variable=self.agent_var).pack(side='left')

        more_card.columnconfigure(1, weight=1)
        more_card.columnconfigure(3, weight=1)

        action_frame = ttk.LabelFrame(root, text="操作", style='Card.TLabelframe')
        action_frame.pack(fill='x', padx=12, pady=(0, 4))
        action_frame.configure(padding=5)

        left_frame = ttk.Frame(action_frame)
        left_frame.pack(side='left')
        ttk.Label(left_frame, text="今日已投:", font=('Microsoft YaHei', 8)).pack(side='left')
        self.today_count_var = tk.StringVar(value=str(get_today_count()))
        ttk.Label(left_frame, textvariable=self.today_count_var,
                  font=('Microsoft YaHei', 10, 'bold'), foreground=DANGER).pack(side='left', padx=(3, 10))
        ttk.Button(left_frame, text="重置计数", command=self.reset_count, style='Warning.TButton').pack(side='left')

        right_frame = ttk.Frame(action_frame)
        right_frame.pack(side='right')
        self.start_btn = ttk.Button(right_frame, text="开始投递", command=self.start_apply,
                                    style='Primary.TButton', width=10)
        self.start_btn.pack(side='left')
        self.stop_btn = ttk.Button(right_frame, text="终止", command=self.stop_apply,
                                   style='Danger.TButton', width=6, state='disabled')
        self.stop_btn.pack(side='left', padx=(6, 0))

        flywheel_frame = ttk.LabelFrame(self.more_container, text="飞轮", style='Card.TLabelframe')
        flywheel_frame.pack(fill='x', padx=12, pady=(0, 4))
        flywheel_frame.configure(padding=5)

        self.flywheel_var = tk.StringVar(value="加载中...")
        ttk.Label(flywheel_frame, textvariable=self.flywheel_var, style='Status.TLabel').pack(anchor='w', pady=(0, 4))

        btn_row = ttk.Frame(flywheel_frame)
        btn_row.pack(fill='x')
        ttk.Button(btn_row, text="标注", command=self.open_label_window,
                   style='Success.TButton').pack(side='left', padx=(0, 4))
        ttk.Button(btn_row, text="挖掘规则", command=self.open_suggest_window,
                   style='Warning.TButton').pack(side='left', padx=(0, 4))
        ttk.Button(btn_row, text="趋势", command=self.open_trend_window,
                   style='Info.TButton').pack(side='left', padx=(0, 4))
        ttk.Button(btn_row, text="刷新", command=self.refresh_flywheel_status,
                   style='Light.TButton').pack(side='left')

        # ====== 智能简历区 ======
        resume_frame = ttk.LabelFrame(self.more_container, text="智能简历", style='Card.TLabelframe')
        resume_frame.pack(fill='x', padx=12, pady=(0, 4))
        resume_frame.configure(padding=5)

        ttk.Button(resume_frame, text="打开智能简历助手（上传简历 → 匹配JD → 生成打招呼语）",
                   command=self.open_resume_window, style='Primary.TButton').pack(side='left')

        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(root, textvariable=self.status_var, style='Status.TLabel')
        status_bar.pack(fill='x', padx=12, pady=(0, 5), anchor='e')

        self.load_settings()
        self.refresh_flywheel_status()
        self._fit_window()

    def _fit_window(self):
        """按内容自适应窗口尺寸（折叠/展开后调用）"""
        try:
            self.root.update_idletasks()
            self.root.geometry(f"{self.root.winfo_reqwidth()}x{self.root.winfo_reqheight()}")
        except Exception:
            pass

    def toggle_more(self):
        """展开 / 收起「更多设置」折叠区"""
        if self._more_open:
            self.more_container.pack_forget()
            self.more_toggle_btn.config(text="更多设置 ▾")
            self._more_open = False
        else:
            self.more_container.pack(fill='x', after=self.card_frame)
            self.more_toggle_btn.config(text="收起设置 ▴")
            self._more_open = True
        self._fit_window()

    def open_platform_info(self):
        """弹出「各招聘平台介绍」面板（实习 / 校招 / 社招 一目了然）"""
        top = tk.Toplevel(self.root)
        top.title("各招聘平台介绍")
        top.transient(self.root)
        top.resizable(False, False)

        ttk.Label(top,
                  text="按你的求职类型选平台：实习 → 实习僧 / BOSS；校招 → BOSS、智联、前程无忧；社招 → 基本都适用",
                  style='Subtitle.TLabel', wraplength=520, justify='left').pack(
            fill='x', padx=12, pady=(10, 6))

        cols = ("platform", "intern", "campus", "social", "desc")
        tree = ttk.Treeview(top, columns=cols, show='headings', height=len(PLATFORM_INFO))
        for cid, text, w, anchor in [
            ("platform", "平台", 96, 'w'),
            ("intern", "实习", 46, 'center'),
            ("campus", "校招", 46, 'center'),
            ("social", "社招", 46, 'center'),
            ("desc", "面向人群 / 特点", 320, 'w'),
        ]:
            tree.heading(cid, text=text)
            tree.column(cid, width=w, anchor=anchor)
        for row in PLATFORM_INFO:
            tree.insert("", 'end', values=row)
        tree.pack(fill='both', expand=True, padx=12, pady=(0, 8))

        ttk.Button(top, text="关闭", command=top.destroy,
                   style='Light.TButton').pack(pady=(0, 10))

        # 位置居中（相对主窗）
        top.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - top.winfo_width()) // 2
        y = self.root.winfo_rooty() + 60
        top.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _toggle_schedule(self):
        state = 'normal' if self.schedule_var.get() else 'disabled'
        self.hour_spin.config(state=state)
        self.minute_spin.config(state=state)

    def save_settings(self):
        cfg = {
            "platform": self.platform_var.get(),
            "keywords": self.kw_var.get(),
            "city": self.city_var.get(),
            "count": self.count_var.get(),
            "speed": self.speed_var.get(),
            "exclude": self.exclude_var.get(),
            "intern": self.intern_var.get(),
            "login": self.login_var.get(),
            "schedule": self.schedule_var.get(),
            "schedule_hour": self.schedule_hour.get(),
            "schedule_minute": self.schedule_minute.get(),
            "scales": [code for code, var in self.scale_vars.items() if var.get()],
            "agent_filter": self.agent_var.get(),
            "rag_enabled": self.rag_var.get(),
        }
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE) or '.', exist_ok=True)
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            self.status_var.set("✅ 设置已保存")
            messagebox.showinfo("成功", "设置已保存！")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败:\n{e}")

    def load_settings(self):
        if not os.path.exists(SETTINGS_FILE):
            return
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            self.platform_var.set(cfg.get("platform", DEFAULTS["platform"]))
            self.kw_var.set(cfg.get("keywords", DEFAULTS["keywords"]))
            self.city_var.set(cfg.get("city", DEFAULTS["city"]))
            self.count_var.set(cfg.get("count", DEFAULTS["count"]))
            self.speed_var.set(cfg.get("speed", DEFAULTS["speed"]))
            self.exclude_var.set(cfg.get("exclude", DEFAULTS["exclude"]))
            self.intern_var.set(cfg.get("intern", DEFAULTS["intern"]))
            self.login_var.set(cfg.get("login", DEFAULTS["login"]))
            self.schedule_var.set(cfg.get("schedule", DEFAULTS["schedule"]))
            self.schedule_hour.set(cfg.get("schedule_hour", DEFAULTS["schedule_hour"]))
            self.schedule_minute.set(cfg.get("schedule_minute", DEFAULTS["schedule_minute"]))
            self.agent_var.set(cfg.get("agent_filter", DEFAULTS["agent_filter"]))
            self.rag_var.set(cfg.get("rag_enabled", DEFAULTS["rag_enabled"]))
            saved_scales = cfg.get("scales", DEFAULTS["scales"])
            for scale_code, var in self.scale_vars.items():
                var.set(scale_code in saved_scales)
            self._toggle_schedule()
            self.status_var.set("✅ 已加载上次保存的设置")
        except Exception as e:
            self.status_var.set(f"⚠ 加载设置失败: {e}")

    def restore_defaults(self):
        if not messagebox.askyesno("确认", "确定恢复所有设置为默认值？"):
            return
        self.platform_var.set(DEFAULTS["platform"])
        self.kw_var.set(DEFAULTS["keywords"])
        self.city_var.set(DEFAULTS["city"])
        self.count_var.set(DEFAULTS["count"])
        self.speed_var.set(DEFAULTS["speed"])
        self.exclude_var.set(DEFAULTS["exclude"])
        self.intern_var.set(DEFAULTS["intern"])
        self.login_var.set(DEFAULTS["login"])
        self.schedule_var.set(DEFAULTS["schedule"])
        self.schedule_hour.set(DEFAULTS["schedule_hour"])
        self.schedule_minute.set(DEFAULTS["schedule_minute"])
        self.agent_var.set(DEFAULTS["agent_filter"])
        self.rag_var.set(DEFAULTS["rag_enabled"])
        for scale_code, var in self.scale_vars.items():
            var.set(scale_code in DEFAULTS.get("scales", []))
        self._toggle_schedule()
        if os.path.exists(SETTINGS_FILE):
            os.remove(SETTINGS_FILE)
        self.status_var.set("↩ 已恢复为默认设置")
        messagebox.showinfo("完成", "已恢复为默认设置")

    def reset_count(self):
        count = get_today_count()
        if count == 0:
            messagebox.showinfo("提示", "当前没有今日记录")
            return
        if messagebox.askyesno("确认", f"确定清除今日已投的 {count} 条记录？"):
            if reset_today_count():
                self.today_count_var.set("0")
                self.status_var.set("已重置")
                messagebox.showinfo("成功", "今日计数已重置")
            else:
                messagebox.showerror("错误", "重置失败")

    def _get_config(self):
        keywords = [k.strip() for k in self.kw_var.get().replace("，", ",").split(",") if k.strip()]
        if not keywords:
            keywords = KEYWORDS.copy()
        max_applies = self.count_var.get()
        if not max_applies.isdigit():
            max_applies = MAX_DAILY_APPLIES
        else:
            max_applies = int(max_applies)
        speed = self.speed_var.get()
        delay_map = {"1": (1, 2), "2": (3, 6), "3": (5, 10)}
        delay_range = delay_map.get(speed, (1, 2))
        exclude = [e.strip() for e in self.exclude_var.get().replace("，", ",").split(",") if e.strip()]
        return {
            "keywords": keywords,
            "cities": [self.city_var.get()],
            "city_code": CITY_OPTIONS.get(self.city_var.get(), CITY_OPTIONS[CITIES[0]]),
            "max_daily_applies": max_applies,
            "test_limit": None,
            "delay_range": delay_range,
            "internship_only": self.intern_var.get(),
            "exclude_keywords": exclude,
            "skip_login": self.login_var.get(),
            "schedule_enabled": self.schedule_var.get(),
            "schedule_hour": int(self.schedule_hour.get()) if self.schedule_hour.get().isdigit() else 9,
            "schedule_minute": int(self.schedule_minute.get()) if self.schedule_minute.get().isdigit() else 0,
            "scales": [code for code, var in self.scale_vars.items() if var.get()],
            "agent_filter": self.agent_var.get(),
            "rag_enabled": self.rag_var.get(),
        }

    def start_apply(self):
        cfg = self._get_config()
        schedule_str = ""
        if cfg["schedule_enabled"]:
            h = cfg["schedule_hour"]
            m = cfg["schedule_minute"]
            schedule_str = f"\n定时: {h:02d}:{m:02d}"
        scale_names = [name for name, code in SCALE_OPTIONS.items() if code in cfg["scales"]]
        scale_str = ", ".join(scale_names) if scale_names else "不限"
        rag_str = "启用" if cfg.get("rag_enabled") else "关闭"
        msg = f"""确认开始投递？

关键词: {', '.join(cfg['keywords'][:5])}
城市:   {cfg['cities'][0]}
数量:   {cfg['max_daily_applies']} 个
规模:   {scale_str}
间隔:   {cfg['delay_range'][0]}-{cfg['delay_range'][1]}秒
实习:   {'是' if cfg['internship_only'] else '否'}
登录:   {'已登录' if cfg['skip_login'] else '需扫码'}
RAG召回: {rag_str}
{schedule_str}"""
        if not messagebox.askyesno("确认", msg):
            return
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.applier = JobApplier()
        # 把 RAG 配置透传给 applier
        if cfg.get("rag_enabled") is not None:
            self.applier.rag_enabled = cfg["rag_enabled"]
        from threading import Thread
        Thread(target=self._run_apply, args=(cfg,), daemon=True).start()

    def _run_apply(self, cfg):
        try:
            # 把 GUI 配置同步到 applier 实例属性
            a = self.applier
            a.keywords = cfg["keywords"]
            a.city_code = cfg["city_code"]
            a.max_daily_applies = cfg["max_daily_applies"]
            a.delay_range = cfg["delay_range"]
            a.internship_only = cfg["internship_only"]
            a.exclude_keywords = cfg["exclude_keywords"]
            a.skip_login = cfg["skip_login"]
            a.scale_codes = cfg["scales"]
            a.agent_filter_enabled = cfg["agent_filter"]
            a.rag_enabled = cfg.get("rag_enabled", False)

            a.run()
            final_count = get_today_count()
            self.status_var.set(f"完成！本次投递 {self.applier.today_count} 个，今日累计 {final_count} 个")
        except Exception as e:
            self.status_var.set(f"错误: {e}")
        finally:
            self.root.after(0, lambda: self.start_btn.config(state='normal'))
            self.root.after(0, lambda: self.stop_btn.config(state='disabled'))

    def stop_apply(self):
        if hasattr(self, 'applier'):
            self.applier.stop_requested = True
            self.status_var.set("🛑 终止信号已发送")

    def open_label_window(self):
        from flywheel.label_ui import LabelWindow
        LabelWindow(self.root)

    def open_suggest_window(self):
        from flywheel.suggest_ui import SuggestWindow
        SuggestWindow(self.root)

    def open_trend_window(self):
        from flywheel.trend_ui import TrendWindow
        TrendWindow(self.root)

    def open_resume_window(self):
        from resume.resume_ui import ResumeWindow
        ResumeWindow(self.root)

    def refresh_flywheel_status(self):
        try:
            from flywheel import metrics
            m = metrics.compute_metrics()
            total = m.get("total_labeled", 0)
            if total == 0:
                self.flywheel_var.set("标注: 0 条 | 开始标注启动飞轮")
            else:
                g1, g2, g3, g4 = m.get("G1", 0), m.get("G2", 0), m.get("G3", 0), m.get("G4", 0)
                oa = m.get("overall_accuracy")
                oa_pct = f"{oa*100:.0f}%" if oa else "N/A"
                # Holt 预测下一轮
                pred = metrics.predict_overall_accuracy()
                pred_str = f" | 预测:{pred*100:.0f}%" if pred is not None else ""
                self.flywheel_var.set(f"标注:{total}条 G1:{g1} G2:{g2} G3:{g3} G4:{g4} 综合:{oa_pct}{pred_str}")
        except Exception as e:
            self.flywheel_var.set(f"加载失败: {e}")


def _ensure_embedding_dependency(parent=None):
    """首次运行快速自检：已安装则毫秒级跳过；缺依赖仅首次询问，选“否”后不再打扰"""
    import importlib.util

    # 1) 已安装 → 立即跳过（不询问、不安装）
    try:
        if importlib.util.find_spec("sentence_transformers") is not None:
            return
    except Exception:
        return

    # 2) 未安装 → 询问用户（每次运行都会问，直到装上为止）
    try:
        ok = messagebox.askyesno(
            "缺少语义过滤依赖",
            "检测到未安装 sentence-transformers（约 1.5GB）。\n\n"
            "是否现在用【清华镜像】自动安装？\n\n"
            "选「否」将跳过：程序仍可正常投递，只是不启用语义过滤（对海投影响很小）。",
            parent=parent,
        )
    except Exception:
        ok = False

    if not ok:
        print("\n[依赖] 已跳过 sentence-transformers 安装，语义过滤关闭（不影响投递）。\n", flush=True)
        return

    # 使用国内镜像（清华）安装，并实时转发 pip 输出（含下载进度）
    import subprocess
    mirror = "https://pypi.tuna.tsinghua.edu.cn/simple"
    print("\n" + "=" * 60, flush=True)
    print("[依赖] 开始安装 sentence-transformers（清华镜像，约 1.5GB，请耐心等待）...", flush=True)
    print("=" * 60, flush=True)

    returncode = -1
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "pip", "install", "-i", mirror,
             "--progress-bar", "on", "sentence-transformers"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="ignore", bufsize=1,
        )
        for line in proc.stdout:
            print(line.rstrip(), flush=True)   # 逐行显示 pip 进度
        proc.wait()
        returncode = proc.returncode
    except Exception as e:
        print(f"[依赖] 安装异常: {e}", flush=True)

    if returncode == 0:
        try:
            messagebox.showinfo("安装完成", "sentence-transformers 安装成功，已启用语义过滤。", parent=parent)
        except Exception:
            pass
        print("[依赖] sentence-transformers 安装成功，已启用语义过滤。\n", flush=True)
    else:
        try:
            messagebox.showwarning(
                "安装未完成",
                "安装未成功，程序将以「语义过滤关闭」模式运行（不影响投递）。",
                parent=parent,
            )
        except Exception:
            pass
        print("[依赖] 安装未成功，语义过滤保持关闭（不影响投递）。\n", flush=True)


def main():
    root = tk.Tk()
    root.withdraw()                       # 先隐藏主窗口，用于首次依赖询问
    _ensure_embedding_dependency(root)    # 首次运行：缺依赖则询问并自动安装
    root.deiconify()                      # 再显示主界面
    app = ConfigGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()