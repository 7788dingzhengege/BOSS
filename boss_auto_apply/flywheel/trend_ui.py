# 趋势窗口: 展示各轮准确率变化

import tkinter as tk
from tkinter import ttk
from . import metrics

# Google Material Design 配色 (模块级常量, 供所有方法使用)
LIGHT = '#f8f9fa'
BORDER = '#e0e0e0'
TEXT = '#333333'
TEXT_LIGHT = '#666666'


class TrendWindow:
    """趋势图窗口"""

    def __init__(self, parent=None):
        self.top = tk.Toplevel(parent)
        self.top.title("飞轮趋势")
        self.top.geometry("780x600")
        self.top.resizable(True, True)
        self.top.minsize(600, 450)
        self.top.lift()
        self.top.focus_force()

        style = ttk.Style()
        style.theme_use('clam')

        style.configure('TFrame', background=LIGHT)
        style.configure('TLabel', background=LIGHT, foreground=TEXT, font=('Microsoft YaHei', 9))
        style.layout('Card.TLabelframe', style.layout('TLabelframe'))
        style.configure('Card.TLabelframe', background='white', bordercolor=BORDER,
                        relief='solid', font=('Microsoft YaHei', 10, 'bold'), foreground=TEXT)

        self.top.configure(bg=LIGHT)

        self.rolling_mode = tk.BooleanVar(value=False)
        self.text_widget = None
        self.chart_canvas = None
        self.chart_card = None

        # 视图状态: 缩放(可见轮数) / 平移(起始偏移) / 预测步长
        self.all_rounds = []
        self.zoom_var = tk.IntVar(value=10)
        self.pan_var = tk.IntVar(value=0)
        self.horizon_var = tk.IntVar(value=5)
        self.info_var = tk.StringVar(value="")
        self._sliders_ready = False
        self.ctrl_frame = None
        self.info_label = None

        self._build_ui()

    def _build_ui(self):
        try:
            metrics.recompute_all_run_metrics()
        except Exception:
            pass

        header_frame = ttk.Frame(self.top, style='TFrame')
        header_frame.pack(fill='x', padx=20, pady=(15, 0))

        health = metrics.flywheel_health()
        health_label = ttk.Label(header_frame, text=f"飞轮健康度: {health}",
                                 font=('Microsoft YaHei', 11, 'bold'))
        health_label.pack(side='left')

        rolling_check = ttk.Checkbutton(header_frame, text="统一分母(消除样本量偏差)",
                                         variable=self.rolling_mode,
                                         command=self._on_toggle_rolling,
                                         style='TCheckbutton')
        rolling_check.pack(side='right')

        table_card = ttk.LabelFrame(self.top, text="趋势数据", style='Card.TLabelframe')
        table_card.pack(fill='x', padx=20, pady=(10, 10))
        table_card.configure(padding=12)

        rounds = self._get_rounds()
        self.all_rounds = rounds

        # 动态适配缩放默认值: 默认显示全部轮次 (而非硬编码 10)
        n = len(rounds)
        if n >= 2:
            self.zoom_var.set(n)      # 默认看全部
            self.pan_var.set(0)       # 从第一轮开始

        trend_text = metrics.format_trend(rounds)
        self.text_widget = tk.Text(table_card, font=('Consolas', 9), wrap='word', bg='white',
                                   borderwidth=0, highlightthickness=0, height=8)
        self.text_widget.pack(fill='x')
        self.text_widget.insert(tk.END, trend_text)
        self.text_widget.config(state='disabled')

        if len(rounds) < 2:
            ttk.Label(self.top, text="至少需要2轮标注才能画趋势图",
                      font=('Microsoft YaHei', 9), foreground=TEXT_LIGHT).pack(pady=20)
            return

        chart_card = ttk.LabelFrame(self.top, text="趋势图表", style='Card.TLabelframe')
        chart_card.pack(fill='both', expand=True, padx=20, pady=(0, 8))
        chart_card.configure(padding=12)
        self.chart_card = chart_card

        self._draw_chart(chart_card, rounds)

        # 控制条: 缩放 / 平移 / 预测步长
        self._build_controls()

        # 信息条
        self.info_label = ttk.Label(self.top, textvariable=self.info_var,
                                    font=('Microsoft YaHei', 8), foreground=TEXT_LIGHT)
        self.info_label.pack(pady=(0, 10))

    def _build_controls(self):
        """构建缩放/平移/预测控制条"""
        n = len(self.all_rounds)
        max_zoom = max(10, n)

        ctrl = ttk.Frame(self.top, style='TFrame')
        ctrl.pack(fill='x', padx=20, pady=(0, 4))
        self.ctrl_frame = ctrl

        # 缩放: 可见轮数
        ttk.Label(ctrl, text="缩放", font=('Microsoft YaHei', 8),
                  foreground=TEXT_LIGHT).grid(row=0, column=0, sticky='w')
        zoom_scale = ttk.Scale(ctrl, from_=5, to=max_zoom, orient='horizontal',
                               variable=self.zoom_var, command=self._on_view_change,
                               length=160)
        zoom_scale.grid(row=0, column=1, padx=(4, 12), sticky='ew')
        ttk.Label(ctrl, textvariable=self.zoom_var, font=('Microsoft YaHei', 8),
                  width=4).grid(row=0, column=2, sticky='w')

        # 平移: 起始偏移
        ttk.Label(ctrl, text="平移", font=('Microsoft YaHei', 8),
                  foreground=TEXT_LIGHT).grid(row=0, column=3, sticky='w')
        pan_scale = ttk.Scale(ctrl, from_=0, to=max(0, n - 5), orient='horizontal',
                              variable=self.pan_var, command=self._on_view_change,
                              length=160)
        pan_scale.grid(row=0, column=4, padx=(4, 12), sticky='ew')
        ttk.Label(ctrl, text="起始", font=('Microsoft YaHei', 8),
                  foreground=TEXT_LIGHT).grid(row=0, column=5, sticky='w')

        # 预测步长
        ttk.Label(ctrl, text="预测", font=('Microsoft YaHei', 8),
                  foreground=TEXT_LIGHT).grid(row=1, column=0, sticky='w', pady=(4, 0))
        horizon_scale = ttk.Scale(ctrl, from_=1, to=30, orient='horizontal',
                                  variable=self.horizon_var, command=self._on_view_change,
                                  length=160)
        horizon_scale.grid(row=1, column=1, padx=(4, 12), pady=(4, 0), sticky='ew')
        ttk.Label(ctrl, textvariable=self.horizon_var, font=('Microsoft YaHei', 8),
                  width=4).grid(row=1, column=2, pady=(4, 0), sticky='w')

        ctrl.columnconfigure(1, weight=1)
        ctrl.columnconfigure(4, weight=1)
        self._sliders_ready = True

    def _on_view_change(self, *_args):
        """缩放/平移/预测滑块变化时重绘画布"""
        if not self._sliders_ready or self.chart_canvas is None:
            return
        # 修正越界: 平移不能让可见窗口超出数据范围
        n = len(self.all_rounds)
        zoom = self.zoom_var.get()
        if zoom > n:
            self.zoom_var.set(n)
            zoom = n
        max_pan = max(0, n - zoom)
        if self.pan_var.get() > max_pan:
            self.pan_var.set(max_pan)
        self.chart_canvas.delete('all')
        self._draw_chart(self.chart_card, self.all_rounds)

    def _on_toggle_rolling(self):
        self._refresh_ui()

    def _get_rounds(self):
        if self.rolling_mode.get():
            return metrics.compute_all_runs_rolling()
        else:
            return metrics.compute_all_runs()

    def _refresh_ui(self):
        try:
            metrics.recompute_all_run_metrics()
        except Exception:
            pass

        rounds = self._get_rounds()
        self.all_rounds = rounds

        if self.text_widget:
            self.text_widget.config(state='normal')
            self.text_widget.delete(1.0, tk.END)
            trend_text = metrics.format_trend(rounds)
            self.text_widget.insert(tk.END, trend_text)
            self.text_widget.config(state='disabled')

        if self.chart_card:
            self.chart_card.destroy()
            self.chart_card = None
            self.chart_canvas = None

        # 销毁旧控制条和信息条, 避免切换时重复堆叠
        if self.ctrl_frame is not None:
            self.ctrl_frame.destroy()
            self.ctrl_frame = None
        if self.info_label is not None:
            self.info_label.destroy()
            self.info_label = None

        if len(rounds) >= 2:
            # 重置滑块范围并适配当前数据量: 默认显示全部轮次
            n = len(rounds)
            self._sliders_ready = False
            self.zoom_var.set(n)      # 切换后默认显示全部
            self.pan_var.set(0)       # 从第一轮开始

            chart_card = ttk.LabelFrame(self.top, text="趋势图表", style='Card.TLabelframe')
            chart_card.pack(fill='both', expand=True, padx=20, pady=(0, 8))
            chart_card.configure(padding=12)
            self.chart_card = chart_card
            self._draw_chart(chart_card, rounds)
            self._build_controls()
            self.info_label = ttk.Label(self.top, textvariable=self.info_var,
                                       font=('Microsoft YaHei', 8), foreground=TEXT_LIGHT)
            self.info_label.pack(pady=(0, 10))

    def _draw_chart(self, parent, rounds):
        """用 Canvas 画美化后的折线图, 支持缩放/平移/多步预测"""
        W, H = 720, 350
        PAD_L, PAD_B, PAD_T, PAD_R = 60, 50, 30, 60

        # 复用画布: 已存在则清空, 否则创建
        if self.chart_canvas is None:
            self.chart_canvas = tk.Canvas(parent, width=W, height=H, bg='white', highlightthickness=0)
            self.chart_canvas.pack(fill='both', expand=True)
        else:
            self.chart_canvas.delete('all')

        n_total = len(rounds)
        if n_total < 2:
            return

        # 应用缩放/平移窗口
        zoom = max(2, min(self.zoom_var.get(), n_total))
        pan = max(0, min(self.pan_var.get(), n_total - zoom))
        horizon = max(1, self.horizon_var.get())

        visible = rounds[pan:pan + zoom]
        n = len(visible)

        # 总 x 轴槽位 = 可见轮 + 预测步数 (预留空间给预测线延伸)
        total_slots = (n - 1) + horizon
        if total_slots < 1:
            total_slots = 1

        chart_w = W - PAD_L - PAD_R
        chart_h = H - PAD_T - PAD_B
        step_w = chart_w / total_slots

        # 坐标轴
        self.chart_canvas.create_line(PAD_L, H - PAD_B, W - PAD_R, H - PAD_B, fill='#ccc', width=1.5)
        self.chart_canvas.create_line(PAD_L, PAD_T, PAD_L, H - PAD_B, fill='#ccc', width=1.5)

        for pct in (0, 25, 50, 75, 100):
            y = H - PAD_B - (chart_h * pct / 100)
            self.chart_canvas.create_text(PAD_L - 8, y, text=f"{pct}%", font=('Microsoft YaHei', 8),
                                          anchor='e', fill='#666')
            self.chart_canvas.create_line(PAD_L, y, W - PAD_R, y, fill='#f0f0f0', dash=(3, 3))

        # 两段配色: 规则段(原色) vs embedding段(区分色)
        # 规则段: 综合=蓝 投递=绿 过滤=橙
        # embedding段: 综合=紫 投递=青 过滤=红
        lines_rule = [
            ("overall_accuracy", '#1a73e8', '综合准确率(规则)'),
            ("apply_accuracy", '#43a047', '投递准确率(规则)'),
            ("exclude_accuracy", '#ff9800', '过滤准确率(规则)'),
        ]
        lines_embed = [
            ("overall_accuracy", '#8e24aa', '综合准确率(Embedding)'),
            ("apply_accuracy", '#00897b', '投递准确率(Embedding)'),
            ("exclude_accuracy", '#e53935', '过滤准确率(Embedding)'),
        ]

        # 滚动累计模式下才分段绘制; 单轮模式 is_embedding 字段不存在, 全用规则色
        use_split = self.rolling_mode.get() and any("is_embedding" in r for r in visible)

        def draw_segment(seg_lines, seg_records, offset_i):
            """绘制一段折线 + 数据点"""
            for key, color, label in seg_lines:
                points = []
                for i, r in enumerate(seg_records):
                    val = r.get(key)
                    if val is None:
                        continue
                    x = PAD_L + step_w * (offset_i + i)
                    y = H - PAD_B - (chart_h * val)
                    points.append((x, y))
                for j in range(len(points) - 1):
                    self.chart_canvas.create_line(points[j][0], points[j][1], points[j+1][0], points[j+1][1],
                                                  fill=color, width=2.5, smooth=True)
                for x, y in points:
                    self.chart_canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill='white', outline=color, width=2)
                    self.chart_canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill=color, outline='')

        if use_split:
            # 分段: 找到第一个 is_embedding=True 的索引
            split_idx = next((i for i, r in enumerate(visible) if r.get("is_embedding")), len(visible))
            rule_part = visible[:split_idx]
            embed_part = visible[split_idx:]
            # 绘制规则段
            if rule_part:
                draw_segment(lines_rule, rule_part, 0)
            # 绘制 embedding 段 (offset = 规则段长度)
            if embed_part:
                draw_segment(lines_embed, embed_part, split_idx)
            # 跨段虚线连接: 规则段最后一点 → embedding 段第一点 (每个指标一条)
            if rule_part and embed_part:
                x1 = PAD_L + step_w * (split_idx - 1)
                x2 = PAD_L + step_w * split_idx
                for key, ecolor, _ in lines_embed:
                    v1 = rule_part[-1].get(key)
                    v2 = embed_part[0].get(key)
                    if v1 is None or v2 is None:
                        continue
                    y1 = H - PAD_B - (chart_h * v1)
                    y2 = H - PAD_B - (chart_h * v2)
                    self.chart_canvas.create_line(x1, y1, x2, y2,
                                                  fill=ecolor, width=2, dash=(6, 4))
            # 分界点竖虚线 + 标签
            if 0 < split_idx < n:
                bx = PAD_L + step_w * split_idx
                self.chart_canvas.create_line(bx, PAD_T, bx, H - PAD_B,
                                              fill='#9c27b0', width=1.5, dash=(4, 4))
                self.chart_canvas.create_text(bx, PAD_T - 6, text="Embedding上线",
                                              font=('Microsoft YaHei', 8, 'bold'),
                                              fill='#9c27b0', anchor='n')
            lines_for_legend = lines_rule + lines_embed
        else:
            # 单轮模式或无 is_embedding 字段: 全部用规则色
            draw_segment(lines_rule, visible, 0)
            lines_for_legend = lines_rule

        # x 轴标签 (数据多时稀疏显示, 避免重叠)
        label_step = max(1, n // 12)
        for i, r in enumerate(visible):
            if i % label_step != 0 and i != n - 1:
                continue
            rid = str(r.get("run_id", ""))[:10]
            x = PAD_L + step_w * i
            self.chart_canvas.create_text(x, H - PAD_B + 20, text=rid, font=('Microsoft YaHei', 8),
                                          anchor='n', fill='#666')

        # ====== Holt 多步预测 (综合准确率) ======
        overall_series = [r.get("overall_accuracy") for r in visible if r.get("overall_accuracy") is not None]
        last_oa = visible[-1].get("overall_accuracy") if visible else None

        if last_oa is not None and len(overall_series) >= 3:
            last_idx = n - 1
            last_x = PAD_L + step_w * last_idx
            last_y = H - PAD_B - (chart_h * last_oa)

            # 逐步预测 horizon 步
            prev_x, prev_y = last_x, last_y
            for h in range(1, horizon + 1):
                pred = metrics.predict_next_round(overall_series, alpha=0.5, beta=0.3, horizon=h)
                if pred is None:
                    break
                pred_x = PAD_L + step_w * (last_idx + h)
                pred_y = H - PAD_B - (chart_h * pred)

                # 虚线连接上一点到当前预测点
                self.chart_canvas.create_line(prev_x, prev_y, pred_x, pred_y,
                                              fill='#1a73e8', width=2, dash=(6, 3))
                # 预测点空心圆
                self.chart_canvas.create_oval(pred_x - 6, pred_y - 6, pred_x + 6, pred_y + 6,
                                              fill='white', outline='#1a73e8', width=2)
                self.chart_canvas.create_oval(pred_x - 2, pred_y - 2, pred_x + 2, pred_y + 2,
                                              fill='#1a73e8', outline='')

                # 末尾预测点标注数值
                if h == horizon or h == 1:
                    self.chart_canvas.create_text(pred_x, pred_y - 12,
                                                  text=f"{pred*100:.1f}%",
                                                  font=('Microsoft YaHei', 8, 'bold'),
                                                  fill='#1a73e8', anchor='e')
                # x 轴标签
                self.chart_canvas.create_text(pred_x, H - PAD_B + 20, text=f"+{h}",
                                              font=('Microsoft YaHei', 8), fill='#1a73e8', anchor='n')
                prev_x, prev_y = pred_x, pred_y

            # 预测段标识
            mid_h = max(1, horizon // 2)
            mid_x = PAD_L + step_w * (last_idx + mid_h)
            self.chart_canvas.create_text(mid_x, PAD_T - 12, text=f"预测趋势 (未来{horizon}轮)",
                                          font=('Microsoft YaHei', 8), fill='#1a73e8', anchor='n')

        # 图例 (根据是否分段显示对应数量的图例项)
        legend_y = PAD_T
        for idx, (_, color, label) in enumerate(lines_for_legend):
            self.chart_canvas.create_rectangle(W - PAD_R - 85, legend_y + idx * 22,
                                                W - PAD_R - 73, legend_y + idx * 22 + 10, fill=color, outline='')
            self.chart_canvas.create_text(W - PAD_R - 68, legend_y + idx * 22 + 5, text=label,
                                          font=('Microsoft YaHei', 8), anchor='w', fill='#333333')

        # 更新信息条
        start_id = str(visible[0].get("run_id", ""))[:10] if visible else "?"
        end_id = str(visible[-1].get("run_id", ""))[:10] if visible else "?"
        self.info_var.set(
            f"显示 第{pan+1}-{pan+n}轮 (共{n_total}轮)  |  预测未来{horizon}轮  |  "
            f"窗口 [{start_id} → {end_id}]"
        )