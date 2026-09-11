# 简历优化建议模块
# 基于匹配分析结果，生成具体的简历修改建议

import os
import json
import logging

logger = logging.getLogger("boss_applier")

_SYSTEM_PROMPT = """你是一个专业的简历优化顾问。你的任务是根据 JD 和匹配分析结果，生成具体的简历修改建议。

## 修改原则
1. 只建议修改，不编造经历
2. 优先突出与 JD 匹配的经历和技能
3. 建议补充 JD 中的关键词到简历合适位置
4. 建议调整经历描述的措辞，使其更贴合 JD
5. 不建议修改真实信息（学历、公司名、时间等）

## 输出格式（严格 JSON，不要 markdown 代码块）
{
  "modifications": [
    {
      "section": "修改的简历段落（如'专业技能'、'项目经历'）",
      "action": "add|modify|reorder|highlight",
      "original": "原文内容（modify时提供）",
      "suggested": "建议修改后的内容",
      "reason": "修改原因"
    }
  ],
  "summary": "整体优化建议总结",
  "estimated_score_improvement": <预计匹配度提升分数>
}

action 说明：
- add: 新增内容（如补充JD关键词到技能栏）
- modify: 修改现有内容措辞
- reorder: 调整顺序（把匹配的经历提前）
- highlight: 建议突出某段经历"""


class ResumeOptimizer:
    """简历优化建议生成器"""

    def __init__(self, agent_config):
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

    def optimize(self, resume_text, jd_text, match_result=None):
        """
        生成简历优化建议

        :param resume_text: 简历全文
        :param jd_text: JD 全文
        :param match_result: matcher.py 的匹配结果（可选，提供更多上下文）
        :return: dict 优化建议
        """
        if not resume_text or not jd_text:
            return None

        client = self._get_client()

        user_parts = ["## 简历原文：", resume_text[:3000], "", "## 目标JD：", jd_text[:2000]]

        if match_result:
            user_parts.append("")
            user_parts.append("## 匹配分析结果：")
            user_parts.append(json.dumps(match_result, ensure_ascii=False, indent=2))

        user_msg = "\n".join(user_parts)

        try:
            response = client.chat.completions.create(
                model=self.config.get("model", "deepseek-chat"),
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.2,
                max_tokens=2000,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content.strip()
            result = json.loads(content)

            mods = result.get("modifications", [])
            logger.info("[简历优化] 生成 %d 条修改建议，预计提升 %d 分",
                        len(mods),
                        result.get("estimated_score_improvement", 0))

            return result

        except json.JSONDecodeError:
            logger.warning("优化建议返回非 JSON 格式")
            return None
        except Exception:
            logger.exception("简历优化分析异常")
            return None

    def format_suggestions(self, result):
        """将优化建议格式化为可读文本"""
        if not result:
            return "无优化建议"

        lines = []
        lines.append(f"整体建议: {result.get('summary', '')}")
        lines.append(f"预计匹配度提升: +{result.get('estimated_score_improvement', 0)} 分")
        lines.append("")

        for i, mod in enumerate(result.get("modifications", []), 1):
            action_map = {"add": "新增", "modify": "修改", "reorder": "调整顺序", "highlight": "突出"}
            action = action_map.get(mod.get("action", ""), mod.get("action", ""))
            lines.append(f"{i}. [{action}] {mod.get('section', '')}")
            if mod.get("original"):
                lines.append(f"   原文: {mod['original'][:80]}")
            if mod.get("suggested"):
                lines.append(f"   建议: {mod['suggested'][:80]}")
            lines.append(f"   原因: {mod.get('reason', '')}")
            lines.append("")

        return "\n".join(lines)
