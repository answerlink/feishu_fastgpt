from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.core.config import settings
from app.core.logger import setup_logger
from app.utils.fastgpt_cleaner import FastGPTCleaner

router = APIRouter()
logger = setup_logger("fastgpt_cleaner_api")

class CleanupRequest(BaseModel):
    """清理请求模型"""
    app_id: str
    dry_run: Optional[bool] = False  # 是否仅预览，不实际删除

class CleanupResponse(BaseModel):
    """清理响应模型"""
    code: int
    message: str
    data: Optional[dict] = None

@router.post("/clean-duplicate-collections", response_model=CleanupResponse)
async def clean_duplicate_collections(request: CleanupRequest):
    """清理FastGPT中重复的collections
    
    清理规则：
    1. 递归遍历所有可访问的文件夹、知识库（dataset）、文件（collection）
    2. 在一个知识库内发现collection有重名时，保留最新时间的，删除其他的
    
    Args:
        request: 清理请求，包含app_id和dry_run参数
        
    Returns:
        CleanupResponse: 清理结果
    """
    try:
        logger.info(f"收到FastGPT清理请求 - app_id: {request.app_id}, dry_run: {request.dry_run}")
        
        # 验证app_id是否存在
        app_config = next((app for app in settings.FEISHU_APPS if app.app_id == request.app_id), None)
        if not app_config:
            logger.error(f"未找到应用配置: {request.app_id}")
            return CleanupResponse(
                code=400,
                message=f"未找到应用配置: {request.app_id}",
                data=None
            )
        
        # 检查是否配置了FastGPT
        if not app_config.fastgpt_url or not app_config.fastgpt_key:
            logger.error(f"应用 {request.app_id} 未配置FastGPT相关参数")
            return CleanupResponse(
                code=400,
                message=f"应用 {request.app_id} 未配置FastGPT相关参数",
                data=None
            )
        
        # 如果是预览模式，记录日志
        if request.dry_run:
            logger.warning("🔍 DRY RUN 模式：将只扫描和分析，不会实际删除任何文件")
        
        # 创建清理工具并执行清理
        cleaner = FastGPTCleaner(request.app_id, dry_run=request.dry_run)
        
        try:
            result = await cleaner.clean_duplicate_collections()
            
            logger.info(f"FastGPT清理完成 - app_id: {request.app_id}, 结果: {result.get('message')}")
            
            return CleanupResponse(
                code=result.get("code", 500),
                message=result.get("message", "未知错误"),
                data=result.get("data")
            )
            
        finally:
            # 确保清理工具正确关闭
            await cleaner.close()
            
    except Exception as e:
        error_msg = f"FastGPT清理过程中发生异常: {str(e)}"
        logger.error(error_msg)
        
        return CleanupResponse(
            code=500,
            message=error_msg,
            data=None
        )

@router.get("/cleanup-status/{app_id}")
async def get_cleanup_status(app_id: str):
    """获取应用的FastGPT清理状态和配置信息
    
    Args:
        app_id: 应用ID
        
    Returns:
        dict: 状态信息
    """
    try:
        logger.info(f"查询FastGPT清理状态 - app_id: {app_id}")
        
        # 验证app_id是否存在
        app_config = next((app for app in settings.FEISHU_APPS if app.app_id == app_id), None)
        if not app_config:
            logger.error(f"未找到应用配置: {app_id}")
            return {
                "code": 400,
                "message": f"未找到应用配置: {app_id}",
                "data": None
            }
        
        # 获取配置状态
        has_fastgpt_config = bool(app_config.fastgpt_url and app_config.fastgpt_key)
        
        status_data = {
            "app_id": app_id,
            "app_name": app_config.app_name or "未命名应用",
            "has_fastgpt_config": has_fastgpt_config,
            "fastgpt_url": app_config.fastgpt_url if has_fastgpt_config else None,
            "dataset_sync_enabled": app_config.dataset_sync,
            "ready_for_cleanup": has_fastgpt_config and app_config.dataset_sync
        }
        
        return {
            "code": 200,
            "message": "查询成功",
            "data": status_data
        }
        
    except Exception as e:
        error_msg = f"查询FastGPT清理状态异常: {str(e)}"
        logger.error(error_msg)
        
        return {
            "code": 500,
            "message": error_msg,
            "data": None
        } 