#!/usr/bin/env python3
"""
单飞书应用工作进程

这个脚本在独立进程中运行，只处理环境变量指定的单个飞书应用。
每个应用进程运行完整的应用实例，但回调服务只处理指定的app_id。
"""

import os
import sys
import signal
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# 添加项目根目录到Python路径
sys.path.insert(0, os.getcwd())

from app.core.config import settings
from app.api.v1.api import api_router
from app.db.session import init_db
from app.services.feishu_callback import FeishuCallbackService
from app.core.scheduler import scheduler
from fastapi.staticfiles import StaticFiles
from app.core.logger import setup_app_logger

# 导入所有模型
from app.models import feishu_token, doc_subscription, space_subscription

# 获取环境变量中指定的app_id
TARGET_APP_ID = os.environ.get('FEISHU_SINGLE_APP_ID')
SINGLE_APP_MODE = os.environ.get('FEISHU_SINGLE_APP_MODE', 'false').lower() == 'true'
ASSIGNED_PORT = os.environ.get('FEISHU_SINGLE_APP_PORT')

if not TARGET_APP_ID or not SINGLE_APP_MODE:
    print("错误: 请设置 FEISHU_SINGLE_APP_ID 和 FEISHU_SINGLE_APP_MODE 环境变量")
    sys.exit(1)

if not ASSIGNED_PORT:
    print("错误: 请设置 FEISHU_SINGLE_APP_PORT 环境变量")
    sys.exit(1)

try:
    port = int(ASSIGNED_PORT)
except ValueError:
    print(f"错误: FEISHU_SINGLE_APP_PORT 必须是有效的端口号，当前值: {ASSIGNED_PORT}")
    sys.exit(1)

# 查找目标应用配置
target_app = None
for app in settings.FEISHU_APPS:
    if app.app_id == TARGET_APP_ID:
        target_app = app
        break

if not target_app:
    print(f"错误: 未找到应用配置 {TARGET_APP_ID}")
    sys.exit(1)

# 为该应用创建专用日志记录器
logger = setup_app_logger(f"single_app_worker_{TARGET_APP_ID}", target_app.app_id, target_app.app_name)
logger.info(f"单应用工作进程启动: {target_app.app_name} ({TARGET_APP_ID})")

# 创建临时目录和静态文件目录
os.makedirs(os.path.join(os.getcwd(), "temp"), exist_ok=True)
os.makedirs(os.path.join(os.getcwd(), "temp", "images"), exist_ok=True)
os.makedirs(os.path.join(os.getcwd(), "static"), exist_ok=True)
os.makedirs(os.path.join(os.getcwd(), "static", "images"), exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info(f"开始启动应用生命周期管理: {target_app.app_name}")
    
    try:
        # 启动时执行
        logger.info("正在初始化数据库...")
        await init_db()
        logger.info("数据库初始化完成")
        
        # 启动指定应用的飞书回调服务
        logger.info(f"正在启动飞书回调服务: {target_app.app_name}")
        callback_service = FeishuCallbackService()
        success = callback_service.start_callback_service(
            target_app.app_id, 
            target_app.app_secret, 
            target_app.app_name
        )
        
        if not success:
            logger.error(f"启动回调服务失败: {target_app.app_name}")
        else:
            logger.info(f"回调服务启动成功: {target_app.app_name}")
        
        # 启动订阅定时任务调度器
        logger.info("正在启动订阅定时任务调度器...")
        scheduler.start()
        logger.info("订阅定时任务调度器启动完成")
        
        logger.info(f"应用生命周期启动完成: {target_app.app_name}")
        
        yield
        
    except Exception as e:
        logger.error(f"应用启动失败: {str(e)}")
        import traceback
        logger.error(f"错误详情: {traceback.format_exc()}")
        raise
    finally:
        # 关闭时执行
        logger.info(f"开始关闭应用: {target_app.app_name}")
        try:
            # 停止飞书回调服务
            callback_service = FeishuCallbackService()
            callback_service.stop_callback_service()
            logger.info("飞书回调服务已停止")
            
            # 停止订阅定时任务调度器
            scheduler.shutdown()
            logger.info("订阅定时任务调度器已停止")
            
            logger.info(f"应用已正常关闭: {target_app.app_name}")
        except Exception as e:
            logger.error(f"应用关闭时出错: {str(e)}")

# 创建FastAPI应用
app = FastAPI(
    title=f"{settings.APP_NAME} - {target_app.app_name}",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# 设置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")

# 注册路由
app.include_router(api_router, prefix=settings.API_V1_STR)

# 注册子应用前端路由
from app.api.v1.endpoints.app_frontend import router as app_frontend_router
app.include_router(app_frontend_router)

# 信号处理
def signal_handler(sig, frame):
    """处理停止信号"""
    logger.info(f"收到停止信号 {sig}，正在关闭应用: {target_app.app_name}")
    sys.exit(0)

# 注册信号处理器
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

if __name__ == "__main__":
    import uvicorn
    
    try:
        logger.info(f"启动应用服务: {target_app.app_name}, 端口: {port}")
        logger.info(f"应用配置: AI Chat启用={target_app.aichat_enable}")
        
        # 使用字符串形式的app引用确保lifespan正常工作
        uvicorn.run(
            "single_app_worker:app",
            host="0.0.0.0",
            port=port,
            log_level="info",
            lifespan="on"  # 显式启用lifespan
        )
    except Exception as e:
        logger.error(f"应用启动失败: {str(e)}")
        import traceback
        logger.error(f"错误详情: {traceback.format_exc()}")
        sys.exit(1) 