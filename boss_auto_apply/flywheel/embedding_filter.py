# RAG 召回: n-gram 相似度 + 飞轮历史投票
# 简化版 RAG: 无 Embedding 模型依赖, 用字符 n-gram 模拟语义相似度
# 召回 Top-K 相似历史已标注职位, 按相似度加权投票决定是否投递

import math
from collections import Counter
from . import store


def _trigrams(text: str) -> set:
    """字符 n-gram (3-gram), 模拟 Embedding 效果"""
    text = (text or "").strip()
    if len(text) < 3:
        return {text} if text else set()
    return {text[i:i + 3] for i in range(len(text) - 2)}


def ngram_similarity(a: str, b: str) -> float:
    """n-gram 余弦相似度"""
    ga, gb = _trigrams(a), _trigrams(b)
    if not ga or not gb:
        return 0.0
    inter = len(ga & gb)
    return inter / math.sqrt(len(ga) * len(gb))


def jaccard(a: str, b: str) -> float:
    """Jaccard 相似度 (备选)"""
    sa, sb = set(a or ""), set(b or "")
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def retrieve_similar_jobs(job_text: str, top_k: int = 5, threshold: float = 0.2):
    """
    召回与目标职位最相似的历史已标注职位
    :param job_text: 目标职位文本 (job_name + 关键词 + 公司等)
    :param top_k: 召回前 K 个
    :param threshold: 相似度阈值
    :return: [(job_dict, similarity), ...]
    """
    labeled = store.get_labeled()
    if not labeled:
        return []

    scored = []
    for j in labeled:
        # 用职位名 + 命中关键词拼接作为检索文本
        text_parts = [j.get("job_name", "")]
        if j.get("hit_keyword"):
            text_parts.append(j["hit_keyword"])
        if j.get("company"):
            text_parts.append(j["company"])
        text = " ".join(text_parts)

        sim = ngram_similarity(job_text, text)
        if sim >= threshold:
            scored.append((j, sim))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def vote_by_history(job_text: str, top_k: int = 5, threshold: float = 0.2):
    """
    根据历史标注投票决定是否投递
    :return: (action, confidence, details)
      action: "apply" | "exclude" | "unsure"
      confidence: 0~1
      details: 召回的相似职位列表 [(job, sim), ...]
    """
    similar = retrieve_similar_jobs(job_text, top_k, threshold)
    if not similar:
        return "unsure", 0.0, []

    # 按相似度加权投票
    accept_score, reject_score = 0.0, 0.0
    for job, sim in similar:
        weight = sim
        if job.get("label") == "accepted":
            accept_score += weight
        elif job.get("label") == "rejected":
            reject_score += weight

    total = accept_score + reject_score
    if total == 0:
        return "unsure", 0.0, similar

    accept_ratio = accept_score / total
    # 置信度: 越极端越自信
    confidence = abs(accept_ratio - 0.5) * 2

    if accept_ratio > 0.6:
        return "apply", confidence, similar
    elif accept_ratio < 0.4:
        return "exclude", confidence, similar
    else:
        return "unsure", 1 - confidence, similar


def rag_filter(job_text: str, rag_config: dict = None):
    """
    RAG 召回统一入口 (供 applier 调用)
    :param job_text: 职位文本
    :param rag_config: 配置 {enabled, top_k, threshold, accept_threshold, reject_threshold}
    :return: (pass, reason)
      pass: True/False
      reason: 决策原因
    """
    if not rag_config or not rag_config.get("enabled", False):
        return True, "RAG未启用"

    top_k = rag_config.get("top_k", 5)
    threshold = rag_config.get("threshold", 0.2)
    accept_th = rag_config.get("accept_threshold", 0.6)
    reject_th = rag_config.get("reject_threshold", 0.4)
    conf_th = rag_config.get("confidence_threshold", 0.3)

    similar = retrieve_similar_jobs(job_text, top_k, threshold)
    if not similar:
        return True, "RAG: 无历史样本, 兜底通过"

    # 加权投票
    accept_score, reject_score = 0.0, 0.0
    for job, sim in similar:
        if job.get("label") == "accepted":
            accept_score += sim
        elif job.get("label") == "rejected":
            reject_score += sim

    total = accept_score + reject_score
    if total == 0:
        return True, "RAG: 无有效投票"

    accept_ratio = accept_score / total
    confidence = abs(accept_ratio - 0.5) * 2

    if accept_ratio >= accept_th and confidence >= conf_th:
        return True, f"RAG: {len(similar)}个相似样本中{accept_ratio:.0%}投过(置信{confidence:.0%})"
    elif accept_ratio <= reject_th and confidence >= conf_th:
        return False, f"RAG: {len(similar)}个相似样本中{(1-accept_ratio):.0%}投错(置信{confidence:.0%})"
    else:
        return True, f"RAG: 投票不确定({accept_ratio:.0%}), 兜底通过"
