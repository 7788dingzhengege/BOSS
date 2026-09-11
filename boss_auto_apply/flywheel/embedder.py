# Embedding 语义相似度层 (基于 sentence-transformers)
# 开闭原则: 新增文件, 不修改 embedding_filter.py / applier.py 的策略逻辑
# 接口与 rag_filter 完全兼容, 可直接替换
#
# 使用:
#     from flywheel.embedder import embedding_filter
#     pass_filter, reason = embedding_filter(job_text, config)
#
# 安装:
#     pip install sentence-transformers -i https://pypi.tuna.tsinghua.edu.cn/simple
#
# 模型:
#     BAAI/bge-small-zh-v1.5 (~130MB, 中文语义最优, 体积小)
#     若需要中英混合可改回 paraphrase-multilingual-MiniLM-L12-v2
#     首次运行自动下载, 之后从本地缓存加载
#
# 国内镜像: 自动设置 HF_ENDPOINT=https://hf-mirror.com 解决 huggingface.co 超时

import os
import pickle
import hashlib
import logging
from . import store

logger = logging.getLogger("boss_embedder")

# bge 系列检索时给 query 加前缀, 效果更稳
_BGE_QUERY_PREFIX = "为这个句子生成表示以用于检索："

# ====== 国内镜像 (必须在 import sentence_transformers 之前设置) ======
# hf-mirror.com 是 HuggingFace 官方镜像, 国内访问速度快
# 若已手动设置 HF_ENDPOINT 环境变量则尊重用户配置
if not os.environ.get("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# ====== 路径 ======
DATA_DIR = "data"
CACHE_FILE = os.path.join(DATA_DIR, "embeddings_cache.pkl")

# ====== 默认配置 (与 RAG_CONFIG 兼容, 阈值适配 cosine 相似度) ======
# cosine 相似度范围 0~1, 语义高度相关通常 >0.6
# n-gram 相似度范围 0~1 但分布不同, 通常 0.1~0.3 就算相似
# 所以 similarity_threshold 默认 0.65, 远高于 n-gram 的 0.2
DEFAULT_CONFIG = {
    "enabled": True,                  # 总开关 (与 RAG_CONFIG.enabled 共用)
    "use_embedding": True,            # True=embedding, False=降级到 rag_filter
    "model_name": "BAAI/bge-small-zh-v1.5",
    "top_k": 5,                       # 召回相似职位数量
    "similarity_threshold": 0.65,     # cosine 相似度阈值, 低于此值不参与投票
    "accept_threshold": 0.6,          # accept 投票占比 >= 此值 → 放行
    "reject_threshold": 0.4,          # accept 投票占比 <= 此值 → 拦截
    "confidence_threshold": 0.3,      # 置信度 >= 此值才采纳投票结果
}

# ====== 全局状态 (懒加载) ======
_model = None                # SentenceTransformer 实例
_model_load_attempted = False  # 是否已尝试加载 (避免反复重试)
_cache = {}                  # job_id -> {"text_hash": str, "vector": np.ndarray}
_cache_loaded = False        # 是否已从磁盘加载缓存


def _text_hash(text):
    """文本哈希 (用于判断缓存是否过期)"""
    return hashlib.md5((text or "").encode("utf-8")).hexdigest()


def _get_model():
    """
    懒加载 sentence-transformers 模型
    首次调用时下载模型 (~130MB), 之后从本地缓存加载
    返回 None 表示不可用 (未安装/加载失败)
    """
    global _model, _model_load_attempted
    if _model is not None or _model_load_attempted:
        return _model
    _model_load_attempted = True
    try:
        from sentence_transformers import SentenceTransformer
        model_name = DEFAULT_CONFIG["model_name"]
        print(f"[Embedding] 加载模型 {model_name} (首次需下载~130MB, 请等待)...", flush=True)
        # device=None -> SentenceTransformer 自动选 cuda/cpu；绝不传 "auto"（非法值）
        _model = SentenceTransformer(model_name, device=None)
        # 兼容新旧版本方法名 (新版改名 get_embedding_dimension)
        dim_fn = getattr(_model, "get_embedding_dimension", None) or _model.get_sentence_embedding_dimension
        print(f"[Embedding] 模型加载完成, 维度={dim_fn()}", flush=True)
        logger.info("[Embedding] 真实句向量模型已加载: %s (维度 %d)", model_name, dim_fn())
        return _model
    except ImportError:
        msg = ("[Embedding] sentence-transformers 未安装 —— 语义过滤层将完全失效"
               "(所有职位无差别放行)。请安装: pip install sentence-transformers "
               "-i https://pypi.tuna.tsinghua.edu.cn/simple")
        print(msg, flush=True)
        logger.warning(msg)
        return None
    except Exception as e:
        msg = f"[Embedding] 模型加载失败: {e} —— 语义过滤层将失效(降级放行)"
        print(msg, flush=True)
        logger.warning(msg)
        return None


def _load_cache():
    """从磁盘加载 embedding 缓存 (仅首次调用时加载)"""
    global _cache_loaded, _cache
    if _cache_loaded:
        return
    _cache_loaded = True
    if not os.path.exists(CACHE_FILE):
        _cache = {}
        return
    try:
        with open(CACHE_FILE, "rb") as f:
            _cache = pickle.load(f)
        if not isinstance(_cache, dict):
            _cache = {}
    except Exception:
        _cache = {}


def _save_cache():
    """保存 embedding 缓存到磁盘"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(CACHE_FILE, "wb") as f:
            pickle.dump(_cache, f)
    except Exception:
        pass


def _embed_text(text, is_query=False):
    """
    单条文本 embedding
    返回归一化向量 (np.ndarray) 或 None
    normalize_embeddings=True → 向量 L2 范数=1, cosine 相似度 = 点积
    is_query=True 时给 bge 模型加检索前缀 (仅 query 加, corpus 不加)
    """
    model = _get_model()
    if model is None or not text:
        return None
    try:
        import numpy as np
        t = text
        if is_query and DEFAULT_CONFIG["model_name"].lower().startswith("bge"):
            t = _BGE_QUERY_PREFIX + t
        vec = model.encode(t, normalize_embeddings=True)
        return np.array(vec, dtype=np.float32)
    except Exception:
        return None


def _embed_cached(job_id, text):
    """
    带磁盘缓存的 embedding
    按 job_id + 文本哈希判断是否需要重新计算
    (职位文本不变时, embedding 永久有效)
    """
    _load_cache()
    h = _text_hash(text)
    cache_key = job_id if job_id else f"text_{h}"
    cached = _cache.get(cache_key)
    if cached and cached.get("text_hash") == h:
        return cached["vector"]
    # 缓存未命中, 重新计算
    vec = _embed_text(text)
    if vec is not None:
        _cache[cache_key] = {"text_hash": h, "vector": vec}
    return vec


def _get_job_text(job):
    """
    拼接职位的检索文本
    与 embedding_filter.py 保持一致: job_name + company (+ salary)
    """
    parts = [job.get("job_name", "")]
    if job.get("company"):
        parts.append(job["company"])
    if job.get("salary"):
        parts.append(job["salary"])
    return " ".join(parts)


def _cosine_sim(a, b):
    """余弦相似度 (向量已归一化, 等于点积)"""
    try:
        import numpy as np
        return float(np.dot(a, b))
    except Exception:
        return 0.0


def warmup():
    """
    预热: 批量计算所有已标注职位的 embedding
    首次运行时调用, 避免投递过程中逐条计算导致延迟
    后续新增标注后再次调用即可增量更新

    返回: 已缓存的职位数量
    """
    model = _get_model()
    if model is None:
        return 0

    labeled = store.get_labeled()
    if not labeled:
        print("[Embedding] 无已标注职位, 跳过预热", flush=True)
        return 0

    _load_cache()

    # 找出需要计算的 (不在缓存或文本已变更)
    to_compute = []
    for job in labeled:
        job_id = job.get("job_id", "")
        text = _get_job_text(job)
        h = _text_hash(text)
        cache_key = job_id if job_id else f"text_{h}"
        cached = _cache.get(cache_key)
        if not cached or cached.get("text_hash") != h:
            to_compute.append((cache_key, text, h))

    if not to_compute:
        print(f"[Embedding] 缓存已最新, 共 {len(labeled)} 个职位, 无需更新", flush=True)
        return len(labeled)

    # 批量 encode (比逐条快 10~50 倍)
    texts = [t for _, t, _ in to_compute]
    print(f"[Embedding] 批量计算 {len(to_compute)} 个新 embedding...", flush=True)
    try:
        import numpy as np
        vectors = model.encode(texts, batch_size=32, normalize_embeddings=True)
        for (cache_key, _, h), vec in zip(to_compute, vectors):
            _cache[cache_key] = {"text_hash": h, "vector": np.array(vec, dtype=np.float32)}
        _save_cache()
        print(f"[Embedding] 预热完成, 共缓存 {len(_cache)} 个职位 embedding", flush=True)
        return len(_cache)
    except Exception as e:
        print(f"[Embedding] 预热失败: {e}", flush=True)
        return len(_cache)


# ====== 异步预热 (标注后自动触发, 不阻塞 GUI) ======
import threading

_warmup_lock = threading.Lock()
_warmup_running = False


def async_warmup():
    """
    异步预热: 在后台线程执行 warmup, 不阻塞 GUI
    标注完成后自动调用, 增量更新新标注职位的 embedding
    若已有预热任务在跑则跳过 (避免并发)
    """
    global _warmup_running
    if _warmup_running:
        return  # 已有任务在跑, 跳过
    try:
        if not _warmup_lock.acquire(blocking=False):
            return  # 获取锁失败, 跳过
    except Exception:
        return

    def _run():
        global _warmup_running
        _warmup_running = True
        try:
            warmup()
        except Exception:
            pass
        finally:
            _warmup_running = False
            try:
                _warmup_lock.release()
            except Exception:
                pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def retrieve_similar_jobs(job_text, top_k=5, threshold=0.65):
    """
    用 embedding 召回与目标职位最相似的历史已标注职位
    (替代 embedding_filter.py 的 n-gram 版本)

    :param job_text: 目标职位文本 (job_name + company 等)
    :param top_k: 召回前 K 个
    :param threshold: cosine 相似度阈值 (默认 0.65)
    :return: [(job_dict, similarity), ...] 按相似度降序
    """
    model = _get_model()
    if model is None:
        return []

    labeled = store.get_labeled()
    if not labeled:
        return []

    # 查询向量 (新职位, 不缓存 — 每次都是新职位)；is_query=True 加 bge 检索前缀
    query_vec = _embed_text(job_text, is_query=True)
    if query_vec is None:
        return []

    # 遍历已标注职位, 用缓存加速
    cache_before = len(_cache)
    scored = []
    for job in labeled:
        job_id = job.get("job_id", "")
        text = _get_job_text(job)
        job_vec = _embed_cached(job_id, text)
        if job_vec is None:
            continue
        sim = _cosine_sim(query_vec, job_vec)
        if sim >= threshold:
            scored.append((job, sim))

    # 有新计算的 embedding 则保存缓存
    if len(_cache) > cache_before:
        _save_cache()

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def embedding_filter(job_text, config=None):
    """
    Embedding 语义过滤入口 (与 rag_filter 同签名, 可直接替换)

    工作流程:
    1. 将 job_text 转为 embedding 向量
    2. 从历史已标注职位中召回 top_k 个最相似的 (cosine 相似度 > threshold)
    3. 按相似度加权投票: accepted(投对) vs rejected(投错/该排)
    4. accept 占比 >= accept_threshold → 放行
       accept 占比 <= reject_threshold → 拦截
       其他 → 兜底放行 (不误杀)

    :param job_text: 职位文本 (job_name + company 等)
    :param config: 配置 dict (兼容 RAG_CONFIG, 额外支持 use_embedding / similarity_threshold)
    :return: (pass, reason)
      pass: True=放行, False=拦截
      reason: 决策原因 (含相似样本数和投票比例)
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}

    if not cfg.get("enabled", False):
        return True, "Embedding未启用"

    if not cfg.get("use_embedding", True):
        return True, "Embedding未启用(use_embedding=False)"

    model = _get_model()
    if model is None:
        # 降级: 模型不可用时兜底通过, 不影响投递流程 —— 但语义层已失效, 必须告警
        logger.warning(
            "[Embedding] 模型不可用, 语义过滤层失效(所有职位无差别放行)。"
            "安装: pip install sentence-transformers -i https://pypi.tuna.tsinghua.edu.cn/simple"
        )
        return True, "Embedding: 模型未安装, 语义过滤失效→兜底通过(请安装 sentence-transformers)"

    top_k = cfg.get("top_k", 5)
    threshold = cfg.get("similarity_threshold", 0.65)
    accept_th = cfg.get("accept_threshold", 0.6)
    reject_th = cfg.get("reject_threshold", 0.4)
    conf_th = cfg.get("confidence_threshold", 0.3)

    similar = retrieve_similar_jobs(job_text, top_k, threshold)
    if not similar:
        return True, "Embedding: 无相似样本(冷启动), 兜底通过"

    # 加权投票 (与 rag_filter 逻辑一致, 仅相似度算法不同)
    accept_score, reject_score = 0.0, 0.0
    for job, sim in similar:
        if job.get("label") == "accepted":
            accept_score += sim
        elif job.get("label") == "rejected":
            reject_score += sim

    total = accept_score + reject_score
    if total == 0:
        return True, "Embedding: 无有效投票(样本未标注)"

    accept_ratio = accept_score / total
    confidence = abs(accept_ratio - 0.5) * 2

    if accept_ratio >= accept_th and confidence >= conf_th:
        return True, f"Embedding: {len(similar)}个相似样本中{accept_ratio:.0%}投过(置信{confidence:.0%})"
    elif accept_ratio <= reject_th and confidence >= conf_th:
        return False, f"Embedding: {len(similar)}个相似样本中{(1-accept_ratio):.0%}投错(置信{confidence:.0%})"
    else:
        return True, f"Embedding: 投票不确定({accept_ratio:.0%}), 兜底通过"
