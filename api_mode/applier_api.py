# 限速投递 —— 令牌桶限速，遵守平台每日沟通上限
#
# 投递不宜并发（平台有每日上限且风控严格），故顺序执行 + 速率限制。
# 每日上限由 pipeline 对照 dedup.today_count() 统一控制。

import time
import logging

logger = logging.getLogger("boss_api")


class RateLimiter:
    def __init__(self, min_interval=1.0, tokens_per_sec=0.5, daily_cap=130):
        self.min_interval = min_interval
        self.tokens_per_sec = tokens_per_sec
        self.daily_cap = daily_cap
        self._last = 0.0

    def acquire(self):
        now = time.time()
        wait = self.min_interval - (now - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()


class ApplyRunner:
    def __init__(self, apply_client, rate=None):
        r = rate or {}
        self.client = apply_client
        self.limiter = RateLimiter(
            min_interval=r.get("min_interval", 1.0),
            tokens_per_sec=r.get("tokens_per_sec", 0.5),
            daily_cap=r.get("daily_cap", 130),
        )

    def apply_one(self, job, stop_event=None):
        if stop_event is not None and stop_event.is_set():
            return False
        self.limiter.acquire()
        if stop_event is not None and stop_event.is_set():
            return False
        try:
            ok = self.client.apply(job)
        except Exception as e:
            logger.warning("apply 异常: %s", e)
            ok = False
        return bool(ok)
