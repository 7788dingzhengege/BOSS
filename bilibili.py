# Bilibili 播放量刷取工具 v3 (浏览器真实观看版)
# 使用 DrissionPage 模拟真实用户观看，有效增加播放量
# 独立脚本，与 BOSS 投递代码完全隔离

import sys
import os
import time
import random

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from DrissionPage import ChromiumPage, ChromiumOptions

# ====== 配置（可自行修改）=====
VIDEO_URL = "https://www.bilibili.com/video/BV1Wv411F7ae/?spm_id_from=333.1387.homepage_video_card.click"
TARGET_COUNT = 60             # 目标刷取数量
WATCH_TIME_RANGE = (6, 12)    # 每个视频观看时长(秒)
PAGE_LOAD_WAIT = 5            # 页面加载等待(秒)
HEADLESS = False              # 是否无头模式(False=显示浏览器)


def create_browser():
    """创建浏览器实例"""
    co = ChromiumOptions()
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_argument('--no-sandbox')
    if HEADLESS:
        co.headless()
    page = ChromiumPage(co)
    return page


def run():
    print()
    print("  ╔══════════════════════════════════╗")
    print("  ║  Bilibili 播放量刷取 v3 (浏览器) ║")
    print("  ╚══════════════════════════════════╝")
    print(f"\n  视频: {VIDEO_URL}")
    print(f"  目标: {TARGET_COUNT} 次 | 观看: {WATCH_TIME_RANGE[0]}-{WATCH_TIME_RANGE[1]}秒/次\n")

    page = create_browser()
    success = 0
    fail = 0
    start_time = time.time()

    try:
        for i in range(1, TARGET_COUNT + 1):
            try:
                # 打开视频页面
                page.get(VIDEO_URL)
                time.sleep(PAGE_LOAD_WAIT)

                # 等待播放器出现并点击播放
                player = None

                # 方式1: B站新版播放器选择器
                selectors = [
                    "css:.bpx-player-container",
                    "css:#bilibili-player",
                    "css:.bilibili-player-video-wrap",
                    "css:video",
                    "css:[class*='player']",
                ]

                for sel in selectors:
                    try:
                        el = page.ele(sel, timeout=3)
                        if el:
                            player = el
                            break
                    except Exception:
                        continue

                # 点击播放器区域确保开始播放
                if player:
                    try:
                        player.click()
                        time.sleep(0.5)
                    except Exception:
                        pass

                # 尝试点击播放按钮
                play_btns = [
                    "css:.bpx-player-ctrl-play",
                    "css:.bilibili-player-video-btn",
                    "css:[class*='play'][class*='btn']",
                ]
                for sel in play_btns:
                    try:
                        btn = page.ele(sel, timeout=1)
                        if btn and btn.is_displayed():
                            btn.click()
                            time.sleep(0.5)
                            break
                    except Exception:
                        continue

                # 模拟真实观看 - 随机滚动页面
                watch_time = random.randint(*WATCH_TIME_RANGE)
                elapsed_watch = 0
                scroll_count = 0
                while elapsed_watch < watch_time:
                    step = random.uniform(2, 4)
                    time.sleep(step)
                    elapsed_watch += step
                    scroll_count += 1
                    # 偶尔滚动一下，模拟真人行为
                    if scroll_count % 3 == 0:
                        try:
                            page.scroll.down(random.randint(100, 300))
                            time.sleep(0.5)
                        except Exception:
                            pass

                success += 1

            except Exception as e:
                fail += 1
                print(f"\r  [!] 第{i}次异常: {e}")

            # 进度显示
            elapsed_total = time.time() - start_time
            speed = i / elapsed_total if elapsed_total > 0 else 0
            eta = (TARGET_COUNT - i) / speed if speed > 0 else 0
            bar_len = 30
            filled = int(bar_len * i / TARGET_COUNT)
            bar = "=" * filled + "-" * (bar_len - filled)

            print(
                f"\r  [{bar}] {i}/{TARGET_COUNT} "
                f"| 成功:{success} 失败:{fail} "
                f"| {speed:.1f}/min 剩余{eta/60:.1f}m",
                end="", flush=True
            )

            # 随机间隔后下一个
            time.sleep(random.uniform(1, 3))

    finally:
        # 关闭浏览器
        try:
            page.quit()
        except Exception:
            pass

    total_time = time.time() - start_time
    print(f"\n\n  {'='*40}")
    print(f"  完成! 耗时: {total_time/60:.1f}分钟 ({total_time:.0f}秒)")
    print(f"  成功: {success} | 失败: {fail}")
    print(f"  平均每个: {total_time/max(success,1):.1f}秒")
    print(f"{'='*40}\n")


if __name__ == "__main__":
    run()
