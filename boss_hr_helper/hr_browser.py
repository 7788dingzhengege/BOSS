# BOSS直聘消息页面浏览器操作模块
# 兼容HR端和求职者端的消息列表

import time
import logging

logger = logging.getLogger("boss_hr")

BOSS_CHAT_URL = "https://www.zhipin.com/web/chat/"


class HRBrowser:
    """BOSS直聘消息页面浏览器操作"""

    def __init__(self, browser_manager):
        self.browser = browser_manager
        self.driver = browser_manager.driver

    def open_chat_page(self):
        """打开BOSS直聘消息页面"""
        logger.info("[HR] 打开消息页面...")
        self.driver.get(BOSS_CHAT_URL)
        time.sleep(4)
        current_url = self.driver.url
        logger.info("[HR] 当前URL: %s", current_url)

        if "login" in current_url or "signin" in current_url:
            logger.warning("[HR] 需要登录，请在浏览器中扫码登录")
            print("  ⚠️  请在浏览器中扫码登录BOSS直聘...")
            return False

        print("  ✅ 消息页面已打开")
        return True

    def wait_for_login(self, timeout=120):
        """等待用户登录"""
        start = time.time()
        while time.time() - start < timeout:
            current_url = self.driver.url
            if "login" not in current_url and "signin" not in current_url:
                try:
                    title = self.driver.title
                    if "消息" in title or "BOSS" in title or "沟通" in title:
                        logger.info("[HR] 登录成功")
                        print("  ✅ 登录成功")
                        time.sleep(3)
                        return True
                except Exception:
                    pass
            time.sleep(2)
        logger.warning("[HR] 登录超时")
        return False

    def get_conversations(self):
        """
        获取当前可见的对话列表（更健壮的版本）

        :return: list of dict [{name, last_msg, unread, unread_count, index}]
        """
        try:
            result = self.driver.run_js('''
                (function() {
                    var items = [];

                    // 策略1: 找所有包含头像和文字的可点击列表项
                    // 左侧消息列表通常在页面左侧，包含头像、名字、消息预览
                    function findConversations() {
                        var found = [];

                        // 找所有可能的列表项容器
                        var candidates = document.querySelectorAll(
                            'div[class*="item"], div[class*="list"] > div, ' +
                            'li[class*="item"], [class*="chat"] [class*="item"], ' +
                            '[class*="conversation"], [class*="message-list"] > div'
                        );

                        // 过滤：必须包含头像（img或带背景图的div）和文字
                        for (var i = 0; i < candidates.length; i++) {
                            var el = candidates[i];
                            // 跳过太小的元素
                            if (el.offsetHeight < 40 || el.offsetWidth < 100) continue;

                            // 检查是否有头像（img标签或者带背景图的div）
                            var hasAvatar = el.querySelector('img') ||
                                el.querySelector('[style*="background-image"]') ||
                                el.querySelector('[class*="avatar"]');
                            if (!hasAvatar) continue;

                            // 获取所有文本
                            var text = el.innerText.trim();
                            if (!text || text.length < 2) continue;

                            // 文本行应该有2-4行（名字、消息、时间等）
                            var lines = text.split('\\n').filter(function(l) { return l.trim().length > 0; });
                            if (lines.length < 2) continue;

                            found.push({
                                element: el,
                                text: text,
                                lines: lines,
                                height: el.offsetHeight
                            });
                        }

                        // 按高度排序，取高度相近的一组（消息列表项高度应该差不多）
                        if (found.length === 0) return [];

                        found.sort(function(a, b) { return b.height - a.height; });

                        // 取前30个中高度最接近的
                        var result = [];
                        var avgHeight = 0;
                        for (var j = 0; j < Math.min(found.length, 20); j++) {
                            avgHeight += found[j].height;
                        }
                        avgHeight = avgHeight / Math.min(found.length, 20);

                        for (var k = 0; k < found.length; k++) {
                            if (Math.abs(found[k].height - avgHeight) < avgHeight * 0.4) {
                                result.push(found[k]);
                            }
                        }

                        return result;
                    }

                    var convs = findConversations();

                    // 解析每个对话的信息
                    for (var i = 0; i < convs.length; i++) {
                        var c = convs[i];
                        var lines = c.lines;

                        // 第一行一般是名字
                        var name = lines[0] || '';

                        // 找最后一条消息（不含纯数字时间的行）
                        var lastMsg = '';
                        for (var m = lines.length - 1; m >= 0; m--) {
                            var line = lines[m].trim();
                            // 跳过纯时间格式（如 13:52, 昨天, 07-15等）
                            if (/^\\d{1,2}:\\d{2}$/.test(line)) continue;
                            if (/^昨天|前天|刚刚|\\d{1,2}-\\d{1,2}$/.test(line)) continue;
                            if (/^\\d+月\\d+日$/.test(line)) continue;
                            if (line.length < 2) continue;
                            lastMsg = line;
                            break;
                        }

                        // 检查未读：有没有红色小圆点或者数字角标
                        var hasUnread = false;
                        var unreadCount = 0;

                        // 检查是否有sup/badage/带数字的小圆圈
                        var badges = c.element.querySelectorAll(
                            'sup, [class*="badge"], [class*="num"], [class*="count"], ' +
                            '[class*="unread"], [class*="dot"], [class*="red"]'
                        );
                        for (var b = 0; b < badges.length; b++) {
                            var btext = badges[b].innerText.trim();
                            var bstyle = window.getComputedStyle(badges[b]);
                            var bgColor = bstyle.backgroundColor || '';
                            var isRed = bgColor.indexOf('255') >= 0 || bgColor.indexOf('red') >= 0 ||
                                bgColor.indexOf('rgb(255') >= 0;

                            if (btext && /^\\d+$/.test(btext)) {
                                hasUnread = true;
                                unreadCount = parseInt(btext);
                                break;
                            }
                            if (isRed && badges[b].offsetWidth > 0 && badges[b].offsetHeight > 0) {
                                // 红色小圆点
                                var isSmall = badges[b].offsetWidth < 20 && badges[b].offsetHeight < 20;
                                if (isSmall) {
                                    hasUnread = true;
                                    unreadCount = 1;
                                    break;
                                }
                            }
                        }

                        // 额外检测：名字前面有没有 [已读] 等标签
                        var hasReadTag = /^\\[已读\\]/.test(lastMsg) || /已读/.test(name);

                        items.push({
                            name: name.replace(/^\\[.*?\\]/, '').trim(),
                            last_msg: lastMsg,
                            unread: hasUnread,
                            unread_count: unreadCount,
                            has_read_tag: hasReadTag,
                            index: i
                        });
                    }

                    return JSON.stringify(items);
                })();
            ''')

            if result and result.strip():
                import json
                conversations = json.loads(result)
                logger.info("[HR] 获取到 %d 个对话", len(conversations))
                return conversations

        except Exception as e:
            logger.exception("[HR] 获取对话列表失败: %s", e)

        return []

    def get_unread_conversations(self):
        """获取未读对话列表（兼容接口）"""
        return self.get_conversations()

    def click_conversation(self, index):
        """
        点击第index个对话

        :param index: 对话索引
        :return: bool
        """
        try:
            self.driver.run_js(f'''
                (function(idx) {{
                    function findConversations() {{
                        var found = [];
                        var candidates = document.querySelectorAll(
                            'div[class*="item"], div[class*="list"] > div, ' +
                            'li[class*="item"], [class*="chat"] [class*="item"], ' +
                            '[class*="conversation"], [class*="message-list"] > div'
                        );
                        for (var i = 0; i < candidates.length; i++) {{
                            var el = candidates[i];
                            if (el.offsetHeight < 40 || el.offsetWidth < 100) continue;
                            var hasAvatar = el.querySelector('img') ||
                                el.querySelector('[style*="background-image"]') ||
                                el.querySelector('[class*="avatar"]');
                            if (!hasAvatar) continue;
                            var text = el.innerText.trim();
                            if (!text || text.length < 2) continue;
                            var lines = text.split('\\n').filter(function(l) {{ return l.trim().length > 0; }});
                            if (lines.length < 2) continue;
                            found.push({{ element: el, height: el.offsetHeight }});
                        }}
                        if (found.length === 0) return false;

                        found.sort(function(a, b) {{ return b.height - a.height; }});
                        var avgHeight = 0;
                        for (var j = 0; j < Math.min(found.length, 20); j++) {{
                            avgHeight += found[j].height;
                        }}
                        avgHeight = avgHeight / Math.min(found.length, 20);

                        var result = [];
                        for (var k = 0; k < found.length; k++) {{
                            if (Math.abs(found[k].height - avgHeight) < avgHeight * 0.4) {{
                                result.push(found[k]);
                            }}
                        }}

                        if (idx >= result.length) return false;
                        var target = result[idx].element;
                        target.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        setTimeout(function() {{
                            target.click();
                        }}, 300);
                        return true;
                    }}
                    return findConversations();
                }})({index});
            ''')
            time.sleep(1.5)
            logger.info("[HR] 点击第 %d 个对话", index)
            return True
        except Exception as e:
            logger.exception("[HR] 点击对话失败: %s", e)
            return False

    def get_current_chat_messages(self):
        """获取当前聊天窗口的消息"""
        try:
            result = self.driver.run_js('''
                (function() {
                    var msgs = [];

                    // 找聊天消息容器
                    var containers = document.querySelectorAll(
                        '[class*="chat-message"], [class*="message-item"], ' +
                        '[class*="msg-item"], [class*="bubble"], ' +
                        '[class*="chat-content"] [class*="item"]'
                    );

                    if (containers.length === 0) {
                        // 兜底：找所有带文字的气泡
                        containers = document.querySelectorAll('div[class*="bubble"], div[class*="message"]');
                    }

                    for (var i = 0; i < containers.length; i++) {
                        var el = containers[i];
                        var text = el.innerText.trim();
                        if (!text || text.length < 1) continue;
                        if (text.length > 500) continue; // 太长的跳过

                        // 判断左右（自己发的还是对方发的）
                        var rect = el.getBoundingClientRect();
                        var parent = el.parentElement;
                        var parentRect = parent ? parent.getBoundingClientRect() : { width: window.innerWidth, left: 0 };

                        var isSelf = false;
                        // 如果元素在右半边，一般是自己发的
                        if (rect.left > parentRect.left + parentRect.width / 2) {
                            isSelf = true;
                        }
                        // 检查class名
                        var cls = el.className || '';
                        if (/self|mine|right|send/.test(cls)) isSelf = true;
                        if (/other|left|receive|friend/.test(cls)) isSelf = false;

                        msgs.push({
                            sender: isSelf ? 'self' : 'other',
                            content: text,
                            index: i
                        });
                    }

                    return JSON.stringify(msgs);
                })();
            ''')

            if result and result.strip():
                import json
                return json.loads(result)
        except Exception as e:
            logger.debug("[HR] 获取聊天消息失败: %s", e)

        return []

    def get_candidate_info(self):
        """获取当前聊天对方的信息"""
        info = {"name": "候选人"}
        try:
            result = self.driver.run_js('''
                (function() {
                    var info = {};

                    // 找顶部标题栏的名字
                    var selectors = [
                        '[class*="chat-header"] [class*="name"]',
                        '[class*="chat-title"] [class*="name"]',
                        '[class*="header"] [class*="name"]',
                        '[class*="title"] [class*="name"]',
                        'h3[class*="name"]',
                        '[class*="user-name"]',
                        '[class*="username"]'
                    ];

                    for (var s = 0; s < selectors.length; s++) {
                        var el = document.querySelector(selectors[s]);
                        if (el && el.innerText.trim().length > 0 && el.innerText.trim().length < 20) {
                            info.name = el.innerText.trim();
                            break;
                        }
                    }

                    return JSON.stringify(info);
                })();
            ''')
            if result and result.strip():
                import json
                info.update(json.loads(result))
        except Exception:
            pass

        return info

    def send_message(self, text):
        """发送消息"""
        try:
            # 第一步：找到输入框并填入内容
            input_found = self.driver.run_js(f'''
                (function(txt) {{
                    // 找输入框
                    var inputs = document.querySelectorAll(
                        'textarea[placeholder*="输入"], textarea[placeholder*="消息"], ' +
                        'textarea[placeholder*="说"], input[placeholder*="输入"], ' +
                        '[class*="chat-input"] textarea, [class*="chat-input"] input, ' +
                        '[class*="input-area"] textarea, [contenteditable="true"]'
                    );

                    var input = null;
                    for (var i = 0; i < inputs.length; i++) {{
                        if (inputs[i].offsetParent !== null || inputs[i].isContentEditable) {{
                            input = inputs[i];
                            break;
                        }}
                    }}

                    if (!input) return false;

                    input.focus();

                    if (input.tagName === 'TEXTAREA' || input.tagName === 'INPUT') {{
                        input.value = txt;
                        // 触发事件
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }} else if (input.isContentEditable) {{
                        input.innerHTML = txt.replace(/\\n/g, '<br>');
                        // 触发事件
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}

                    return true;
                }})({repr(text)});
            ''')

            if not input_found:
                logger.warning("[HR] 没找到输入框")
                return False

            time.sleep(0.8)

            # 第二步：点击发送按钮或按回车
            sent = self.driver.run_js('''
                (function() {
                    // 找发送按钮
                    var btns = document.querySelectorAll(
                        'button[class*="send"], [class*="send-btn"], ' +
                        'button[class*="submit"], [class*="btn-send"], ' +
                        'button:has-text("发送"), [aria-label*="发送"]'
                    );

                    for (var i = 0; i < btns.length; i++) {
                        var btn = btns[i];
                        if (btn.offsetParent !== null) {
                            btn.click();
                            return true;
                        }
                    }

                    // 兜底：找输入框按回车
                    var inputs = document.querySelectorAll(
                        'textarea[placeholder*="输入"], textarea[placeholder*="消息"], ' +
                        '[class*="chat-input"] textarea'
                    );
                    for (var j = 0; j < inputs.length; j++) {
                        if (inputs[j].offsetParent !== null) {
                            inputs[j].focus();
                            var ev = new KeyboardEvent('keydown', {
                                key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true
                            });
                            inputs[j].dispatchEvent(ev);
                            return true;
                        }
                    }

                    return false;
                })();
            ''')

            if sent:
                time.sleep(1)
                logger.info("[HR] 消息已发送: %s...", text[:30])
                return True

            return False

        except Exception as e:
            logger.exception("[HR] 发送消息失败: %s", e)
            return False

    def scroll_chat_list(self, direction="down"):
        """滚动消息列表"""
        try:
            self.driver.run_js(f'''
                (function(dir) {{
                    // 找左侧列表容器
                    var containers = document.querySelectorAll(
                        '[class*="chat-list"], [class*="conversation-list"], ' +
                        '[class*="message-list"], [class*="list-panel"], ' +
                        'aside [class*="list"], .left-panel [class*="list"]'
                    );

                    var container = null;
                    for (var i = 0; i < containers.length; i++) {{
                        if (containers[i].scrollHeight > containers[i].clientHeight + 100) {{
                            container = containers[i];
                            break;
                        }}
                    }}

                    if (container) {{
                        if (dir === 'down') {{
                            container.scrollTop += 400;
                        }} else {{
                            container.scrollTop -= 400;
                        }}
                    }} else {{
                        window.scrollBy(0, dir === 'down' ? 400 : -400);
                    }}
                    return true;
                }})('{direction}');
            ''')
            time.sleep(0.5)
        except Exception as e:
            logger.debug("[HR] 滚动失败: %s", e)

    def scroll_to_top_chat_list(self):
        """滚动到消息列表顶部"""
        try:
            self.driver.run_js('''
                (function() {
                    var containers = document.querySelectorAll(
                        '[class*="chat-list"], [class*="conversation-list"], ' +
                        '[class*="message-list"], [class*="list-panel"]'
                    );
                    for (var i = 0; i < containers.length; i++) {
                        if (containers[i].scrollHeight > 0) {
                            containers[i].scrollTop = 0;
                        }
                    }
                })();
            ''')
            time.sleep(0.5)
        except Exception:
            pass
