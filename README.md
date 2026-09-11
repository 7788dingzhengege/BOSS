# BOSS 直聘智能自动投递工具

> 基于"规则 + 飞轮 + RAG"三层架构的智能求职投递系统，配套 Tkinter 桌面 GUI。

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org)
[![Selenium](https://img.shields.io/badge/Selenium-4-green)](https://www.selenium.dev)
[![License](https://img.shields.io/badge/License-MIT-yellow)]()

## ✨ 项目亮点

| 模块 | 功能 |
|------|------|
| 🤖 **三层过滤** | 关键词粗筛 → RAG 召回 → Agent 智能筛选 |
| 🌀 **规则飞轮** | 人工标注 → 规则挖掘 → 自动更新 |
| 📈 **趋势分析** | 累计混淆矩阵 + Laplace 平滑 + Holt 预测 |
| 🖥️ **桌面 GUI** | ttk 美化卡片 + Canvas 趋势图 + 实时飞轮状态 |
| 📄 **简历智能** | PDF 解析 + JD 匹配 + 定制简历生成 |
| ⏹️ **优雅终止** | 投递中可随时停止，断点续投 |

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────┐
│                GUI (Tkinter)                    │
│  投递设置 | 操作控制 | 飞轮状态 | 趋势图表       │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│            Applier 投递引擎                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ 关键词   │→ │ RAG 召回 │→ │ Agent    │       │
│  │ 排除     │  │ 投票     │  │ 重排(可选)│      │
│  └──────────┘  └──────────┘  └──────────┘       │
└────────────────────┬────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
   ┌────────┐   ┌────────┐   ┌────────┐
   │ Browser│   │ 飞轮   │   │ 简历   │
   │ Selenium│  │ 数据层 │   │ 智能匹配│
   └────────┘   └────────┘   └────────┘
```

## 🌀 规则飞轮核心流程

```
投递  →  关键词/RAG过滤  →  人工标注（👍/👎）
                              ↓
                         飞轮历史库
                              ↓
                  n-gram 挖掘排除词/白名单
                              ↓
                         规则更新(v++)
                              ↓
                         下次投递生效
```

## 📊 工业级指标算法

### 1. 累计混淆矩阵（统一分母）
```
acc_t = (ΣG1_i + ΣG4_i) / (ΣG1_i + ΣG2_i + ΣG3_i + ΣG4_i)
```
解决小样本波动问题。

### 2. Laplace 平滑
```
acc_smooth = (sum + α) / (count + 2α)    # α=1
```
防止第一轮出现 100% / 0% 的虚假极值。

### 3. Holt 指数平滑预测
```
level = α·x + (1-α)·(level + trend)       # α=0.5
trend = β·(level - prev_level) + (1-β)·trend  # β=0.3
pred  = level + horizon·trend
```
预测下一轮综合准确率。

## 🚀 快速开始

### 1. 环境准备
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置 DeepSeek API（可选，用于 Agent 筛选）
set DEEPSEEK_API_KEY=your_api_key
```

### 2. 启动 GUI
```bash
python gui.py
```

### 3. 启动 CLI 投递
```bash
python boss_auto_apply.py
```

## 📁 项目结构

```
boss_auto_apply/
├── gui.py                     # Tkinter 桌面配置界面
├── applier.py                 # 核心投递引擎
├── browser.py                 # Selenium 浏览器管理
├── config.py                  # 配置文件
├── agent_filter.py            # DeepSeek Agent 筛选
│
├── flywheel/                  # 飞轮子系统
│   ├── store.py               # 数据存储 (labels/rules/metrics)
│   ├── decision.py            # 规则决策
│   ├── labeler.py             # 标注逻辑
│   ├── miner.py               # 规则挖掘（n-gram 频次）
│   ├── metrics.py             # 准确率 + Holt 预测
│   ├── embedding_filter.py    # RAG 召回 + 飞轮投票
│   ├── label_ui.py            # 标注窗口 GUI
│   ├── suggest_ui.py          # 规则建议窗口
│   └── trend_ui.py            # 趋势图窗口
│
├── resume/                    # 简历子系统
│   ├── parser.py              # PDF 解析
│   ├── matcher.py             # JD 匹配
│   ├── optimizer.py           # 简历优化
│   └── generator.py           # DOCX 生成
│
├── data/
│   ├── labels.json            # 标注数据
│   ├── rules.json             # 当前规则（含版本号）
│   ├── metrics_history.json   # 历史指标
│   └── resume.pdf             # 用户简历
│
└── logs/                      # 运行日志
```

## 🎯 使用流程

1. **配置参数**：在 GUI 中设置关键词、城市、排除词、投递数量等
2. **启动投递**：点击「开始投递」，浏览器自动打开 BOSS 直聘
3. **等待完成**：实时显示进度，可随时「终止」
4. **人工标注**：投递后点击「标注」按钮，对已投递/被过滤的职位做 👍/👎 标注
5. **挖掘规则**：点击「挖掘规则」，AI 自动发现新的排除词/白名单
6. **查看趋势**：点击「趋势」查看历史准确率曲线 + 下一轮预测

## 🔧 核心配置

### 关键词（config.py）
```python
KEYWORDS = ["AI", "VibeCoding", "AIGC", "大模型"]
```

### 排除词
```python
FILTER_CONFIG = {
    "exclude_keywords": ["销售", "外包", "电话销售", "客服", "电销", "推广", "中介"]
}
```

### RAG 召回（n-gram 相似度）
```python
RAG_CONFIG = {
    "enabled": True,           # 是否启用
    "top_k": 5,                # 召回 Top-K
    "threshold": 0.2,          # 相似度阈值
    "accept_threshold": 0.6,   # 投票通过比例
    "reject_threshold": 0.4,   # 投票拒绝比例
    "confidence_threshold": 0.3  # 置信度门槛
}
```

## 📈 飞轮指标示例

| 轮次 | 投递准确 | 过滤准确 | 综合准确 | 错投 | 漏投 |
|------|----------|----------|----------|------|------|
| r1   | 66.7%    | 100%     | 66.7%    | 2    | 0    |
| r2   | 71.0%    | 100%     | 71.0%    | 5    | 0    |
| r3   | 80.0%    | 100%     | 80.0%    | 2    | 0    |
| 下一轮预测 | 84.9%    | -        | -        | -    | -    |

## 🛠️ 进阶优化（可选）

- **真实 Embedding**：将 `ngram_similarity` 替换为 `sentence-transformers` 向量检索
- **LLM 重排**：在 RAG 召回后用 DeepSeek 对 Top-K 重排序
- **多平台支持**：抽象 Browser 层，扩展到拉勾/猎聘/V2EX
- **数据库迁移**：labels/rules 改用 SQLite，支持高并发

## ⚠️ 免责声明

本项目仅供学习交流使用，请遵守 BOSS 直聘用户协议和相关法律法规。
- 合理设置投递频率，避免账号风控
- 仅用于个人求职场景，禁止商用

## 📄 License

MIT
