# 消息处理核心模块
# 监听BOSS直聘消息，简历筛选 + 自动回复

import os
import json
import time
import logging
from datetime import datetime

from config import (
    API_CONFIG, DEFAULT_POSITION, COMPANY_INFO,
    RESUME_FILTER_CONFIG, AUTO_REPLY_CONFIG, MESSAGE_CONFIG,
    CANDIDATES_FILE, MESSAGES_FILE,
)

logger = logging.getLogger("boss_hr")


class MessageHandler:
    """消息处理器"""

    def __init__(self, browser=None):
        self.browser = browser
        self._resume_filter = None
        self._reply_generator = None
        self._candidates = {}
        self._messages = []
        self._load_data()
        self._stop_requested = False
        self._today_auto_replied = 0
        self._last_check_date = datetime.now().strftime("%Y-%m-%d")

    def _load_data(self):
        """加载本地数据"""
        if os.path.exists(CANDIDATES_FILE):
            try:
                with open(CANDIDATES_FILE, 'r', encoding='utf-8') as f:
                    self._candidates = json.load(f)
                logger.info("已加载 %d 位候选人", len(self._candidates))
            except Exception:
                logger.exception("加载候选人数据失败")

        if os.path.exists(MESSAGES_FILE):
            try:
                with open(MESSAGES_FILE, 'r', encoding='utf-8') as f:
                    self._messages = json.load(f)
                logger.info("已加载 %d 条消息记录", len(self._messages))
            except Exception:
                logger.exception("加载消息记录失败")

    def _save_data(self):
        """保存本地数据"""
        os.makedirs(os.path.dirname(CANDIDATES_FILE) or '.', exist_ok=True)
        try:
            with open(CANDIDATES_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._candidates, f, ensure_ascii=False, indent=2)
        except Exception:
            logger.exception("保存候选人数据失败")

        try:
            with open(MESSAGES_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._messages, f, ensure_ascii=False, indent=2)
        except Exception:
            logger.exception("保存消息记录失败")

    def _get_resume_filter(self):
        """获取简历筛选器（延迟初始化）"""
        if self._resume_filter is None:
            from resume_filter import ResumeFilter
            self._resume_filter = ResumeFilter(API_CONFIG, DEFAULT_POSITION)
        return self._resume_filter

    def _get_reply_generator(self):
        """获取回复生成器（延迟初始化）"""
        if self._reply_generator is None:
            from auto_reply import AutoReplyGenerator
            from config import REPLY_MODE
            self._reply_generator = AutoReplyGenerator(
                API_CONFIG, COMPANY_INFO, DEFAULT_POSITION, mode=REPLY_MODE
            )
        return self._reply_generator

    def _is_working_hours(self):
        """判断是否工作时间"""
        if not AUTO_REPLY_CONFIG.get("working_hours_only", False):
            return True
        now_hour = datetime.now().hour
        start, end = AUTO_REPLY_CONFIG.get("working_hours", [9, 19])
        return start <= now_hour < end

    def _check_today_count(self):
        """检查今日自动回复数"""
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self._last_check_date:
            self._today_auto_replied = 0
            self._last_check_date = today
        max_replies = MESSAGE_CONFIG.get("max_auto_replies_per_day", 100)
        return self._today_auto_replied < max_replies

    def process_candidate_resume(self, candidate_id, resume_text, candidate_info=None):
        """
        处理候选人简历：筛选 + 生成回复建议

        :param candidate_id: 候选人ID
        :param resume_text: 简历全文
        :param candidate_info: 候选人基本信息
        :return: dict {filter_result, reply_result}
        """
        logger.info("[处理] 候选人 %s 简历处理中...", candidate_id)

        result = {
            "candidate_id": candidate_id,
            "filter_result": None,
            "reply_result": None,
            "auto_reply_sent": False,
            "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # 1. 简历筛选
        try:
            filt = self._get_resume_filter()
            filter_result = filt.filter_resume(resume_text, candidate_info)
            result["filter_result"] = filter_result
            logger.info("[筛选] %s 得分=%d 等级=%s", candidate_id,
                        filter_result.get("score", 0), filter_result.get("level", ""))
        except Exception as e:
            logger.exception("[筛选] 失败: %s", e)
            filter_result = {"score": 60, "level": "待定", "summary": "筛选异常",
                             "matched_points": [], "concerns": [str(e)],
                             "interview_questions": [], "reply_suggestion": "需人工确认"}
            result["filter_result"] = filter_result

        # 2. 生成回复建议
        try:
            reply_gen = self._get_reply_generator()
            level = filter_result.get("level", "待定")
            auto_levels = AUTO_REPLY_CONFIG.get("auto_reply_levels", ["强烈推荐", "推荐"])

            if level in auto_levels:
                scene = "收到新投递（初筛通过，邀请沟通）"
            else:
                scene = "收到新投递（初筛不通过）"

            reply_result = reply_gen.generate_reply(
                scene=scene,
                candidate_info=candidate_info,
                filter_result=filter_result,
            )
            result["reply_result"] = reply_result
        except Exception as e:
            logger.exception("[回复] 生成失败: %s", e)
            result["reply_result"] = {
                "reply_text": "感谢您的投递，我们会尽快查看并回复~",
                "next_action": "继续沟通",
                "urgency": "中",
                "tags": ["兜底"],
            }

        # 3. 保存候选人信息
        if candidate_id not in self._candidates:
            self._candidates[candidate_id] = {
                "id": candidate_id,
                "info": candidate_info or {},
                "resume_text": resume_text[:5000],
                "filter_history": [],
                "message_history": [],
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

        self._candidates[candidate_id]["filter_history"].append(filter_result)
        self._candidates[candidate_id]["last_filter"] = filter_result
        self._candidates[candidate_id]["status"] = filter_result.get("level", "待定")
        self._save_data()

        # 4. 自动回复（如果开启）
        if (AUTO_REPLY_CONFIG.get("enabled", False) and
            RESUME_FILTER_CONFIG.get("auto_reply_enabled", False) and
            self._is_working_hours() and
            self._check_today_count()):

            level = filter_result.get("level", "")
            auto_levels = AUTO_REPLY_CONFIG.get("auto_reply_levels", [])
            if level in auto_levels:
                result["auto_reply_sent"] = True
                self._today_auto_replied += 1
                logger.info("[自动回复] 已发送给 %s", candidate_id)

        return result

    def process_incoming_message(self, candidate_id, message_content, candidate_info=None):
        """
        处理候选人发来的消息

        :param candidate_id: 候选人ID
        :param message_content: 消息内容
        :param candidate_info: 候选人信息
        :return: dict
        """
        logger.info("[消息] 收到候选人 %s 的消息: %s", candidate_id, message_content[:50])

        result = {
            "candidate_id": candidate_id,
            "message": message_content,
            "reply_result": None,
            "category": "其他",
            "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # 记录消息
        self._messages.append({
            "candidate_id": candidate_id,
            "direction": "in",
            "content": message_content,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

        # 生成回复
        try:
            reply_gen = self._get_reply_generator()

            # 简单判断场景（MVP版本，后续可接入消息分类模块）
            scene = "候选人主动打招呼"
            if "面试" in message_content or "约面" in message_content:
                scene = "面试相关"
            elif "薪资" in message_content or "工资" in message_content:
                scene = "候选人询问岗位详情"
            elif "岗位" in message_content or "工作内容" in message_content:
                scene = "候选人询问岗位详情"

            reply_result = reply_gen.generate_reply(
                scene=scene,
                candidate_info=candidate_info,
                message_content=message_content,
            )
            result["reply_result"] = reply_result
            result["category"] = scene

        except Exception as e:
            logger.exception("[回复] 生成失败: %s", e)
            result["reply_result"] = {
                "reply_text": "收到~我这边帮您确认下，稍后回复您😊",
                "next_action": "继续沟通",
                "urgency": "中",
                "tags": ["兜底"],
            }

        self._save_data()
        return result

    def stop(self):
        """停止消息监听"""
        self._stop_requested = True
        logger.info("[消息] 收到停止信号")

    def get_candidate(self, candidate_id):
        """获取候选人信息"""
        return self._candidates.get(candidate_id)

    def get_all_candidates(self):
        """获取所有候选人列表"""
        return list(self._candidates.values())

    def update_position(self, position_config):
        """更新招聘岗位配置"""
        if self._resume_filter:
            self._resume_filter.update_position(position_config)
        if self._reply_generator:
            self._reply_generator.update_position(position_config)
        logger.info("[配置] 岗位已更新: %s", position_config.get("name", ""))

    def update_company(self, company_info):
        """更新公司信息"""
        if self._reply_generator:
            self._reply_generator.update_company(company_info)
        logger.info("[配置] 公司信息已更新")

    def start_auto_reply(self, hr_browser, status_callback=None, progress_callback=None):
        """
        启动自动回复循环

        :param hr_browser: HRBrowser 实例
        :param status_callback: 状态回调函数 status_callback(text)
        :param progress_callback: 进度回调函数 progress_callback(processed, total)
        """
        self._stop_requested = False
        replied_count = 0
        processed_names = set()  # 本轮已处理的候选人（避免重复处理）

        def _log(msg):
            print(msg, flush=True)
            if status_callback:
                try:
                    status_callback(msg)
                except Exception:
                    pass

        _log("🤖 自动回复已启动...")
        _log("📋 正在扫描消息列表...")

        # 等待页面完全加载
        for wait_i in range(6):
            if self._stop_requested:
                return 0
            conversations = hr_browser.get_unread_conversations()
            if conversations:
                break
            _log(f"  等待页面加载... ({wait_i + 1}/6)")
            time.sleep(3)

        if not conversations:
            _log("⚠️  页面加载完成但未找到对话列表，可能是选择器不匹配")
            _log("💡 请确保当前在BOSS直聘消息页面，且左侧有对话列表")

        # 滚动到最顶部，从最新的开始处理
        hr_browser.scroll_to_top_chat_list()
        time.sleep(1)

        round_num = 0
        no_list_count = 0
        while not self._stop_requested:
            round_num += 1
            _log(f"\n--- 第 {round_num} 轮扫描 ---")

            # 获取当前可见的对话列表
            conversations = hr_browser.get_unread_conversations()
            if not conversations:
                no_list_count += 1
                _log(f"  未找到对话列表，等待重试... ({no_list_count})")
                time.sleep(5)
                if no_list_count >= 10:
                    _log("  ⚠️  连续多次未找到对话列表，请检查页面是否正常")
                    no_list_count = 5  # 重置为5，继续尝试但不那么频繁
                continue

            no_list_count = 0  # 找到了就重置计数

            unread_list = [c for c in conversations if c.get("unread")]
            _log(f"  本页共 {len(conversations)} 个对话，未读标记 {len(unread_list)} 个")

            # 遍历所有对话，跳过已处理的（未读标记不准时也能兜底）
            for idx, conv in enumerate(conversations):
                if self._stop_requested:
                    break

                name = conv.get("name", f"候选人_{idx}")

                # 如果已回复过，跳过（用名字做简单去重）
                if name in processed_names:
                    continue

                _log(f"\n  👉 检查: {name}")

                # 点击进入对话
                if not hr_browser.click_conversation(idx):
                    _log(f"    ❌ 点击失败，跳过")
                    continue

                time.sleep(1.5)

                # 获取聊天消息
                messages = hr_browser.get_current_chat_messages()
                if not messages:
                    _log(f"    ⚠️  没有消息，跳过")
                    processed_names.add(name)
                    continue

                # 检查最后一条消息是不是对方发的
                last_msg_sender = "self"
                last_msg_content = ""
                for m in reversed(messages):
                    if m.get("content", "").strip():
                        last_msg_sender = m.get("sender", "self")
                        last_msg_content = m.get("content", "")
                        break

                # 如果最后一条是自己发的，说明已经回复过了
                if last_msg_sender == "self":
                    _log(f"    ✅ 最后一条是自己发的，已回复过")
                    processed_names.add(name)
                    continue

                # 对方发了新消息，需要回复
                # 获取候选人信息
                candidate_info = hr_browser.get_candidate_info()
                candidate_info["name"] = name
                _log(f"    候选人: {candidate_info.get('name', '')}")

                latest_msg = last_msg_content
                _log(f"    最新消息: {latest_msg[:40]}..." if len(latest_msg) > 40 else f"    最新消息: {latest_msg}")

                # 判断场景并生成回复
                scene = self._detect_scene(latest_msg)
                _log(f"    场景: {scene}")

                # 生成回复
                reply_gen = self._get_reply_generator()
                reply_result = reply_gen.generate_reply(
                    scene=scene,
                    candidate_info=candidate_info,
                    message_content=latest_msg,
                )

                reply_text = reply_result.get("reply_text", "")
                _log(f"    回复内容: {reply_text[:50]}...")

                # 发送回复
                if reply_text:
                    sent = hr_browser.send_message(reply_text)
                    if sent:
                        replied_count += 1
                        processed_names.add(name)
                        _log(f"    ✅ 已回复（累计 {replied_count} 条）")
                        if progress_callback:
                            try:
                                progress_callback(replied_count)
                            except Exception:
                                pass
                    else:
                        _log(f"    ❌ 发送失败")

                    # 记录到本地
                    candidate_id = name
                    self.process_incoming_message(candidate_id, latest_msg, candidate_info)

                # 回复间隔，模拟人工
                time.sleep(1.5)

            # 本轮处理完，往下滚加载更多
            if not self._stop_requested:
                _log("\n  ⬇️  下滑加载更多...")
                hr_browser.scroll_chat_list("down")
                time.sleep(1.5)

                # 获取滚动后的对话列表
                new_convs = hr_browser.get_unread_conversations()
                new_unread = [c for c in new_convs if c.get("unread") and c.get("name") not in processed_names]

                # 如果没有新的未读了，再滚几次确认，然后退出
                if not new_unread:
                    _log("  📭 暂无新的未读消息，继续监听...")
                    # 等一会儿再检查
                    for _ in range(6):  # 等30秒
                        if self._stop_requested:
                            break
                        time.sleep(5)

        _log(f"\n🏁 自动回复已停止，共回复 {replied_count} 条消息")
        return replied_count

    def _detect_scene(self, message):
        """
        根据消息内容判断回复场景

        :param message: 候选人消息内容
        :return: 场景名称
        """
        if not message:
            return "候选人主动打招呼"

        msg = message.strip()

        # 婉拒相关
        if any(w in msg for w in ["不去了", "不考虑", "算了", "不好意思", "抱歉", "暂时不"]):
            return "候选人婉拒"

        # 面试相关
        if any(w in msg for w in ["面试", "约面", "什么时候面", "方便面试"]):
            return "邀约面试"

        # 岗位咨询
        if any(w in msg for w in ["薪资", "工资", "多少钱", "工作内容", "做什么", "岗位", "职责", "要求"]):
            return "候选人询问岗位详情"

        # 投递相关（刚投递打招呼）
        if any(w in msg for w in ["投递", "简历", "你好", "您好", "hi", "Hi", "在吗", "请问"]):
            return "收到新投递（初筛通过，邀请沟通）"

        # 默认
        return "候选人主动打招呼"
