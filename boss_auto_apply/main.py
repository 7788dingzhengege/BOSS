# BOSS直聘自动投递 - 主程序入口

import sys
import os
import logging

if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# 确保在项目根目录运行
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from applier import JobApplier
from config import (
    KEYWORDS, CITIES, MAX_DAILY_APPLIES,
    TEST_LIMIT, DELAY_RANGE, FILTER_CONFIG,
)


def _setup_logging():
    """配置日志：控制台 + 文件输出"""
    os.makedirs("data", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("data/applier.log", encoding='utf-8'),
        ],
    )


def print_banner():
    print()
    print("  ╔══════════════════════════════════════╗")
    print("  ║     BOSS 直聘 自动投递工具 v1.0      ║")
    print("  ╠══════════════════════════════════════╣")
    print("  ║  搜索 → 筛选 → 沟通 → 记录          ║")
    print("  ╚══════════════════════════════════════╝")
    print()


def interactive_config():
    """交互式参数配置（循环重设，避免递归）"""
    while True:
        print("=" * 50)
        print("  ⚙️  参数设置（直接回车使用默认值）")
        print("=" * 50)

        # 关键词
        default_kw = ", ".join(KEYWORDS[:3]) + ("..." if len(KEYWORDS) > 3 else "")
        kw_input = input(f"  [1] 搜索关键词 [{default_kw}]: ").strip()
        keywords = [k.strip() for k in kw_input.split(",") if k.strip()] if kw_input else KEYWORDS

        # 城市
        default_city = CITIES[0] if CITIES else "北京"
        city_input = input(f"  [2] 目标城市 [{default_city}]: ").strip()
        cities = [city_input] if city_input else [default_city]

        # 投递数量
        max_input = input(f"  [3] 投递数量 [{MAX_DAILY_APPLIES}]: ").strip()
        max_applies = int(max_input) if max_input.isdigit() else MAX_DAILY_APPLIES

        # 操作速度
        speed_input = input(f"  [4] 速度 (1=快/2=正常/3=慢) [1]: ").strip()
        if speed_input == "2":
            delay_range = (3, 6)
        elif speed_input == "3":
            delay_range = (5, 10)
        else:
            delay_range = (1, 2)

        # 排除词
        exclude_default = ", ".join(FILTER_CONFIG.get("exclude_keywords", [])[:4])
        excl_input = input(f"  [5] 排除词(逗号分隔) [{exclude_default}]: ").strip()
        exclude_keywords = [e.strip() for e in excl_input.split(",") if e.strip()] if excl_input \
            else FILTER_CONFIG.get("exclude_keywords", [])

        # 是否只投实习
        intern_input = input(f"  [6] 只投实习岗? (y/n) [y]: ").strip().lower()
        internship_only = intern_input != "n"

        # 是否需要登录确认
        login_input = input(f"  [7] 已登录?(跳过扫码等待) (y/n) [y]: ").strip().lower()
        skip_login = login_input != "n"

        # 是否启用 Agent 智能筛选
        agent_input = input(f"  [8] 启用Agent智能筛选? (y/n) [n]: ").strip().lower()
        agent_filter = agent_input == "y"

        print()
        print("-" * 50)
        print("  📋 当前配置：")
        print(f"     关键词: {', '.join(keywords)}")
        print(f"     城市:   {cities[0]}")
        print(f"     数量:   {max_applies} 个")
        print(f"     间隔:   {delay_range[0]}-{delay_range[1]} 秒/个")
        print(f"     实习:   {'是' if internship_only else '否'}")
        print(f"     排除:   {', '.join(exclude_keywords[:5])}")
        print(f"     登录:   {'已登录，直接开始' if skip_login else '需要扫码'}")
        print(f"     Agent: {'开启' if agent_filter else '关闭'}")

        confirm = input("\n  ✅ 确认开始? (回车=确认 / r=重新设置): ").strip().lower()

        if confirm == "r":
            print()
            continue

        # 返回覆盖后的配置字典
        return {
            "keywords": keywords,
            "cities": cities,
            "max_daily_applies": max_applies,
            "test_limit": None,
            "delay_range": delay_range,
            "internship_only": internship_only,
            "exclude_keywords": exclude_keywords,
            "skip_login": skip_login,
            "agent_filter": agent_filter,
        }


def main():
    _setup_logging()
    print_banner()

    # 交互式获取配置
    cfg = interactive_config()

    # 通过实例属性传递配置（不再修改全局变量）
    applier = JobApplier()
    applier.skip_login = cfg["skip_login"]
    applier.keywords = cfg["keywords"]
    applier.max_daily_applies = cfg["max_daily_applies"]
    applier.test_limit = cfg["test_limit"]
    applier.delay_range = cfg["delay_range"]
    applier.exclude_keywords = cfg["exclude_keywords"]
    applier.internship_only = cfg["internship_only"]
    applier.interactive = True  # CLI 模式等待回车
    applier.agent_filter_enabled = cfg.get("agent_filter", False)
    applier.run()


if __name__ == "__main__":
    main()
