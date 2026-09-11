# 简历智能筛选模块
# 基于招聘JD，使用大模型对候选人简历进行综合评估

import os
import json
import logging

logger = logging.getLogger("boss_hr")

_RESUME_FILTER_SYSTEM_PROMPT = """你是一名经验丰富的高级HR招聘专家，擅长快速精准地筛选简历。你的任务是根据招聘岗位要求，对候选人简历进行综合评估。

## 招聘岗位要求
{jd_requirements}

## 评估维度（满分100分）

### 一、硬性条件（40分）
- 学历要求（10分）：符合要求得满分，差一档扣5分
- 工作年限/经验（10分）：完全匹配得满分，基本匹配得5-8分，不匹配得0-3分
- 专业背景（10分）：专业对口得满分，相关得5-8分，不相关得0-3分
- 到岗时间/实习稳定性（10分）：符合要求得满分

### 二、技能匹配（30分）
- 核心技能匹配度（15分）：掌握JD中80%以上核心技能得12-15分，掌握50%得8-11分，低于30%得0-7分
- 项目经验相关性（15分）：有高度相关项目经验得12-15分，有一定相关性得7-11分，不相关得0-6分

### 三、软素质与加分项（20分）
- 大厂/知名公司背景（5分）
- 教育背景亮点（985/211/海外名校）（5分）
- 简历完整度与表达（5分）
- 额外加分技能或证书（5分）

### 四、稳定性与匹配度（10分）
- 职业连贯性（5分）：频繁跳槽扣分
- 期望与岗位匹配度（5分）：薪资/地点/方向匹配度

## 筛选结果分类标准
- 强烈推荐（85-100分）：各方面都很优秀，优先约面
- 推荐（70-84分）：符合要求，可以约面
- 待定（55-69分）：基本符合但有短板，可放入人才池
- 不推荐（0-54分）：不符合要求，淘汰

## 输出格式（严格JSON，不要markdown）
{{
  "score": <0-100整数>,
  "level": "<强烈推荐/推荐/待定/不推荐>",
  "summary": "<一句话总评，50字以内>",
  "matched_points": ["匹配点1", "匹配点2", "匹配点3"],
  "concerns": ["顾虑点1", "顾虑点2"],
  "interview_questions": ["建议面试提问1", "建议面试提问2"],
  "reply_suggestion": "<建议回复话术方向：如'邀请面试'/'进入人才池'/'婉拒'>"
}}

注意事项：
1. 客观评分，不要受主观偏好影响
2. 重点关注与岗位直接相关的经验和技能
3. 对于实习岗，重点关注潜力、学习能力和相关项目经历
4. 不要编造简历中没有的信息
5. 如果简历信息不完整，在concerns中注明"""


class ResumeFilter:
    """简历筛选器"""

    def __init__(self, api_config, position_config):
        """
        :param api_config: API配置字典
        :param position_config: 岗位配置字典（含jd和requirements）
        """
        self.api_config = api_config
        self.position = position_config
        self._client = None
        self._system_prompt = None
        self._build_system_prompt()

    def _build_system_prompt(self):
        """构建系统提示词"""
        jd = self.position.get("jd", "")
        requirements = self.position.get("requirements", {})
        req_text = "\n".join([f"- {k}: {v}" for k, v in requirements.items()])
        full_jd = f"{jd}\n\n详细要求:\n{req_text}"
        self._system_prompt = _RESUME_FILTER_SYSTEM_PROMPT.format(jd_requirements=full_jd)

    def _get_client(self):
        """延迟初始化OpenAI兼容客户端"""
        if self._client is not None:
            return self._client

        api_key = os.environ.get(self.api_config.get("api_key_env", "DEEPSEEK_API_KEY"), "")
        if not api_key:
            raise ValueError(
                f"未找到 API Key，请在环境变量中设置 {self.api_config.get('api_key_env')}。"
            )

        from openai import OpenAI
        self._client = OpenAI(
            api_key=api_key,
            base_url=self.api_config.get("api_base", "https://api.deepseek.com/v1"),
            timeout=self.api_config.get("timeout", 30),
        )
        return self._client

    def filter_resume(self, resume_text, candidate_info=None):
        """
        筛选简历

        :param resume_text: 简历全文文本
        :param candidate_info: 候选人基本信息 dict（可选）
        :return: dict 筛选结果
        """
        if not resume_text or len(resume_text.strip()) < 50:
            logger.warning("[筛选] 简历内容过短，跳过")
            return {
                "score": 0,
                "level": "不推荐",
                "summary": "简历内容不足，无法评估",
                "matched_points": [],
                "concerns": ["简历信息不完整"],
                "interview_questions": [],
                "reply_suggestion": "需人工确认",
            }

        client = self._get_client()

        user_parts = []
        if candidate_info:
            user_parts.append("## 候选人基本信息：")
            user_parts.append(json.dumps(candidate_info, ensure_ascii=False, indent=2))
            user_parts.append("")
        user_parts.append("## 简历全文：")
        user_parts.append(resume_text[:4000])

        user_msg = "\n".join(user_parts)

        try:
            response = client.chat.completions.create(
                model=self.api_config.get("model", "deepseek-chat"),
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.1,
                max_tokens=800,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content.strip()
            result = json.loads(content)

            logger.info("[筛选] 评分=%d 等级=%s", result.get("score", 0), result.get("level", ""))
            return result

        except json.JSONDecodeError:
            logger.warning("[筛选] 返回非JSON格式")
            return {
                "score": 60,
                "level": "待定",
                "summary": "AI解析异常，需人工确认",
                "matched_points": [],
                "concerns": ["AI解析失败"],
                "interview_questions": [],
                "reply_suggestion": "需人工确认",
            }
        except Exception as e:
            logger.exception("[筛选] 调用异常: %s", e)
            return {
                "score": 60,
                "level": "待定",
                "summary": f"系统异常: {str(e)[:30]}",
                "matched_points": [],
                "concerns": ["系统异常"],
                "interview_questions": [],
                "reply_suggestion": "需人工确认",
            }

    def update_position(self, position_config):
        """更新岗位配置，重新构建系统提示词"""
        self.position = position_config
        self._build_system_prompt()
        logger.info("[筛选] 岗位配置已更新: %s", position_config.get("name", ""))
