# 编排管线：fetch → dedup → 三层过滤(关键词 / RAG / Agent) → 限速apply → 记录 → 飞轮
#
# 复用 boss_auto_apply 的：
#   - flywheel.decision  （关键词排除 / 白名单）
#   - flywheel.store      （标注数据持久化，与旧模式共享 labels.json）
#   - flywheel.metrics    （轮次指标）
#   - agent_filter        （DeepSeek Agent 深度筛选）
# 新增：
#   - dedup.DedupStore    （原子去重，不重复投递）
#   - embed_rag.EmbedRAG  （本地 embedding RAG）
#   - fetcher / applier_api（并发抓取 / 限速投递）

import logging
import threading
from datetime import datetime

from flywheel import decision, store, metrics
from config import JOB_SEEKER_PROFILE, AGENT_FILTER_CONFIG, RAG_CONFIG

import agent_filter
import dedup
import embed_rag
import fetcher
import applier_api
import config_api
import api_client

logger = logging.getLogger("boss_api")


class Pipeline:
    def __init__(self):
        self.stop_event = threading.Event()
        self.running = False
        self.applied = 0
        self.excluded = 0
        self.cfg = None

    def run(self, cfg, on_status=None, use_mock=False,
             token=None, e2mf_token=None, base_url=None):
        self.stop_event.clear()
        self.running = True
        self.applied = 0
        self.excluded = 0
        self.cfg = cfg
        try:
            self._run(cfg, on_status, use_mock, token, e2mf_token, base_url)
        finally:
            self.running = False

    def _run(self, cfg, on_status, use_mock, token, e2mf_token, base_url):
        api = config_api.API_CONFIG
        dd = dedup.DedupStore(api["dedup_db"])
        on_status and on_status("初始化中...")

        # 1. 客户端（Mock 或你的 User* 实现）。token 来自 GUI 输入或环境变量
        job_source, apply_client = api_client.build_clients(
            use_mock=use_mock, token=token, e2mf_token=e2mf_token,
            base_url=base_url, token_env=api["token_env"]
        )

        # 2. 已处理过的 job_id（避免重复处理 / 投递）
        seen = set()
        for j in store.get_labeled():
            seen.add(j.get("job_id"))

        # 3. RAG 拟合历史标注
        rag = embed_rag.EmbedRAG(RAG_CONFIG, config_api.EMBEDDING_CONFIG)
        if cfg.get("rag_enabled", True):
            rag.fit()

        # 4. Agent（DeepSeek 深度筛选，按需触发）
        agent = None
        if cfg.get("agent_filter", False):
            agent = agent_filter.JobFilterAgent(AGENT_FILTER_CONFIG, JOB_SEEKER_PROFILE)

        # 5. 并发抓取
        on_status and on_status(f"并发抓取中（{cfg.get('fetch_workers', api['fetch_workers'])} 线程）...")
        jobs = fetcher.fetch_all(
            job_source,
            cfg["keywords"],
            [cfg["city_code"]],
            cfg.get("scales", []),
            cfg.get("internship_only", True),
            api["max_results_per_query"],
            workers=cfg.get("fetch_workers", api["fetch_workers"]),
        )
        on_status and on_status(f"抓到 {len(jobs)} 个职位，开始过滤 + 投递")

        # 6. 限速投递器（整个循环共用一个，保证速率连续）
        runner = applier_api.ApplyRunner(apply_client, api["apply_rate"])
        daily_cap = api["apply_rate"]["daily_cap"]
        run_id = datetime.now().strftime("api-%Y%m%d-%H%M%S")

        for job in jobs:
            if self.stop_event.is_set():
                on_status and on_status("已终止")
                break

            jid = job.get("job_id")
            if not jid or jid in seen:
                continue

            name = job.get("name", "")
            company = job.get("company", "")

            # ---- 第一层：关键词排除（合并 GUI 排除 + 飞轮规则）----
            d = decision.decide(name, company, cfg.get("exclude_keywords", []))
            if d["decision"] == "exclude":
                store.add_pending(jid, name, company, job.get("salary", ""), "excluded", d["hit_keyword"], run_id)
                self.excluded += 1
                seen.add(jid)
                continue

            # ---- 第二层：本地 embedding RAG 投票 ----
            if cfg.get("rag_enabled", True):
                text = f"{name} {company} {job.get('salary', '')} {job.get('jd', '')}"
                passed, reason = rag.vote(text)
                if not passed:
                    store.add_pending(jid, name, company, job.get("salary", ""), "excluded", "RAG", run_id)
                    self.excluded += 1
                    seen.add(jid)
                    continue

            # ---- 第三层：Agent 深度筛选（仅在不确定时触发）----
            if agent is not None:
                info = {"name": name, "company": company, "salary": job.get("salary", "")}
                if agent.should_trigger(info):
                    passed, reason, score = agent.analyze(info, job.get("jd", ""))
                    if not passed:
                        store.add_pending(jid, name, company, job.get("salary", ""), "excluded", "Agent", run_id)
                        self.excluded += 1
                        seen.add(jid)
                        continue

            # ---- 原子去重预约（多线程安全，永不重复投递）----
            if not dd.try_reserve(jid, name, company, job.get("salary", ""), run_id):
                seen.add(jid)
                continue

            # ---- 限速投递 ----
            ok = runner.apply_one(job, self.stop_event)
            if ok:
                store.add_pending(jid, name, company, job.get("salary", ""), "applied", "", run_id)
                dd.mark_applied(jid)
                self.applied += 1
                if self.applied >= daily_cap:
                    on_status and on_status(f"已达每日上限 {self.applied}，停止")
                    break
            else:
                dd.release(jid)

            on_status and on_status(
                f"已投 {self.applied} | 过滤 {self.excluded} | 今日累计 {dd.today_count()}"
            )

        # 记录本轮（标注后才有 G 值；这里仅占位，标注完在 GUI 里重算）
        if self.applied + self.excluded > 0:
            try:
                metrics.compute_run_metrics(run_id)
            except Exception:
                pass

        on_status and on_status(f"完成：投递 {self.applied}，过滤 {self.excluded}")
