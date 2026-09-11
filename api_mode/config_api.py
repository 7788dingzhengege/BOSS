# API 模式配置
#
# 上半部分：直接复用 boss_auto_apply.config 的字段结构（关键词/城市/画像/Agent/RAG 配置），
#           保证与旧模式完全一致的过滤语义。
# 下半部分：API 模式专属配置（token 环境变量名、并发度、限速、去重库路径）。
#           你通常只需要改这里，以及在 api_client.py 里填你的 token + 接口。

from config import (
    KEYWORDS, CITIES, CITY_OPTIONS, MAX_DAILY_APPLIES,
    FILTER_CONFIG, JOB_SEEKER_PROFILE, AGENT_FILTER_CONFIG, RAG_CONFIG,
)

# ====== API 模式专属配置 ======
API_CONFIG = {
    # token 从环境变量读取，避免硬编码泄露（你的 e2e / e2mf token 放这里）
    "token_env": "BOSS_API_TOKEN",

    # api_client.py 中你实现的适配器类名（留空字符串时用 Mock 离线验证）
    "job_source_cls": "UserJobSource",
    "apply_client_cls": "UserApplyClient",

    # FETCH 并发度（线程池大小）。平台有风控，4~8 足够，别开太大
    "fetch_workers": 4,

    # 单次搜索返回的最大职位数
    "max_results_per_query": 60,

    # 投递限速（令牌桶 + 每日上限）。投递必须慢，平台每日沟通上限约 150
    "apply_rate": {
        "min_interval": 1.0,    # 两次投递最小间隔(秒)
        "tokens_per_sec": 0.5, # ≈ 每 2 秒 1 个
        "daily_cap": 130,      # 每日沟通上限（留余量，避免触发风控）
    },

    # 中央去重库路径（相对 boss_auto_apply/data，与飞轮数据同目录）
    "dedup_db": "data/dedup.db",

    # 是否复用飞轮 store 的 labels.json（已投/已过滤的职位不再重复处理）
    "use_flywheel_store": True,
}

# ====== 真实 Embedding 配置 ======
# use_real_embedding=True  -> 优先用本地句向量模型（语义召回，比 n-gram 准很多）
#                           -> 模型未安装/加载失败时才回退 n-gram，并明确告警
# use_real_embedding=False -> 强制只用 n-gram（纯离线、零依赖、但语义弱）
#
# 中文场景推荐 bge-small-zh-v1.5（体积小、中文语义强）；
# 若需要中英混合，可改 paraphrase-multilingual-MiniLM-L12-v2。
EMBEDDING_CONFIG = {
    "use_real_embedding": True,
    # 首次使用会从 HuggingFace 下载到 cache_dir（约 130MB），之后完全离线
    "model_name": "BAAI/bge-small-zh-v1.5",
    "cache_dir": "data/embed_cache",   # 相对 boss_auto_apply 目录，模型与索引都缓存在这里
    "device": "auto",                  # "auto" -> 有 GPU 用 GPU，否则 CPU
    # 仅用于调试：True 时即使有模型也强制走 n-gram
    "force_fallback": False,
}
