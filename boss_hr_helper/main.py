# BOSS直聘HR助手 - 入口文件

import sys
import os
import logging
from datetime import datetime

if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from config import LOG_FILE, LOG_LEVEL, DATA_DIR


def setup_logging():
    """配置日志"""
    os.makedirs(DATA_DIR, exist_ok=True)

    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler(sys.stdout),
        ]
    )


def main():
    setup_logging()
    logger = logging.getLogger("boss_hr")
    logger.info("=" * 50)
    logger.info("BOSS直聘 HR助手 启动")
    logger.info("启动时间: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("=" * 50)

    from gui import HRHelperGUI
    app = HRHelperGUI()
    app.run()


if __name__ == "__main__":
    main()
