# BOSS直聘HR助手 - 配置文件

# ====== 浏览器配置 ======
BROWSER_CONFIG = {
    "browser_type": "edge",
    "headless": False,
    "window_size": (1920, 1080),
}

# BOSS直聘网址
BOSS_URL = "https://www.zhipin.com/web/geek/chat"

# ====== API配置 ======
API_CONFIG = {
    "api_base": "https://api.deepseek.com/v1",
    "api_key_env": "DEEPSEEK_API_KEY",
    "model": "deepseek-chat",
    "timeout": 30,
    "temperature": 0.7,
}

# ====== 招聘岗位配置 ======
# 默认招聘岗位（可在GUI中修改）
DEFAULT_POSITION = {
    "name": "AI产品经理实习生",
    "department": "AI产品部",
    "jd": """岗位名称：AI产品经理实习生

工作内容：
1. 参与AI产品的需求调研、产品设计和迭代优化
2. 对接算法/研发团队，推动AI功能落地
3. 跟踪产品数据，持续优化用户体验
4. 参与AI相关的竞品分析和行业研究

任职要求：
1. 本科及以上学历，对AI/大模型有浓厚兴趣
2. 了解产品设计基本流程，有产品实习经验优先
3. 具备良好的逻辑思维和沟通能力
4. 熟悉Axure、Figma、SQL、Excel等工具优先
5. 每周至少到岗4天，可稳定实习3个月以上

工作地点：北京
薪资：300-500元/天
""",
    "requirements": {
        "min_education": "本科",
        "min_experience": "在校实习",
        "required_skills": ["产品设计", "需求分析", "Axure", "Figma"],
        "preferred_skills": ["AI", "大模型", "Python", "SQL"],
        "work_location": "北京",
        "salary_range": "300-500元/天",
    }
}

# ====== 公司信息（用于自动回复） ======
COMPANY_INFO = {
    "name": "科技公司",
    "industry": "互联网/AI",
    "size": "500-1000人",
    "description": "快速成长的AI科技公司，专注大模型应用落地",
    "benefits": ["弹性工作", "免费三餐", "转正机会"],
}

# ====== 简历筛选配置 ======
RESUME_FILTER_CONFIG = {
    "enabled": True,
    "min_score": 70,  # 低于此分不推荐
    "auto_reply_enabled": True,  # 是否自动回复
    "reply_threshold": 70,  # 达到此分自动发邀约
}

# ====== 自动回复配置 ======
AUTO_REPLY_CONFIG = {
    "enabled": True,
    "auto_reply_levels": ["强烈推荐", "推荐"],  # 哪些级别自动回复
    "working_hours_only": True,  # 仅工作时间自动回复
    "working_hours": [9, 19],  # 工作时间范围 [开始, 结束]
    "reply_delay_range": [3, 10],  # 回复延迟秒数（模拟人工）
}

# ====== 消息监听配置 ======
MESSAGE_CONFIG = {
    "check_interval": 5,  # 检查新消息间隔（秒）
    "max_auto_replies_per_day": 100,  # 每日最大自动回复数
}

# ====== 数据文件路径 ======
DATA_DIR = "data"
CANDIDATES_FILE = "data/candidates.json"
MESSAGES_FILE = "data/messages.json"
SETTINGS_FILE = "data/settings.json"

# ====== 回复模式配置 ======
# reply_mode: "template" = 固定模板（无需API，推荐）, "ai" = AI生成（需API Key）
REPLY_MODE = "template"

# ====== 固定回复模板 ======
# 可在GUI中编辑修改
REPLY_TEMPLATES = {
    "收到新投递（初筛通过，邀请沟通）": {
        "reply_text": "您好！感谢您投递我们的岗位，看了您的简历觉得很匹配，方便约个时间简单沟通一下吗？😊",
        "next_action": "继续沟通",
        "urgency": "高",
        "tags": ["初筛通过", "邀约沟通"],
    },
    "收到新投递（初筛不通过）": {
        "reply_text": "您好！感谢您的投递，我们已经认真查看了您的简历，目前这个岗位方向不太匹配，已经把您的简历存入人才库，后续有合适的机会再联系您~",
        "next_action": "存入人才池",
        "urgency": "低",
        "tags": ["婉拒", "人才池"],
    },
    "候选人询问岗位详情": {
        "reply_text": "您好！这个岗位主要负责AI产品的需求设计和迭代，需要有产品相关经验，薪资300-500元/天，每周至少到岗4天。您这边对哪个方向比较感兴趣呀？",
        "next_action": "继续沟通",
        "urgency": "中",
        "tags": ["岗位咨询"],
    },
    "邀约面试": {
        "reply_text": "您好！和您简单沟通后觉得很合适，想邀请您参加一轮面试。面试是线上视频形式，大概30分钟。您看这几个时间哪个方便呀：\n1. 明天上午10:00\n2. 明天下午15:00\n3. 后天上午11:00",
        "next_action": "邀约面试",
        "urgency": "高",
        "tags": ["面试邀约"],
    },
    "候选人主动打招呼": {
        "reply_text": "您好~感谢关注我们的岗位！简单介绍一下：这是AI产品经理实习岗，参与AI产品的需求设计和落地，有转正机会。您有相关产品经验吗？",
        "next_action": "继续沟通",
        "urgency": "中",
        "tags": ["主动招呼"],
    },
    "候选人婉拒": {
        "reply_text": "好的，理解~感谢您的考虑，希望以后有机会合作！祝您求职顺利😊",
        "next_action": "结束沟通",
        "urgency": "低",
        "tags": ["婉拒回应"],
    },
}

# ====== 日志配置 ======
LOG_FILE = "data/hr_helper.log"
LOG_LEVEL = "INFO"
