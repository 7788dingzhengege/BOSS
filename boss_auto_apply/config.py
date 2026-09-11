# BOSS直聘自动投递 - 配置文件

# 搜索关键词
KEYWORDS = ["AI", "VibeCoding", "Vibe Coding", "人工智能", "AIGC", "大模型"]

# 白名单：职位名/公司名必须命中其一才投递（用于提升准确度，过滤不相关岗）
# 命中即"高置信保留"；全部未命中则跳过
INCLUDE_KEYWORDS = ["AI", "AIGC", "大模型", "LLM", "RAG", "Agent", "人工智能",
                    "机器学习", "深度学习", "算法", "NLP", "CV", "数据", "产品", "实习"]

# 城市选项 (名称: city_code)
CITY_OPTIONS = {
    "全国": "100010000",
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280100",
    "深圳": "101280600",
    "杭州": "101210100",
    "西安": "101110100",
    "成都": "101270100",
    "苏州": "101190400",
}

# 默认城市
CITIES = ["北京"]

# 每日最大投递数
MAX_DAILY_APPLIES = 130

# 测试模式：限制总投递数量（None=不限制）
TEST_LIMIT = None

# 操作间隔时间范围（秒）- 越短越快
DELAY_RANGE = (1, 2)

# BOSS直聘网址
BOSS_URL = "https://www.zhipin.com/"

# 数据文件路径
APPLIED_FILE = "data/applied.json"

# 浏览器配置
BROWSER_CONFIG = {
    "browser_type": "edge",
    "headless": False,
    "window_size": (1920, 1080),
}

# 定时投递（北京时间）
SCHEDULE_CONFIG = {
    "enabled": False,
    "hour": 9,
    "minute": 0,
}

# 公司规模选项 (名称: scale_code)
SCALE_OPTIONS = {
    "500-1000人": "304",
    "1000-10000人": "305",
    "10000人以上": "306",
}

FILTER_CONFIG = {
    # 只投实习岗
    "internship_only": True,
    # 排序：latest=最新发布, recommend=推荐
    "sort_by": "latest",
    # 排除关键词（职位名/公司名含这些词的跳过）
    "exclude_keywords": ["销售", "外包", "电话销售", "客服", "电销", "推广", "中介", "剧"],
    # ====== 扩展规则筛选（在卡片信息上做快速过滤，无需进入详情页）======
    # 期望薪资范围（元/月），None=不限。如 (8000, 25000) 表示 8K-25K
    "salary_range": (3000, 40000),  # 元/月；过滤 <3K 与 >40K 的岗位，按个人期望调整
    # 薪资"面议"的处理：True=保留(不过滤)，False=跳过
    "allow_salary_negotiable": True,
    # 期望工作年限上限（年），None=不限。JD要求超过此值的跳过
    "max_experience_years": None,
    # 学历要求下限："不限" / "大专" / "本科" / "硕士" / "博士"
    "min_education": "不限",
}

# ====== 求职者画像（Agent 智能筛选的基准）======
# 请根据自身情况修改以下内容，Agent 会基于此判断 JD 匹配度
JOB_SEEKER_PROFILE = {
    # 目标职位/角色
    "target_roles": ["AI产品经理", "AIGC开发", "大模型应用开发", "AI Agent开发"],
    # 核心技能（Agent 会检查 JD 是否要求相关技能）
    "skills": ["Python", "LLM", "RAG", "AI Agent", "AIGC", "Prompt Engineering", "产品设计"],
    # 经验阶段："在校实习" / "应届" / "1-3年" / "3-5年" / "5年以上"
    "experience": "在校实习",
    # 学历
    "education": "本科",
    # 偏好行业
    "preferred_industries": ["AI/大模型", "互联网", "科技"],
    # 明确回避（比 exclude_keywords 更语义化，Agent 理解）
    "avoid": ["纯销售岗", "外包", "培训公司", "传统行业无AI业务", "强制加班"],
    # 其他偏好（自由文本，Agent 会理解）
    "preferences": "希望做大模型应用相关的工作，技术驱动型团队优先，关注产品落地",
}

# ====== Agent 智能筛选配置 ======
AGENT_FILTER_CONFIG = {
    # 是否启用 Agent 筛选（严格模式）。False=仅用规则筛选
    "enabled": False,
    # DeepSeek API 配置（兼容 OpenAI 接口）
    "api_base": "https://api.deepseek.com/v1",
    # API Key 从环境变量读取，避免硬编码泄露
    "api_key_env": "DEEPSEEK_API_KEY",
    # 模型名称
    "model": "deepseek-chat",
    # 匹配度最低分（0-100），低于此分则拒绝投递
    "min_score": 60,
    # API 超时（秒）
    "timeout": 15,
    # 触发策略：
    # "always" = 规则通过后必过 Agent
    # "on_uncertain" = 仅当规则无法完全判断时才调 Agent（如薪资面议、JD信息模糊）
    "trigger": "on_uncertain",
}

# ====== RAG 召回配置 (n-gram 相似度 + 飞轮历史投票) ======
RAG_CONFIG = {
    # 是否启用 RAG 召回层（在关键词过滤之后生效）
    "enabled": True,
    # 召回历史相似职位数量
    "top_k": 5,
    # n-gram 相似度阈值（0~1），低于此值的样本不参与投票
    "threshold": 0.2,
    # 投票 accept 比例阈值（>=此值则判定为 apply）
    "accept_threshold": 0.6,
    # 投票 reject 比例阈值（<=此值则判定为 exclude）
    "reject_threshold": 0.4,
    # 置信度阈值（>=此值才采纳投票结果）
    "confidence_threshold": 0.3,
}

# ====== 简历智能匹配与生成配置 ======
RESUME_CONFIG = {
    # 是否启用简历匹配分析
    "enabled": False,
    # PDF 简历文件路径（文本型PDF）
    "pdf_path": "data/resume.pdf",
    # DOCX 简历模板路径（用于生成定制简历，可从PDF转换或自行准备）
    "template_path": "data/resume_template.docx",
    # 定制简历输出目录
    "output_dir": "data/custom_resumes",
    # 匹配度阈值：高于此值才生成定制简历
    "match_threshold": 60,
    # 是否在投递时自动生成定制简历
    "auto_generate": False,
    # 生成简历的最大数量（每次运行）
    "max_generate_per_run": 5,
}

# ====== BOSS直聘限制处理配置 ======
BOSS_LIMIT_CONFIG = {
    # 每日沟通次数上限（BOSS直聘约150次）
    "daily_chat_limit": 150,
    # 达到限制后是否自动等待到次日0点继续投递
    "auto_continue_next_day": True,
    # 无新职位时最大滚动次数（超过则换下一个关键词，BOSS直聘是无限滚动加载）
    "max_empty_scrolls": 200,
    # 连续全部被过滤的最大批次数（超过则加速下滑，继续找更多职位）
    "max_filtered_batches": 10,
    # 连续无进展轮数（超过则退出，None=不设限，不达目标不退出）
    "max_no_progress_rounds": None,
    # 最大轮询轮数（None=无限轮询，不达目标不退出）
    "max_rounds": None,
    # 操作间隔（秒），越小速度越快
    "delay_range": (0.3, 0.6),
    # 定时刷新页面间隔（秒），默认300秒=5分钟
    "refresh_interval": 300,
    # 刷新后等待时间（秒），默认10秒
    "refresh_wait": 10,
}
