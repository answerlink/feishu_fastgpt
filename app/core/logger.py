import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from app.core.config import settings

# 创建logs目录
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

# 日志格式
log_format = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# 全局文件处理器（所有日志都写入同一个文件）
_global_file_handler = None

def get_global_file_handler():
    """获取全局文件处理器"""
    global _global_file_handler
    if _global_file_handler is None:
        _global_file_handler = RotatingFileHandler(
            log_dir / "feishu-plus.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8"
        )
        _global_file_handler.setFormatter(log_format)
    return _global_file_handler

def setup_logger(name: str) -> logging.Logger:
    """设置日志记录器"""
    logger = logging.getLogger(name)
    
    # 避免重复添加处理器
    if logger.handlers:
        return logger
        
    logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    # 使用全局文件处理器
    logger.addHandler(get_global_file_handler())

    return logger

# 创建主日志记录器
logger = setup_logger("feishu-plus") 