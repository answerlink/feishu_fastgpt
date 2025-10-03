from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi import HTTPException
from contextlib import asynccontextmanager
from app.core.config import settings
from app.api.v1.api import api_router
from app.db.session import init_db
from app.core.multi_app_manager import multi_app_manager
from app.core.scheduler import scheduler
from fastapi.staticfiles import StaticFiles
import os
from pathlib import Path

# 导入主控前端路由
from app.api.v1.endpoints.main_frontend import router as main_frontend_router

# 导入所有模型，确保它们被注册到Base.metadata中
from app.models import feishu_token, doc_subscription, space_subscription, user_chat_session, user_search_preference, user_memory

# 创建临时目录和静态文件目录
os.makedirs(os.path.join(os.getcwd(), "temp"), exist_ok=True)
os.makedirs(os.path.join(os.getcwd(), "temp", "images"), exist_ok=True)
os.makedirs(os.path.join(os.getcwd(), "static"), exist_ok=True)
os.makedirs(os.path.join(os.getcwd(), "static", "images"), exist_ok=True)
os.makedirs(os.path.join(os.getcwd(), "static", "files"), exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    await init_db()
    
    # 启动多应用管理器（为每个飞书app启动独立进程）
    multi_app_manager.start_all_apps()
    
    # 启动主进程的订阅定时任务调度器（用于全局任务协调）
    scheduler.start()
    
    yield
    
    # 关闭时执行
    # 停止所有应用进程
    multi_app_manager.stop_all_apps()
    
    # 停止订阅定时任务调度器
    scheduler.shutdown()

app = FastAPI(
    title=f"{settings.APP_NAME} - 主控进程",
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

# 添加短路径图片访问支持
@app.get("/img/{filename}")
async def get_image_short_path(filename: str):
    """短路径获取图片文件
    
    Args:
        filename: 图片文件名（包含扩展名）
        
    Returns:
        FileResponse: 图片文件响应
    """
    try:
        # 构建文件路径
        file_path = Path("static") / "images" / filename
        
        # 检查文件是否存在
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="图片文件不存在")
        
        # 检查文件是否在允许的目录内（安全检查）
        try:
            file_path.resolve().relative_to(Path("static").resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="非法的文件路径")
        
        # 根据文件扩展名设置媒体类型
        extension = file_path.suffix.lower()
        media_type_map = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.svg': 'image/svg+xml'
        }
        media_type = media_type_map.get(extension, 'application/octet-stream')
        
        return FileResponse(
            path=str(file_path),
            media_type=media_type,
            filename=filename
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="服务器内部错误")

# 注册API路由
app.include_router(api_router, prefix=settings.API_V1_STR)

# 注册主控前端路由（放在最后，避免拦截API路由）
app.include_router(main_frontend_router)

if __name__ == "__main__":
    import uvicorn
    # 主控进程使用8000端口，子进程使用系统分配端口
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False) 