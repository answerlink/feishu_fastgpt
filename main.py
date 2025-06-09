from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.config import settings
from app.api.v1.api import api_router
from app.db.session import init_db
from app.services.feishu_callback import FeishuCallbackService
from app.core.scheduler import scheduler
from fastapi.staticfiles import StaticFiles
import os

# 导入所有模型，确保它们被注册到Base.metadata中
from app.models import feishu_token, doc_subscription, space_subscription

# 创建临时目录和静态文件目录
os.makedirs(os.path.join(os.getcwd(), "temp"), exist_ok=True)
os.makedirs(os.path.join(os.getcwd(), "temp", "images"), exist_ok=True)
os.makedirs(os.path.join(os.getcwd(), "static"), exist_ok=True)
os.makedirs(os.path.join(os.getcwd(), "static", "images"), exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    await init_db()
    
    # 启动飞书回调服务
    callback_service = FeishuCallbackService()
    callback_service.start_callback_services()
    
    # 启动订阅定时任务调度器
    scheduler.start()
    
    yield
    
    # 关闭时执行
    # 停止飞书回调服务
    callback_service = FeishuCallbackService()
    callback_service.stop_all_callback_services()
    
    # 停止订阅定时任务调度器
    scheduler.shutdown()

app = FastAPI(
    title=settings.APP_NAME,
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

# 挂载静态文件目录，使图片可访问
app.mount("/static", StaticFiles(directory="static"), name="static")

# 注册路由
app.include_router(api_router, prefix=settings.API_V1_STR)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False) 