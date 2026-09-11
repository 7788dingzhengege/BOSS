# 自动回复模块
# 根据不同场景生成专业的HR回复消息

import os
import json
import logging

from config import REPLY_MODE, REPLY_TEMPLATES

logger = logging.getLogger("boss_hr")

_AUTO_REPLY_SYSTEM_PROMPT = """你是一名专业、亲切的HR招聘助手。你的任务是根据不同场景，生成自然、专业的回复消息，发送给BOSS直聘上的求职者。

## HR人设
- 角色：{company_name}的HR招聘专员
- 风格：专业、真诚、高效、有温度
- 语气：友好但不失专业，避免过于生硬或模板化
- 字数：控制在50-200字之间，简洁明了

## 公司信息
- 公司：{company_name}
- 行业：{company_industry}
- 规模：{company_size}
- 简介：{company_description}
- 福利：{company_benefits}

## 招聘岗位
{position_info}

## 回复场景与要求

### 场景1：收到新投递（初筛通过，邀请沟通）
- 感谢投递，表达兴趣
- 简单确认候选人的核心匹配点
- 告知下一步流程，邀请进一步沟通
- 主动询问对方方便的时间
- 结尾留个互动引导

### 场景2：收到新投递（初筛不通过）
- 感谢投递，礼貌感谢
- 委婉说明方向不太匹配（不具体说缺点）
- 表达已存入人才库，有合适机会再联系
- 语气要友好，不要打击对方

### 场景3：候选人询问岗位详情
- 针对性回答问题
- 补充1-2个岗位亮点
- 引导进一步沟通

### 场景4：邀约面试
- 明确告知面试形式（线上面试/线下面试）
- 提供2-3个时间选项供选择
- 简单说明面试流程和面试官
- 提醒需要准备的事项

### 场景5：候选人主动打招呼
- 根据消息内容灵活回复
- 先表达感谢，再简单介绍岗位
- 判断对方匹配度，决定是否推进

### 场景6：候选人婉拒
- 礼貌回应，表示理解
- 表达希望未来有合作机会
- 保持专业友好

## 输出格式（严格JSON，不要markdown）
{{
  "reply_text": "<回复正文>",
  "next_action": "<下一步动作：邀约面试/继续沟通/存入人才池/结束沟通>",
  "urgency": "<紧急程度：高/中/低>",
  "tags": ["标签1", "标签2"]
}}

注意事项：
1. 不要编造公司或岗位不存在的信息
2. 回复要自然，像真人发的，不要太像AI
3. 适当使用表情符号增加亲和力（1-2个即可）
4. 涉及薪资等敏感问题，按公司标准回答，不要随意承诺
5. 对于不合适的候选人，婉拒要礼貌，给对方留面子"""


class AutoReplyGenerator:
    """自动回复生成器"""

    def __init__(self, api_config, company_info, position_config, mode=None):
        """
        :param api_config: API配置字典
        :param company_info: 公司信息字典
        :param position_config: 岗位配置字典
        :param mode: 回复模式 "template" 或 "ai"，默认从配置读取
        """
        self.api_config = api_config
        self.company_info = company_info
        self.position = position_config
        self.mode = mode or REPLY_MODE
        self.templates = REPLY_TEMPLATES.copy()
        self._client = None
        self._system_prompt = None
        if self.mode == "ai":
            self._build_system_prompt()

    def _build_system_prompt(self):
        """构建系统提示词"""
        pos_info = f"""岗位：{self.position.get('name', '')}
部门：{self.position.get('department', '')}
JD：{self.position.get('jd', '')[:500]}"""

        self._system_prompt = _AUTO_REPLY_SYSTEM_PROMPT.format(
            company_name=self.company_info.get("name", ""),
            company_industry=self.company_info.get("industry", ""),
            company_size=self.company_info.get("size", ""),
            company_description=self.company_info.get("description", ""),
            company_benefits="、".join(self.company_info.get("benefits", [])),
            position_info=pos_info,
        )

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

    def generate_reply(self, scene, candidate_info=None, message_content=None, filter_result=None):
        """
        生成自动回复

        :param scene: 场景类型
        :param candidate_info: 候选人信息 dict
        :param message_content: 候选人消息内容
        :param filter_result: 简历筛选结果 dict
        :return: dict 回复结果
        """
        # 模板模式：直接返回预设模板，无需API调用
        if self.mode == "template":
            return self._get_template_reply(scene, candidate_info)

        # AI模式：调用大模型生成
        client = self._get_client()

        user_parts = [f"## 场景：{scene}"]

        if candidate_info:
            user_parts.append("## 候选人信息：")
            user_parts.append(json.dumps(candidate_info, ensure_ascii=False, indent=2))

        if message_content:
            user_parts.append("## 候选人最新消息：")
            user_parts.append(message_content[:1000])

        if filter_result:
            user_parts.append("## 简历筛选结果：")
            user_parts.append(json.dumps(filter_result, ensure_ascii=False, indent=2))

        user_msg = "\n\n".join(user_parts)

        try:
            response = client.chat.completions.create(
                model=self.api_config.get("model", "deepseek-chat"),
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                temperature=self.api_config.get("temperature", 0.7),
                max_tokens=600,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content.strip()
            result = json.loads(content)

            logger.info("[回复] AI生成成功，场景=%s", scene)
            return result

        except json.JSONDecodeError:
            logger.warning("[回复] 返回非JSON格式")
            return {
                "reply_text": "感谢您的投递，我们会尽快查看您的简历并与您联系~",
                "next_action": "继续沟通",
                "urgency": "中",
                "tags": ["兜底回复"],
            }
        except Exception as e:
            logger.exception("[回复] 调用异常: %s", e)
            return {
                "reply_text": "感谢您的投递，我们会尽快查看您的简历并与您联系~",
                "next_action": "继续沟通",
                "urgency": "中",
                "tags": ["异常兜底"],
            }

    def _get_template_reply(self, scene, candidate_info=None):
        """从模板获取回复"""
        # 精确匹配场景
        if scene in self.templates:
            template = self.templates[scene].copy()
            reply_text = template.get("reply_text", "")

            # 简单的变量替换（候选人姓名等）
            if candidate_info:
                name = candidate_info.get("name", "")
                if name:
                    reply_text = reply_text.replace("您好", f"{name} 您好")
                    reply_text = reply_text.replace("您好~", f"{name} 您好~")

            template["reply_text"] = reply_text
            logger.info("[回复] 模板匹配成功，场景=%s", scene)
            return template

        # 模糊匹配（找最接近的场景）
        for key in self.templates:
            if scene in key or key in scene:
                template = self.templates[key].copy()
                logger.info("[回复] 模板模糊匹配: '%s' -> '%s'", scene, key)
                return template

        logger.warning("[回复] 未找到模板: %s", scene)
        return {
            "reply_text": "感谢您的消息，我们会尽快回复~",
            "next_action": "继续沟通",
            "urgency": "中",
            "tags": ["默认模板"],
        }

    def update_template(self, scene, template_data):
        """更新单个场景的模板"""
        self.templates[scene] = template_data
        logger.info("[回复] 模板已更新: %s", scene)

    def get_templates(self):
        """获取所有模板"""
        return self.templates.copy()

    def update_position(self, position_config):
        """更新岗位配置"""
        self.position = position_config
        self._build_system_prompt()

    def update_company(self, company_info):
        """更新公司信息"""
        self.company_info = company_info
        self._build_system_prompt()
