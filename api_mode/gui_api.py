# BOSS 直聘自动投递 —— API 模式 GUI 入口（新建，不修改旧 gui.py）
#
# 与旧 gui.py 布局/样式一致，但后端指向 api_mode 管线：
#   - 复用 flywheel 的标注/挖掘/趋势窗口（LabelWindow / SuggestWindow / TrendWindow）
#   - 新增：并发线程数、限速说明、token 环境变量名、离线 Mock 验证开关
#   - 入口在 GUI，沿用相同「搜索→过滤→投递→标注→飞轮」流程
#
# 合规提示：仅供本人学习/求职用途，遵守平台协议与相关法律法规。

import sys
import os
import json
import logging
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# ====== 引导：让 boss_auto_apply 可被按包导入，且 data/ 指向共享目录 ======
_HERE = os.path.dirname(os.path.abspath(__file__))
_BOSS_AA = os.path.join(os.path.dirname(_HERE), "boss_auto_apply")
if _BOSS_AA not in sys.path:
    sys.path.insert(0, _BOSS_AA)
try:
    os.chdir(_BOSS_AA)
except Exception:
    pass

from config import (
    KEYWORDS, CITIES, MAX_DAILY_APPLIES, FILTER_CONFIG,
    CITY_OPTIONS, SCALE_OPTIONS,
)
import config_api
import dedup
import pipeline

SETTINGS_FILE = "data/gui_api_settings.json"

DEFAULTS = {
    "keywords": ", ".join(KEYWORDS[:3]),
    "city": CITIES[0] if CITIES else "北京",
    "count": str(MAX_DAILY_APPLIES),
    "exclude": ", ".join(FILTER_CONFIG.get("exclude_keywords",
                        ["销售", "外包", "电话销售", "客服", "电销", "推广", "中介", "华为", "算法", "剧", "infra", "字节"])),
    "intern": True,
    "login": True,
    "fetch_workers": str(config_api.API_CONFIG["fetch_workers"]),
    "rag_enabled": True,
    "agent_filter": False,
    "mock": True,  # 默认离线 Mock 验证，避免无 token 时报错
    "e2e_token": "",
    "e2mf_token": "",
    "base_url": "",
}


def get_today_count():
    try:
        return dedup.DedupStore(config_api.API_CONFIG["dedup_db"]).today_count()
    except Exception:
        return 0


class ApiConfigGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("自动投递 (API 模式)")
        self.root.geometry("560x840")
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
        header.pack(fill='x', padx=15, pady=(10, 5))
        ttk.Label(header, text="BOSS 直聘自动投递 · API 模式", style='Title.TLabel').pack(side='left')
        btn_group = ttk.Frame(header)
        btn_group.pack(side='right')
        ttk.Button(btn_group, text="保存", command=self.save_settings, style='Success.TButton').pack(side='left', padx=(0, 4))
        ttk.Button(btn_group, text="重置", command=self.restore_defaults, style='Light.TButton').pack(side='left')

        # 投递设置
        card = ttk.LabelFrame(root, text="投递设置", style='Card.TLabelframe')
        card.pack(fill='x', padx=15, pady=(0, 8))
        card.configure(padding=10)
        row = 0
        ttk.Label(card, text="搜索关键词", font=('Microsoft YaHei', 8, 'bold')).grid(row=row, column=0, sticky='w', pady=(0, 2), columnspan=2)
        self.kw_var = tk.StringVar(value=DEFAULTS["keywords"])
        ttk.Entry(card, textvariable=self.kw_var).grid(row=row + 1, column=0, columnspan=2, sticky='ew', pady=(0, 6))

        row += 2
        ttk.Label(card, text="城市", font=('Microsoft YaHei', 8, 'bold')).grid(row=row, column=0, sticky='w', pady=(0, 2))
        ttk.Label(card, text="投递数量", font=('Microsoft YaHei', 8, 'bold')).grid(row=row, column=1, sticky='w', pady=(0, 2))
        city_frame = ttk.Frame(card)
        city_frame.grid(row=row + 1, column=0, sticky='w', pady=(0, 6))
        self.city_var = tk.StringVar(value=DEFAULTS["city"])
        ttk.Combobox(city_frame, textvariable=self.city_var, values=list(CITY_OPTIONS.keys()), state='readonly', width=10).pack(side='left')
        count_frame = ttk.Frame(card)
        count_frame.grid(row=row + 1, column=1, sticky='w', pady=(0, 6))
        self.count_var = tk.StringVar(value=DEFAULTS["count"])
        for c in ["20", "40", "60", "100", "130"]:
            ttk.Radiobutton(count_frame, text=c, variable=self.count_var, value=c).pack(side='left', padx=(0, 4))

        row += 2
        ttk.Label(card, text="排除关键词", font=('Microsoft YaHei', 8, 'bold')).grid(row=row, column=0, sticky='w', pady=(0, 2), columnspan=2)
        self.exclude_var = tk.StringVar(value=DEFAULTS["exclude"])
        ttk.Entry(card, textvariable=self.exclude_var).grid(row=row + 1, column=0, columnspan=2, sticky='ew', pady=(0, 6))

        row += 2
        ttk.Label(card, text="并发线程数 (FETCH 并行度)", font=('Microsoft YaHei', 8, 'bold')).grid(row=row, column=0, sticky='w', pady=(0, 2), columnspan=2)
        self.workers_var = tk.StringVar(value=DEFAULTS["fetch_workers"])
        ttk.Combobox(card, textvariable=self.workers_var, values=["2", "4", "6", "8"], state='readonly', width=8).grid(row=row + 1, column=0, sticky='w', pady=(0, 6))

        row += 2
        cb_frame = ttk.Frame(card)
        cb_frame.grid(row=row, column=0, sticky='w', pady=(0, 2), columnspan=2)
        self.intern_var = tk.BooleanVar(value=DEFAULTS["intern"])
        ttk.Checkbutton(cb_frame, text="只投实习", variable=self.intern_var).pack(side='left', padx=(0, 20))
        self.login_var = tk.BooleanVar(value=DEFAULTS["login"])
        ttk.Checkbutton(cb_frame, text="已登录", variable=self.login_var).pack(side='left')
        row += 1
        cb_frame2 = ttk.Frame(card)
        cb_frame2.grid(row=row, column=0, sticky='w', pady=(0, 6), columnspan=2)
        self.rag_var = tk.BooleanVar(value=DEFAULTS["rag_enabled"])
        ttk.Checkbutton(cb_frame2, text="RAG召回", variable=self.rag_var).pack(side='left', padx=(0, 20))
        self.agent_var = tk.BooleanVar(value=DEFAULTS["agent_filter"])
        ttk.Checkbutton(cb_frame2, text="Agent筛选", variable=self.agent_var).pack(side='left')

        row += 1
        mock_frame = ttk.Frame(card)
        mock_frame.grid(row=row, column=0, sticky='w', pady=(0, 2), columnspan=2)
        self.mock_var = tk.BooleanVar(value=DEFAULTS["mock"])
        ttk.Checkbutton(mock_frame, text="离线 Mock 验证(无需 token)", variable=self.mock_var).pack(side='left')
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

        # Token / API 配置（GUI 内输入并保存，不再依赖环境变量）
        tok = ttk.LabelFrame(root, text="Token / API 配置（保存于本地 data/，不写入代码）", style='Card.TLabelframe')
        tok.pack(fill='x', padx=15, pady=(0, 8))
        tok.configure(padding=10)

        self.e2e_var = tk.StringVar(value=DEFAULTS["e2e_token"])
        self.e2mf_var = tk.StringVar(value=DEFAULTS["e2mf_token"])
        self.base_url_var = tk.StringVar(value=DEFAULTS["base_url"])
        self.show_token_var = tk.BooleanVar(value=False)

        ttk.Label(tok, text="e2e Token", font=('Microsoft YaHei', 8, 'bold')).grid(row=0, column=0, sticky='w', pady=(0, 2), columnspan=2)
        self.e2e_entry = ttk.Entry(tok, textvariable=self.e2e_var, show="*", width=46)
        self.e2e_entry.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(0, 6))

        ttk.Label(tok, text="e2mf Token（可选）", font=('Microsoft YaHei', 8, 'bold')).grid(row=2, column=0, sticky='w', pady=(0, 2), columnspan=2)
        self.e2mf_entry = ttk.Entry(tok, textvariable=self.e2mf_var, show="*", width=46)
        self.e2mf_entry.grid(row=3, column=0, columnspan=2, sticky='ew', pady=(0, 6))

        ttk.Label(tok, text="接口 Base URL（可选）", font=('Microsoft YaHei', 8, 'bold')).grid(row=4, column=0, sticky='w', pady=(0, 2), columnspan=2)
        ttk.Entry(tok, textvariable=self.base_url_var, width=46).grid(row=5, column=0, columnspan=2, sticky='ew', pady=(0, 6))

        show_cb = ttk.Checkbutton(tok, text="显示 Token 明文", variable=self.show_token_var,
                                  command=lambda: self._toggle_token_visibility())
        show_cb.grid(row=6, column=0, sticky='w', pady=(0, 2))
        ttk.Label(tok, text="取消「离线 Mock」后，将使用此处填入的 token 跑真实接口",
                  style='Status.TLabel').grid(row=6, column=1, sticky='w', pady=(0, 2))
        tok.columnconfigure(0, weight=1)
        tok.columnconfigure(1, weight=1)

        # 操作
        action = ttk.LabelFrame(root, text="操作", style='Card.TLabelframe')
        action.pack(fill='x', padx=15, pady=(0, 8))
        action.configure(padding=8)
        left = ttk.Frame(action)
        left.pack(side='left')
        ttk.Label(left, text="今日已投:", font=('Microsoft YaHei', 8)).pack(side='left')
        self.today_var = tk.StringVar(value=str(get_today_count()))
        ttk.Label(left, textvariable=self.today_var, font=('Microsoft YaHei', 10, 'bold'), foreground=DANGER).pack(side='left', padx=(3, 10))
        ttk.Button(left, text="重置计数", command=self.reset_count, style='Warning.TButton').pack(side='left')
        right = ttk.Frame(action)
        right.pack(side='right')
        self.start_btn = ttk.Button(right, text="开始投递", command=self.start_apply, style='Primary.TButton', width=10)
        self.start_btn.pack(side='left')
        self.stop_btn = ttk.Button(right, text="终止", command=self.stop_apply, style='Danger.TButton', width=6, state='disabled')
        self.stop_btn.pack(side='left', padx=(6, 0))

        # 飞轮
        fly = ttk.LabelFrame(root, text="飞轮", style='Card.TLabelframe')
        fly.pack(fill='x', padx=15, pady=(0, 8))
        fly.configure(padding=8)
        self.fly_var = tk.StringVar(value="加载中...")
        ttk.Label(fly, textvariable=self.fly_var, style='Status.TLabel').pack(anchor='w', pady=(0, 4))
        btn_row = ttk.Frame(fly)
        btn_row.pack(fill='x')
        ttk.Button(btn_row, text="标注", command=self.open_label_window, style='Success.TButton').pack(side='left', padx=(0, 4))
        ttk.Button(btn_row, text="挖掘规则", command=self.open_suggest_window, style='Warning.TButton').pack(side='left', padx=(0, 4))
        ttk.Button(btn_row, text="趋势", command=self.open_trend_window, style='Info.TButton').pack(side='left', padx=(0, 4))
        ttk.Button(btn_row, text="刷新", command=self.refresh_flywheel_status, style='Light.TButton').pack(side='left')

        # 智能简历
        resume_frame = ttk.LabelFrame(root, text="智能简历", style='Card.TLabelframe')
        resume_frame.pack(fill='x', padx=15, pady=(0, 8))
        resume_frame.configure(padding=8)
        ttk.Label(resume_frame, text="上传简历 → 匹配JD → 优化简历 → 生成打招呼语", style='Status.TLabel').pack(anchor='w', pady=(0, 4))
        ttk.Button(resume_frame, text="打开智能简历助手", command=self.open_resume_window, style='Primary.TButton').pack(side='left')

        self.status_var = tk.StringVar(value="就绪 (API 模式)")
        ttk.Label(root, textvariable=self.status_var, style='Status.TLabel').pack(fill='x', padx=15, pady=(0, 10), anchor='e')

        self.pipeline = pipeline.Pipeline()
        self.load_settings()
        self.refresh_flywheel_status()

    # ---------- 设置 ----------
    def _toggle_token_visibility(self):
        show = "" if self.show_token_var.get() else "*"
        self.e2e_entry.config(show=show)
        self.e2mf_entry.config(show=show)

    def save_settings(self):
        cfg = {
            "keywords": self.kw_var.get(),
            "city": self.city_var.get(),
            "count": self.count_var.get(),
            "exclude": self.exclude_var.get(),
            "fetch_workers": self.workers_var.get(),
            "intern": self.intern_var.get(),
            "login": self.login_var.get(),
            "rag_enabled": self.rag_var.get(),
            "agent_filter": self.agent_var.get(),
            "mock": self.mock_var.get(),
            "e2e_token": self.e2e_var.get().strip(),
            "e2mf_token": self.e2mf_var.get().strip(),
            "base_url": self.base_url_var.get().strip(),
        }
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE) or '.', exist_ok=True)
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            self.status_var.set("设置已保存")
            messagebox.showinfo("成功", "设置已保存！")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败:\n{e}")

    def load_settings(self):
        if not os.path.exists(SETTINGS_FILE):
            return
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            self.kw_var.set(cfg.get("keywords", DEFAULTS["keywords"]))
            self.city_var.set(cfg.get("city", DEFAULTS["city"]))
            self.count_var.set(cfg.get("count", DEFAULTS["count"]))
            self.exclude_var.set(cfg.get("exclude", DEFAULTS["exclude"]))
            self.workers_var.set(cfg.get("fetch_workers", DEFAULTS["fetch_workers"]))
            self.intern_var.set(cfg.get("intern", DEFAULTS["intern"]))
            self.login_var.set(cfg.get("login", DEFAULTS["login"]))
            self.rag_var.set(cfg.get("rag_enabled", DEFAULTS["rag_enabled"]))
            self.agent_var.set(cfg.get("agent_filter", DEFAULTS["agent_filter"]))
            self.mock_var.set(cfg.get("mock", DEFAULTS["mock"]))
            self.e2e_var.set(cfg.get("e2e_token", DEFAULTS["e2e_token"]))
            self.e2mf_var.set(cfg.get("e2mf_token", DEFAULTS["e2mf_token"]))
            self.base_url_var.set(cfg.get("base_url", DEFAULTS["base_url"]))
            self.status_var.set("已加载上次保存的设置")
        except Exception as e:
            self.status_var.set(f"加载设置失败: {e}")

    def restore_defaults(self):
        if not messagebox.askyesno("确认", "确定恢复所有设置为默认值？"):
            return
        self.kw_var.set(DEFAULTS["keywords"])
        self.city_var.set(DEFAULTS["city"])
        self.count_var.set(DEFAULTS["count"])
        self.exclude_var.set(DEFAULTS["exclude"])
        self.workers_var.set(DEFAULTS["fetch_workers"])
        self.intern_var.set(DEFAULTS["intern"])
        self.login_var.set(DEFAULTS["login"])
        self.rag_var.set(DEFAULTS["rag_enabled"])
        self.agent_var.set(DEFAULTS["agent_filter"])
        self.mock_var.set(DEFAULTS["mock"])
        self.e2e_var.set(DEFAULTS["e2e_token"])
        self.e2mf_var.set(DEFAULTS["e2mf_token"])
        self.base_url_var.set(DEFAULTS["base_url"])
        if os.path.exists(SETTINGS_FILE):
            os.remove(SETTINGS_FILE)
        self.status_var.set("已恢复默认设置")
        messagebox.showinfo("完成", "已恢复为默认设置")

    def reset_count(self):
        try:
            import sqlite3
            db = config_api.API_CONFIG["dedup_db"]
            if os.path.exists(db):
                conn = sqlite3.connect(db)
                conn.execute("DELETE FROM applied WHERE status='applied' AND substr(created_at,1,10)=?", (datetime.now().strftime("%Y-%m-%d"),))
                conn.commit()
                conn.close()
            self.today_var.set("0")
            self.status_var.set("已重置今日计数")
        except Exception as e:
            messagebox.showerror("错误", f"重置失败: {e}")

    # ---------- 启动投递 ----------
    def _get_config(self):
        keywords = [k.strip() for k in self.kw_var.get().replace("，", ",").split(",") if k.strip()] or KEYWORDS.copy()
        max_applies = self.count_var.get()
        max_applies = int(max_applies) if max_applies.isdigit() else MAX_DAILY_APPLIES
        workers = self.workers_var.get()
        workers = int(workers) if str(workers).isdigit() else config_api.API_CONFIG["fetch_workers"]
        exclude = [e.strip() for e in self.exclude_var.get().replace("，", ",").split(",") if e.strip()]
        return {
            "keywords": keywords,
            "city": self.city_var.get(),
            "city_code": CITY_OPTIONS.get(self.city_var.get(), CITY_OPTIONS[CITIES[0]]),
            "max_daily_applies": max_applies,
            "internship_only": self.intern_var.get(),
            "exclude_keywords": exclude,
            "rag_enabled": self.rag_var.get(),
            "agent_filter": self.agent_var.get(),
            "fetch_workers": workers,
            "scales": [],
        }

    def start_apply(self):
        cfg = self._get_config()
        use_mock = self.mock_var.get()
        e2e_token = self.e2e_var.get().strip()
        e2mf_token = self.e2mf_var.get().strip()
        base_url = self.base_url_var.get().strip()

        if not use_mock and not e2e_token:
            messagebox.showwarning(
                "缺少 Token",
                "当前未勾选「离线 Mock 验证」，但 e2e Token 为空。\n\n"
                "请在上方「Token / API 配置」中填入 token，或勾选「离线 Mock 验证」。",
            )
            return

        masked = ("*" * 8) if e2e_token else "（空）"
        msg = (f"确认开始投递（API 模式）？\n\n"
               f"关键词: {', '.join(cfg['keywords'][:5])}\n"
               f"城市:   {cfg['city']}\n"
               f"数量:   {cfg['max_daily_applies']} 个\n"
               f"并发:   {cfg['fetch_workers']} 线程\n"
               f"RAG召回: {'启用' if cfg['rag_enabled'] else '关闭'}\n"
               f"Agent:  {'启用' if cfg['agent_filter'] else '关闭'}\n"
               f"模式:   {'离线 Mock 验证' if use_mock else '真实 API'}\n"
               f"e2e Token: {masked}"
               + (f"\nBase URL: {base_url}" if base_url else ""))
        if not messagebox.askyesno("确认", msg):
            return
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        from threading import Thread
        Thread(target=self._run_apply,
               args=(cfg, use_mock, e2e_token, e2mf_token, base_url),
               daemon=True).start()

    def _run_apply(self, cfg, use_mock, e2e_token, e2mf_token, base_url):
        try:
            self.pipeline.run(cfg, on_status=self._on_status, use_mock=use_mock,
                              token=e2e_token, e2mf_token=e2mf_token, base_url=base_url)
            self._on_status(f"完成！本次投递 {self.pipeline.applied}，过滤 {self.pipeline.excluded}")
        except Exception as e:
            self._on_status(f"错误: {e}")
        finally:
            self.root.after(0, lambda: self.start_btn.config(state='normal'))
            self.root.after(0, lambda: self.stop_btn.config(state='disabled'))
            self.root.after(0, lambda: self.today_var.set(str(get_today_count())))

    def _on_status(self, text):
        self.root.after(0, lambda: self.status_var.set(text))

    def stop_apply(self):
        self.pipeline.stop_event.set()
        self.status_var.set("终止信号已发送")

    # ---------- 飞轮窗口（直接复用现有 UI 组件）----------
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
        try:
            from resume.resume_ui import ResumeWindow
            ResumeWindow(self.root)
        except Exception as e:
            messagebox.showerror("错误", f"打开智能简历助手失败: {e}")

    def refresh_flywheel_status(self):
        try:
            from flywheel import metrics
            m = metrics.compute_metrics()
            total = m.get("total_labeled", 0)
            if total == 0:
                self.fly_var.set("标注: 0 条 | 开始标注启动飞轮")
            else:
                g1, g2, g3, g4 = m.get("G1", 0), m.get("G2", 0), m.get("G3", 0), m.get("G4", 0)
                oa = m.get("overall_accuracy")
                oa_pct = f"{oa*100:.0f}%" if oa else "N/A"
                pred = metrics.predict_overall_accuracy()
                pred_str = f" | 预测:{pred*100:.0f}%" if pred is not None else ""
                self.fly_var.set(f"标注:{total}条 G1:{g1} G2:{g2} G3:{g3} G4:{g4} 综合:{oa_pct}{pred_str}")
        except Exception as e:
            self.fly_var.set(f"加载失败: {e}")


def main():
    root = tk.Tk()
    ApiConfigGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
