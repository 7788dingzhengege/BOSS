# 并发抓取 —— 用线程池并行调用 JobSource.search（适配同步 HTTP 客户端，无需 aiohttp）
#
# FETCH 阶段可以高并发；APPLY 阶段由 applier_api 限速（平台每日沟通上限），二者解耦。

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger("boss_api")


def fetch_all(job_source, keywords, city_codes, scales, internship_only,
              max_results, workers=4):
    """
    对所有 (关键词 × 城市) 组合并发搜索，返回去重后的职位列表。
    去重键：job_id（平台稳定唯一 id）。
    """
    tasks = [(kw, cc) for kw in keywords for cc in city_codes]
    jobs = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {
            ex.submit(job_source.search, kw, cc, scales, internship_only, max_results): (kw, cc)
            for kw, cc in tasks
        }
        for fut in as_completed(futs):
            kw, cc = futs[fut]
            try:
                res = fut.result() or []
                for j in res:
                    jid = j.get("job_id")
                    if jid and jid not in jobs:
                        jobs[jid] = j
            except Exception as e:
                logger.warning("search 失败 kw=%s city=%s: %s", kw, cc, e)
    logger.info("fetch_all: 抓到 %d 个职位（%d 个查询）", len(jobs), len(tasks))
    return list(jobs.values())
