# 本地 embedding RAG（真实句向量，离线、可缓存）
#
# 默认优先用本地句向量模型（sentence-transformers）把职位编码成稠密向量，
# 语义相近的岗位在向量空间里也相近 —— 能识别“同义不同字”的岗位，比 n-gram 准很多。
# 模型只需首次联网下载一次（约 130MB），之后完全离线运行，不耗 API、不经网络。
#
# 若模型未安装或加载失败，明确告警并回退到 n-gram 向量（绝不静默假装用了 embedding）。
#
# 投票阈值沿用 config.RAG_CONFIG（accept_threshold / reject_threshold / confidence_threshold），
# 与旧模式完全一致。

import os
import math
import logging
import hashlib
import pickle
from collections import Counter

from flywheel import store

logger = logging.getLogger("boss_api")

# bge 系列建议给 query 加前缀，检索效果更稳
_BGE_QUERY_PREFIX = "为这个句子生成表示以用于检索："

# n-gram 回退时的最小文本长度
_NGRAM_MIN = 2


def _char_ngrams(text, n=3):
    text = (text or "").strip()
    if len(text) < n:
        return {text} if text else set()
    return {text[i:i + n] for i in range(len(text) - n + 1)}


class LocalEmbedder:
    """句向量编码器：真实 embedding 优先，n-gram 兜底。"""

    def __init__(self, embedding_config=None):
        ec = embedding_config or {"use_real_embedding": True,
                                  "model_name": "BAAI/bge-small-zh-v1.5",
                                  "cache_dir": "data/embed_cache",
                                  "device": "auto",
                                  "force_fallback": False}
        self.use_real = ec.get("use_real_embedding", True)
        self.model_name = ec.get("model_name", "BAAI/bge-small-zh-v1.5")
        self.cache_dir = ec.get("cache_dir", "data/embed_cache")
        self.device = ec.get("device", "auto")
        self.force_fallback = ec.get("force_fallback", False)

        self.use_st = False
        self.model = None
        self.fell_back = False

        if self.use_real and not self.force_fallback:
            self._try_load_st()
        if not self.use_st:
            self.fell_back = True
            if self.use_real:
                logger.warning(
                    "EmbedRAG: 真实 embedding 不可用，已回退 n-gram（语义召回会变弱）。"
                    "安装：pip install sentence-transformers"
                )
            else:
                logger.info("EmbedRAG: 按配置强制使用 n-gram 向量")

    def _try_load_st(self):
        try:
            from sentence_transformers import SentenceTransformer
            os.makedirs(self.cache_dir, exist_ok=True)
            # SentenceTransformer 不接受 "auto"，翻译为 None（自动选 cuda/cpu）
            dev = self.device
            if dev == "auto":
                dev = None
            self.model = SentenceTransformer(self.model_name, cache_folder=self.cache_dir, device=dev)
            self.use_st = True
            dim = self.model.get_sentence_embedding_dimension()
            logger.info("EmbedRAG: 已加载真实句向量模型 %s (维度 %d)", self.model_name, dim)
        except Exception as e:
            logger.warning("EmbedRAG: 加载句向量模型失败 (%s)，回退 n-gram", e)

    def encode(self, text, is_query=False):
        """编码单条文本。is_query=True 时给 bge 模型加检索前缀。"""
        if self.use_st and self.model is not None:
            t = text or ""
            if is_query and t and self.model_name.lower().startswith("bge"):
                t = _BGE_QUERY_PREFIX + t
            # normalize_embeddings=True -> 余弦相似度 = 向量点积
            vec = self.model.encode([t], normalize_embeddings=True,
                                    convert_to_numpy=True, device=self.device)
            return vec[0]
        # n-gram 兜底
        grams = _char_ngrams(text, 3) | _char_ngrams(text, 2)
        if not grams:
            return {}
        vec = Counter(grams)
        norm = math.sqrt(sum(v * v for v in vec.values()))
        return {g: v / norm for g, v in vec.items()} if norm else {}

    @staticmethod
    def cosine(a, b):
        # n-gram 字典分支
        if isinstance(a, dict) and isinstance(b, dict):
            keys = set(a) | set(b)
            dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
            na = math.sqrt(sum(v * v for v in a.values()))
            nb = math.sqrt(sum(v * v for v in b.values()))
            return dot / (na * nb) if na and nb else 0.0
        # 稠密向量（numpy）分支
        try:
            import numpy as np
            a = np.asarray(a, dtype=float)
            b = np.asarray(b, dtype=float)
            na = np.linalg.norm(a)
            nb = np.linalg.norm(b)
            return float(np.dot(a, b) / (na * nb)) if na and nb else 0.0
        except Exception:
            return 0.0


