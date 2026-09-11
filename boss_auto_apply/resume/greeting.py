# 智能打招呼语生成模块
# 根据简历内容 + JD要求，生成个性化的BOSS直聘打招呼语

import os
import json
import logging

logger = logging.getLogger("boss_applier")

_SYSTEM_PROMPT = """你是一个专业的求职沟通助手。你的任务是根据求职者的简历和目标JD，生成一段适合在BOSS直聘上发送的打招呼语。

## 要求
1. 打招呼语要简短有力，控制在80-150字以内
2. 突出与JD最匹配的2-3个核心技能或项目经验
3. 语气自然真诚，不要套模板的感觉
4. 可以适当表达对该公司/岗位的兴趣
5. 结尾可以加一句简单的互动引导（如"期待和您进一步沟通"）
6. 不要编造简历中没有的经历

## 输出格式（严格JSON）
{
  "greeting": "打招呼语正文",
  "highlights": ["本次突出的要点1", "本次突出的要点2"]
}"""


class GreetingGenerator:
    """打招呼语生成器"""

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

        from openai import OpenAI
        self._client = OpenAI(
            api_key=api_key,
            base_url=self.config.get("api_base", "https://api.deepseek.com/v1"),
            timeout=30,
        )
        return self._client

    def generate(self, resume_text, jd_text, job_info=None):
        """
        根据简历和JD生成打招呼语

        :param resume_text: 简历全文
        :param jd_text: JD全文
        :param job_info: 职位信息 dict（可选）
        :return: dict {"greeting": "...", "highlights": [...]}
        """
        if not resume_text or not jd_text:
            logger.warning("[打招呼] 简历或JD为空")
            return None

        client = self._get_client()

        user_parts = ["## 我的简历：", resume_text[:2500], "", "## 目标岗位JD："]
        if job_info:
            user_parts.append(f"职位：{job_info.get('name', '')} | 公司：{job_info.get('company', '')}")
        user_parts.append(jd_text[:1500])

        user_msg = "\n".join(user_parts)

        try:
            response = client.chat.completions.create(
                model=self.config.get("model", "deepseek-chat"),
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.7,
                max_tokens=500,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content.strip()
            result = json.loads(content)

            logger.info("[打招呼] 生成成功: %d字", len(result.get("greeting", "")))
            return result

        except json.JSONDecodeError:
            logger.warning("[打招呼] 返回非JSON格式")
            return None
        except Exception:
            logger.exception("[打招呼] 生成异常")
            return None
