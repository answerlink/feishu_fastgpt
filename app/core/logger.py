import logging
import sys
import os
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

# 应用专用文件处理器缓存
_app_file_handlers = {}

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

def get_app_file_handler(app_id: str, app_name: str):
    """获取应用专用文件处理器"""
    global _app_file_handlers
    
    handler_key = app_id
    if handler_key not in _app_file_handlers:
        # 使用应用名称作为日志文件名，去除特殊字符
        safe_app_name = "".join(c for c in app_name if c.isalnum() or c in ('-', '_')).strip()
        if not safe_app_name:
            safe_app_name = app_id
        
        app_log_file = log_dir / f"app_{safe_app_name}_{app_id}.log"
        
        app_handler = RotatingFileHandler(
            app_log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8"
        )
        app_handler.setFormatter(log_format)
        _app_file_handlers[handler_key] = app_handler
    
    return _app_file_handlers[handler_key]

def setup_logger(name: str, app_id: str = None, app_name: str = None) -> logging.Logger:
    """设置日志记录器
    
    Args:
        name: 日志器名称
        app_id: 应用ID，如果提供则为该应用创建专用日志文件
        app_name: 应用名称，用于生成日志文件名
    """
    logger = logging.getLogger(name)
    
    # 避免重复添加处理器
    if logger.handlers:
        return logger
        
    logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    # 全局文件处理器（所有日志都会写入）
    logger.addHandler(get_global_file_handler())
    
    # 如果指定了应用ID，还要添加应用专用的文件处理器
    if app_id and app_name:
        app_handler = get_app_file_handler(app_id, app_name)
        logger.addHandler(app_handler)

    return logger

def setup_app_logger(name: str, app_id: str, app_name: str) -> logging.Logger:
    """为特定应用设置专用日志记录器"""
    return setup_logger(name, app_id, app_name)

def get_app_log_files():
    """获取所有应用日志文件列表"""
    app_log_files = []
    
    # 扫描logs目录中的应用日志文件
    for log_file in log_dir.glob("app_*.log"):
        # 解析文件名获取应用信息
        filename = log_file.stem  # 去掉.log扩展名
        if filename.startswith("app_"):
            # 尝试从文件名中提取应用名称和ID
            # 文件名格式：app_{app_name}_{app_id}.log
            # app_id是固定格式：cli_开头的字符串
            parts = filename[4:]  # 去掉"app_"前缀
            
            # 查找最后一个符合app_id格式的部分（cli_开头且包含下划线）
            import re
            app_id_pattern = r'(cli_[a-zA-Z0-9_]+)$'
            match = re.search(app_id_pattern, parts)
            
            if match:
                app_id = match.group(1)
                # app_name是app_id前面的部分（去掉最后的下划线）
                app_name_part = parts[:match.start()].rstrip('_')
                
                # 从配置中获取真实的应用名称
                real_app_name = None
                for app in settings.FEISHU_APPS:
                    if app.app_id == app_id:
                        real_app_name = app.app_name
                        break
                
                display_name = f"{real_app_name}日志" if real_app_name else f"{app_name_part}日志"
                
                app_log_files.append({
                    "file_path": str(log_file),
                    "app_id": app_id,
                    "app_name": real_app_name or app_name_part,
                    "display_name": display_name
                })
    
    return app_log_files

# 检查是否在单应用模式
single_app_mode = os.environ.get('FEISHU_SINGLE_APP_MODE', 'false').lower() == 'true'
target_app_id = os.environ.get('FEISHU_SINGLE_APP_ID') if single_app_mode else None

# 创建主日志记录器
if single_app_mode and target_app_id:
    # 单应用模式：为该应用创建专用日志
    target_app = None
    for app in settings.FEISHU_APPS:
        if app.app_id == target_app_id:
            target_app = app
            break
    
    if target_app:
        logger = setup_app_logger("feishu-plus", target_app.app_id, target_app.app_name)
    else:
        logger = setup_logger("feishu-plus")
else:
    # 多应用模式：只使用全局日志
    logger = setup_logger("feishu-plus") 