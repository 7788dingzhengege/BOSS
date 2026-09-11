# API 适配器层 —— 你只需要在这里填你的 token + 接口逻辑
#
# 这一层是「浏览器自动化」与「API 模式」之间的唯一边界：
#   - 本文件只定义抽象基类 JobSource / ApplyClient 和一个离线 Mock 实现；
#   - 你把真实的 search() / apply() 实现写在下面两个 User* 类里，接入你抓到的
#     endpoint + token（e2e / e2mf token）即可。
#
# 我不会在这里写任何逆向细节 / 签名算法 / 加密参数 —— 那些由你按自己的接口填。
#
# 合规提示：仅供本人账号与学习用途，遵守平台协议与相关法律法规。

import os
import time
import logging

logger = logging.getLogger("boss_api")


class JobSource:
    """职位抓取。子类实现 search()。"""

    def __init__(self, token: str, **kwargs):
        self.token = token
        self.kwargs = kwargs

    def search(self, keyword, city_code, scales=None, internship_only=True, max_results=60):
        """
        返回职位列表，每项至少包含：
            job_id  : 平台稳定的职位唯一 id（用于去重，必须稳定且唯一）
            name    : 职位名
            company : 公司名
            salary  : 薪资（字符串，可为空）
            jd      : JD 全文（可选，用于 Agent 深度筛选；没有则留空）
            url     : 职位链接（可选）
        """
        raise NotImplementedError(
            "请在 api_client.py 的 UserJobSource 中实现 search()，接入你的 token + 接口"
        )


class ApplyClient:
    """投递 / 打招呼。子类实现 apply()。"""

    def __init__(self, token: str, **kwargs):
        self.token = token
        self.kwargs = kwargs

    def apply(self, job: dict) -> bool:
        """对单个职位发起沟通/投递，返回是否成功。"""
        raise NotImplementedError(
            "请在 api_client.py 的 UserApplyClient 中实现 apply()，接入你的 token + 接口"
        )


class TokenAuth:
    """从环境变量读取 token，预留刷新钩子。"""

    def __init__(self, env_name: str = "BOSS_API_TOKEN"):
        self.env_name = env_name
        self._token = os.environ.get(env_name, "")

    @property
    def token(self):
        return self._token

    def refresh(self):
        # TODO: 若你的 token 会过期，在这里实现刷新（如用 refresh_token 换 access_token）
        self._token = os.environ.get(self.env_name, self._token)
        return self._token

    def is_ready(self) -> bool:
        return bool(self._token)


# =====================================================================
# 下面两个类由你实现（类名需与 config_api.API_CONFIG 中的一致）
# =====================================================================

class UserJobSource(JobSource):
    """你的职位抓取实现。把抓到的 endpoint + token 填进来。"""

    def search(self, keyword, city_code, scales=None, internship_only=True, max_results=60):
        # 伪代码骨架（请替换为你真实的请求逻辑）：
        #
        # import requests
        # headers = {"Authorization": f"Bearer {self.token}", ...}  # 按你的接口填
        # resp = requests.get(
        #     "你的搜索接口URL",
        #     params={"query": keyword, "city": city_code, "pageSize": max_results},
        #     headers=headers, timeout=15,
        # )
        # data = resp.json()
        # return [
        #     {
        #         "job_id": item["encryptedJobId"],   # 必须稳定唯一
        #         "name": item["jobName"],
        #         "company": item["brandName"],
        #         "salary": item.get("salaryDesc", ""),
        #         "jd": item.get("jobDescription", ""),
        #         "url": item.get("url", ""),
        #     }
        #     for item in data["zpData"]["jobList"]
        # ]
        raise NotImplementedError(
            "在 api_client.py 的 UserJobSource.search() 中接入你的 token + 接口"
        )


class UserApplyClient(ApplyClient):
    """你的投递/打招呼实现。"""

    def apply(self, job: dict) -> bool:
        # 伪代码骨架（请替换为你真实的请求逻辑）：
        #
        # import requests
        # headers = {"Authorization": f"Bearer {self.token}", ...}
        # resp = requests.post(
        #     "你的沟通/投递接口URL",
        #     json={"jobId": job["job_id"], ...},
        #     headers=headers, timeout=15,
        # )
        # return resp.status_code == 200 and resp.json().get("code") == 0
        raise NotImplementedError(
            "在 api_client.py 的 UserApplyClient.apply() 中接入你的 token + 接口"
        )


# =====================================================================
# 离线 Mock 实现（仅供静态验证管线，不调用任何真实接口）
# =====================================================================

class MockJobSource(JobSource):
    def search(self, keyword, city_code, scales=None, internship_only=True, max_results=60):
        jobs = []
        for i in range(min(max_results, 20)):
            jobs.append({
                "job_id": f"MOCK-{keyword}-{city_code}-{i}",
                "name": f"{keyword}实习生（Mock{i}）",
                "company": "Mock科技" if i % 2 == 0 else "示例网络",
                "salary": "200-300元/天",
                "jd": f"负责{keyword}相关工作，参与大模型应用落地。",
                "url": "",
            })
        return jobs


class MockApplyClient(ApplyClient):
    def apply(self, job: dict) -> bool:
        time.sleep(0.01)
        return True


def build_clients(use_mock: bool = False, token: str = None,
                  e2mf_token: str = None, base_url: str = None,
                  token_env: str = "BOSS_API_TOKEN"):
    """
    构造抓取/投递客户端。
    use_mock=True  -> 返回 Mock 实现（用于验证管线，不触网）。
    use_mock=False -> 动态加载本模块中的 UserJobSource / UserApplyClient。
        token       : e2e token（GUI 输入 / 环境变量），优先于环境变量
        e2mf_token  : e2mf token（可选，透传给 User* 实现的 kwargs）
        base_url    : 接口 base url（可选，透传给 User* 实现的 kwargs）
    透传的 e2mf_token / base_url 可在你的 UserJobSource / UserApplyClient 中
    通过 self.kwargs.get("e2mf_token") / self.kwargs.get("base_url") 读取。
    """
    if use_mock:
        return MockJobSource(token or ""), MockApplyClient(token or "")

    auth = TokenAuth(token_env)
    effective = token or auth.token
    kwargs = {}
    if base_url:
        kwargs["base_url"] = base_url
    if e2mf_token:
        kwargs["e2mf_token"] = e2mf_token

    mod = __import__("api_client", fromlist=["UserJobSource", "UserApplyClient"])
    src_cls = getattr(mod, "UserJobSource", None)
    apc_cls = getattr(mod, "UserApplyClient", None)
    if src_cls is None or apc_cls is None:
        raise RuntimeError(
            "未找到 UserJobSource / UserApplyClient，请在 api_client.py 中实现它们"
        )
    return src_cls(effective, **kwargs), apc_cls(effective, **kwargs)
