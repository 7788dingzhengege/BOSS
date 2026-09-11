# 简历-JD 匹配分析模块
# 使用 DeepSeek 对比简历与 JD，输出匹配度报告

import os
import json
import logging

logger = logging.getLogger("boss_applier")

_SYSTEM_PROMPT = """你是一个专业的简历匹配分析助手。你的任务是对比求职者简历和招聘 JD，输出详细的匹配度报告。

## 输出格式（严格 JSON，不要 markdown 代码块）
{
  "overall_score": <0-100 整数，总体匹配度>,
  "skill_match": {
    "matched": ["JD要求且简历具备的技能"],
    "missing": ["JD要求但简历未体现的技能"],
    "extra": ["简历有但JD未要求的技能"]
  },
  "experience_match": {
    "score": <0-100>,
    "analysis": "经验匹配分析"
  },
  "education_match": {
    "score": <0-100>,
    "analysis": "学历匹配分析"
  },
  "strengths": ["简历中与该JD匹配的亮点"],
  "weaknesses": ["简历中与该JD不匹配的短板"],
  "keywords_to_add": ["建议在简历中补充的JD关键词"]
}

评分标准：
- 90-100：高度匹配
- 70-89：较匹配
- 50-69：部分匹配
- 0-49：不匹配"""


class ResumeMatcher:
    """简历-JD 匹配分析器"""

    def __init__(self, agent_config):
        """
        :param agent_config: AGENT_FILTER_CONFIG 字典（复用 DeepSeek 配置）
        """
        self.config = agent_config
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client

        api_key = os.environ.get(self.config.get("api_key_env", "DEEPSEEK_API_KEY"), "")
        if not api_key:
            raise ValueError(f"未找到 API Key，请设置环境变量 {self.config.get('api_key_env')}")

        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("未安装 openai 库，请运行: pip install openai")

        self._client = OpenAI(
            api_key=api_key,
            base_url=self.config.get("api_base", "https://api.deepseek.com/v1"),
            timeout=30,
        )
        return self._client

    def match(self, resume_text, jd_text, job_info=None):
        """
        分析简历与 JD 的匹配度

        :param resume_text: 简历全文
        :param jd_text: JD 全文
        :param job_info: 职位信息 dict（可选，提供更多上下文）
        :return: dict 匹配报告
        """
        if not resume_text or not jd_text:
            logger.warning("简历或JD为空，跳过匹配分析")
            return None

        client = self._get_client()

        user_msg_parts = ["## 简历内容：", resume_text[:3000], "", "## 招聘JD："]
        if job_info:
            user_msg_parts.append(f"职位：{job_info.get('name', '')} | 公司：{job_info.get('company', '')}")
        user_msg_parts.append(jd_text[:2000])

        user_msg = "\n".join(user_msg_parts)

        try:
            response = client.chat.completions.create(
                model=self.config.get("model", "deepseek-chat"),
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.1,
                max_tokens=1500,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content.strip()
            result = json.loads(content)

            logger.info("[简历匹配] 总分=%d 技能匹配=%d 缺失技能=%s",
                        result.get("overall_score", 0),
                        len(result.get("skill_match", {}).get("matched", [])),
                        result.get("skill_match", {}).get("missing", []))

            return result

        except json.JSONDecodeError:
            logger.warning("匹配分析返回非 JSON 格式")
            return None
        except Exception:
            logger.exception("简历匹配分析异常")
            return None
