import logging
import sys
from logging.handlers import RotatingFileHandler

def setup_logging():
    """初始化日志配置，输出到控制台和文件"""
    log_format = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # 根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    root_logger.addHandler(console_handler)

    # 文件处理器（可选，按需调整路径）
    # file_handler = RotatingFileHandler("app.log", maxBytes=10_000_000, backupCount=5)
    # file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    # root_logger.addHandler(file_handler)

    return root_logger

logger = setup_logging()