class EmbedRAG:
    def __init__(self, rag_config=None, embedding_config=None):
        self.cfg = rag_config or {
            "enabled": True, "top_k": 5, "threshold": 0.2,
            "accept_threshold": 0.6, "reject_threshold": 0.4, "confidence_threshold": 0.3,
        }
        self.ec = embedding_config or {"use_real_embedding": True,
                                       "model_name": "BAAI/bge-small-zh-v1.5",
                                       "cache_dir": "data/embed_cache",
                                       "device": "auto", "force_fallback": False}
        self.embedder = LocalEmbedder(self.ec)
        self._cache = {}        # job_id -> (vector, label)
        self._index_file = None
        self._build_index_path()

    def _build_index_path(self):
        cd = self.ec.get("cache_dir", "data/embed_cache")
        os.makedirs(cd, exist_ok=True)
        sig = self._signature()
        self._index_file = os.path.join(cd, f"rag_index_{sig}.pkl")

    def _signature(self):
        """索引缓存签名：模型名 + 是否真实 embedding + 标注内容指纹。"""
        try:
            labeled = store.get_labeled()
            raw = repr([(j.get("job_id"), j.get("label"), j.get("job_name"))
                        for j in labeled]).encode("utf-8")
            fp = hashlib.md5(raw).hexdigest()[:10]
            n = len(labeled)
        except Exception:
            fp, n = "none", 0
        kind = "st" if self.embedder.use_st else "ngram"
        return f"{kind}_{self.ec.get('model_name','x').replace('/','_')}_{n}_{fp}"

    def fit(self):
        """把已标注历史编码成向量缓存（命中磁盘缓存则跳过编码）。"""
        self._cache = {}
        # 优先从磁盘加载已编码索引
        if self._index_file and os.path.exists(self._index_file):
            try:
                with open(self._index_file, "rb") as f:
                    self._cache = pickle.load(f)
                logger.info("EmbedRAG: 从磁盘缓存加载 %d 条历史向量", len(self._cache))
                return
            except Exception as e:
                logger.warning("EmbedRAG: 索引缓存读取失败(%s)，重新编码", e)

        for j in store.get_labeled():
            text = self._job_text(j)
            self._cache[j.get("job_id")] = (self.embedder.encode(text), j.get("label"))
        logger.info("EmbedRAG: 拟合 %d 条历史标注", len(self._cache))

        # 落盘缓存，下次启动秒开
        if self._index_file:
            try:
                with open(self._index_file, "wb") as f:
                    pickle.dump(self._cache, f)
                logger.info("EmbedRAG: 历史向量已缓存到 %s", self._index_file)
            except Exception as e:
                logger.warning("EmbedRAG: 索引缓存写入失败(%s)", e)

    def _job_text(self, job):
        parts = [job.get("job_name", "")]
        if job.get("hit_keyword"):
            parts.append(job["hit_keyword"])
        if job.get("company"):
            parts.append(job["company"])
        if job.get("description"):
            parts.append(job["description"][:200])
        return " ".join(parts)

    def vote(self, job_text):
        """
        返回 (pass: bool, reason: str)
        沿用 embedding_filter 的加权投票语义：
          accept_ratio >= accept_threshold 且置信度 >= 阈值 -> 投
          accept_ratio <= reject_threshold 且置信度 >= 阈值 -> 不投
          否则 -> 兜底通过（交给 Agent 或人工）
        """
        if not self.cfg.get("enabled"):
            return True, "RAG未启用"
        if not self._cache:
            return True, "RAG: 无历史样本, 兜底通过"

        q = self.embedder.encode(job_text, is_query=True)
        scored = []
        for _jid, (vec, label) in self._cache.items():
            sim = LocalEmbedder.cosine(q, vec)
            if sim >= self.cfg.get("threshold", 0.2):
                scored.append((label, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[: self.cfg.get("top_k", 5)]
        if not top:
            return True, "RAG: 无相似样本, 兜底通过"

        acc = sum(s for l, s in top if l == "accepted")
        rej = sum(s for l, s in top if l == "rejected")
        tot = acc + rej
        if tot == 0:
            return True, "RAG: 无有效投票"

        ratio = acc / tot
        conf = abs(ratio - 0.5) * 2
        at = self.cfg.get("accept_threshold", 0.6)
        rt = self.cfg.get("reject_threshold", 0.4)
        ct = self.cfg.get("confidence_threshold", 0.3)

        if ratio >= at and conf >= ct:
            return True, f"RAG: {len(top)}个相似样本中{ratio:.0%}投过(置信{conf:.0%})"
        if ratio <= rt and conf >= ct:
            return False, f"RAG: {len(top)}个相似样本中{(1 - ratio):.0%}投错(置信{conf:.0%})"
        return True, f"RAG: 投票不确定({ratio:.0%}), 兜底通过"
