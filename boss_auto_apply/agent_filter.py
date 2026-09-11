# AI Agent 智能筛选模块
# 基于求职者画像，使用 DeepSeek（OpenAI 兼容接口）对 JD 深度分析

import os
import json
import logging

logger = logging.getLogger("boss_applier")

# 系统提示词：定义 Agent 的角色和输出格式
_SYSTEM_PROMPT = """你是一个专业的求职筛选助手。你的任务是根据求职者的画像，分析招聘 JD 的匹配度。

## 求职者画像
{profile}

## 你的输出要求
仔细阅读 JD 内容，从以下维度评估匹配度：
1. 岗位方向是否匹配（目标角色）
2. 技能要求是否匹配（求职者技能 vs JD 要求）
3. 经验要求是否匹配
4. 学历要求是否满足
5. 是否命中求职者的回避项（如纯销售、外包、培训公司等）
6. 行业是否属于偏好范围

## 输出格式（严格 JSON，不要 markdown 代码块）
{{
  "score": <0-100的整数，匹配度评分>,
  "passed": <true/false，是否建议投递>,
  "reason": "<一句话说明理由，中文>",
  "matched_skills": ["匹配的核心技能"],
  "concerns": ["潜在顾虑或风险点"]
}}

评分标准：
- 90-100：高度匹配，强烈建议投递
- 70-89：较匹配，建议投递
- 50-69：部分匹配，可投可不投
- 0-49：不匹配，不建议投递

注意：如果 JD 含有培训收费、培训贷、纯销售等求职者回避的特征，score 应低于 30。"""


class JobFilterAgent:
    """基于大模型的职位智能筛选 Agent"""

    def __init__(self, config, profile):
        """
        :param config: AGENT_FILTER_CONFIG 字典
        :param profile: JOB_SEEKER_PROFILE 字典
        """
        self.config = config
        self.profile = profile
        self._client = None
        self._system_prompt = _SYSTEM_PROMPT.format(profile=self._format_profile(profile))

    def _format_profile(self, profile):
        """将画像字典格式化为可读文本"""
        lines = []
        lines.append(f"- 目标角色: {', '.join(profile.get('target_roles', []))}")
        lines.append(f"- 核心技能: {', '.join(profile.get('skills', []))}")
        lines.append(f"- 经验阶段: {profile.get('experience', '不限')}")
        lines.append(f"- 学历: {profile.get('education', '不限')}")
        lines.append(f"- 偏好行业: {', '.join(profile.get('preferred_industries', []))}")
        lines.append(f"- 回避项: {', '.join(profile.get('avoid', []))}")
        lines.append(f"- 其他偏好: {profile.get('preferences', '无')}")
        return "\n".join(lines)

    def _get_client(self):
        """延迟初始化 OpenAI 兼容客户端"""
        if self._client is not None:
            return self._client

        api_key = os.environ.get(self.config.get("api_key_env", "DEEPSEEK_API_KEY"), "")
        if not api_key:
            raise ValueError(
                f"未找到 API Key，请在环境变量中设置 {self.config.get('api_key_env')}。"
                f"DeepSeek API Key 获取：https://platform.deepseek.com/api_keys"
            )

        # 使用 openai 库（兼容 DeepSeek 接口）
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "未安装 openai 库，请运行: pip install openai"
            )

        self._client = OpenAI(
            api_key=api_key,
            base_url=self.config.get("api_base", "https://api.deepseek.com/v1"),
            timeout=self.config.get("timeout", 15),
        )
        return self._client

    def analyze(self, job_info, jd_text):
        """
        分析单个职位的匹配度

        :param job_info: dict，包含 name, company, salary 等
        :param jd_text: str，JD 全文
        :return: (passed: bool, reason: str, score: int)
        """
        if not jd_text or len(jd_text.strip()) < 20:
            # JD 太短无法分析，默认通过（交给规则层处理）
            logger.info("JD 内容过短，跳过 Agent 分析")
            return True, "JD内容不足，默认通过", -1

        # 构造用户消息
        user_msg = self._build_user_message(job_info, jd_text)

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.config.get("model", "deepseek-chat"),
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.1,  # 低温度保证稳定性
                max_tokens=500,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content.strip()
            result = json.loads(content)

            score = result.get("score", 0)
            passed = result.get("passed", False)
            reason = result.get("reason", "未知原因")
            concerns = result.get("concerns", [])

            min_score = self.config.get("min_score", 60)
            # 分数低于阈值也拒绝
            if score < min_score:
                passed = False

            log_msg = f"Agent评分={score} 通过={passed} 理由={reason}"
            if concerns:
                log_msg += f" 顾虑={concerns}"
            logger.info(log_msg)

            return passed, reason, score

        except json.JSONDecodeError:
            logger.warning("Agent 返回非 JSON 格式，保守跳过(不投递)")
            return False, "Agent返回格式异常，保守跳过", -1
        except Exception as e:
            logger.warning("Agent 调用异常: %s，保守跳过(不投递)", e)
            return False, f"Agent异常: {e}", -1

    def _build_user_message(self, job_info, jd_text):
        """构造发送给大模型的用户消息"""
        lines = [
            f"职位名称: {job_info.get('name', '未知')}",
            f"公司: {job_info.get('company', '未知')}",
            f"薪资: {job_info.get('salary', '未知')}",
            "",
            "JD 内容如下：",
            jd_text[:2000],  # 截断防止 token 超限
        ]
        return "\n".join(lines)

    def should_trigger(self, job_info):
        """
        判断是否需要触发 Agent（按需触发策略）

        :param job_info: 职位信息
        :return: True=需要调 Agent
        """
        trigger = self.config.get("trigger", "on_uncertain")

        if trigger == "always":
            return True

        # on_uncertain: 仅在"薪资面议/缺失"这种规则层无法判断方向时触发 Agent。
        # 其余情况由关键词排除 + 白名单在列表层处理，避免每个职位都调一次 LLM
        # （原逻辑对 工程师/专员/助理/运营/经理 或"标题不含技能词"都触发，
        #  导致 AI 实习岗几乎 100% 触发 Agent，既慢又受 API 抖动影响）。
        salary = job_info.get("salary", "")
        if "面议" in salary or not salary:
            return True
        return False
