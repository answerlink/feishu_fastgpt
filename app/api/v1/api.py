from fastapi import APIRouter
from app.api.v1.endpoints import test, wiki, document, scheduler, logs, static, multi_app, fastgpt_cleaner, fastgpt_dataset_updater, group_chat_stats, user_memory, collection_viewer

api_router = APIRouter()

# 注册测试路由
api_router.include_router(test.router, prefix="/test", tags=["test"])

# 注册知识空间路由
api_router.include_router(wiki.router, prefix="/wiki", tags=["wiki"])

# 注册文档管理路由
api_router.include_router(document.router, prefix="/documents", tags=["documents"])

# 注册调度器管理路由
api_router.include_router(scheduler.router, prefix="/scheduler", tags=["scheduler"])

# 注册日志查看路由
api_router.include_router(logs.router, prefix="/logs", tags=["logs"])

# 注册静态文件API路由
api_router.include_router(static.router, prefix="/static", tags=["static"])

# 注册多应用管理路由
api_router.include_router(multi_app.router, prefix="/multi-app", tags=["multi-app"])

# 注册FastGPT清理工具路由
api_router.include_router(fastgpt_cleaner.router, prefix="/fastgpt-cleaner", tags=["fastgpt-cleaner"])

# 注册FastGPT知识库描述更新工具路由
api_router.include_router(fastgpt_dataset_updater.router, prefix="/fastgpt-dataset-updater", tags=["fastgpt-dataset-updater"])

# 注册群聊统计信息路由
api_router.include_router(group_chat_stats.router, prefix="/group-chat", tags=["group-chat"])

# 注册用户记忆管理路由
api_router.include_router(user_memory.router, prefix="/user-memory", tags=["user-memory"])

# 注册知识块查看器路由
api_router.include_router(collection_viewer.router, prefix="/collection-viewer", tags=["collection-viewer"])

# 在这里导入和注册其他路由
# from .endpoints import auth
# api_router.include_router(auth.router, prefix="/auth", tags=["auth"]) 