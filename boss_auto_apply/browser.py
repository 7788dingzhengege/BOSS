# 浏览器管理模块（使用 DrissionPage，无需单独下载驱动）

import sys
import os
import time
import random
import shutil
import logging

if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from DrissionPage import ChromiumPage, ChromiumOptions
from config import BROWSER_CONFIG, BOSS_URL

logger = logging.getLogger("boss_applier")

# Edge 浏览器常见安装路径
_EDGE_CANDIDATE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def _find_edge_path():
    """动态查找 Edge 浏览器可执行文件路径"""
    # 1. 通过 PATH 查找
    path = shutil.which("msedge")
    if path:
        return path
    # 2. 检查常见安装路径
    for p in _EDGE_CANDIDATE_PATHS:
        if os.path.exists(p):
            return p
    return None


class BrowserManager:
    """浏览器管理类"""

    def __init__(self):
        self.driver = None  # 实际是 ChromiumPage

    def init_browser(self):
        """初始化浏览器（直接调用系统安装的 Edge/Chrome）"""
        co = ChromiumOptions()

        if BROWSER_CONFIG["headless"]:
            co.headless()

        co.set_argument(f"--window-size={BROWSER_CONFIG['window_size'][0]},{BROWSER_CONFIG['window_size'][1]}")
        co.set_argument("--lang=zh-CN")

        # 反检测：隐藏自动化痕迹
        co.set_argument("--disable-blink-features=AutomationControlled")
        co.set_argument("--disable-infobars")
        co.set_argument("--no-default-browser-check")
        co.set_argument("--no-first-run")
        co.set_pref("excludeSwitches", ["enable-automation"])

        # 指定浏览器类型：Edge 时动态查找路径，找不到则回退 Chrome
        browser_type = BROWSER_CONFIG.get("browser_type", "chrome").lower()
        if browser_type == "edge":
            edge_path = _find_edge_path()
            if edge_path:
                co.set_browser_path(edge_path)
                logger.info("使用 Microsoft Edge: %s", edge_path)
            else:
                logger.warning("未找到 Edge，回退使用 Chrome")

        try:
            self.driver = ChromiumPage(co)
        except Exception:
            logger.exception("浏览器启动失败")
            print("=" * 50)
            print("[请确认]")
            print("1. 已安装 Edge 或 Chrome 浏览器")
            print("2. 浏览器未被其他程序占用（关闭所有 Edge 窗口再试）")
            print("=" * 50)
            raise

        logger.info("浏览器初始化成功")
        # 接口监听：直接拦截 BOSS 职位列表接口，拿结构化 JSON（比 DOM 解析更稳，抗改版）
        try:
            self.driver.listen.start()
            logger.info("已开启接口监听: joblist")
        except Exception:
            logger.warning("接口监听开启失败，将回退 DOM 解析", exc_info=True)
        return self.driver

    def open_boss(self):
        """打开BOSS直聘"""
        self.driver.get(BOSS_URL)
        time.sleep(5)
        current_url = self.driver.url
        logger.info("已打开 %s", current_url)

        if current_url.startswith("data:"):
            logger.warning("页面可能被拦截，请检查浏览器是否正常显示")

    def scroll_down(self, pixel=500, delay=0.1):
        """向下滚动页面"""
        self.driver.scroll.down(pixel)
        time.sleep(delay)

    def random_delay(self, min_sec=3, max_sec=7):
        """随机延迟"""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)

    def close(self):
        """关闭浏览器"""
        if self.driver:
            self.driver.quit()
            logger.info("浏览器已关闭")
