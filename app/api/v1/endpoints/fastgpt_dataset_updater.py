from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.core.config import settings
from app.core.logger import setup_logger
from app.utils.fastgpt_dataset_updater import FastGPTDatasetUpdater

router = APIRouter()
logger = setup_logger("fastgpt_dataset_updater_api")

class UpdateDescriptionRequest(BaseModel):
    """更新描述请求模型"""
    app_id: str
    skip_existing: Optional[bool] = True  # 是否跳过已有描述的知识库，False表示全量覆盖更新
    dry_run: Optional[bool] = False  # 是否仅预览，不实际更新

class UpdateDescriptionResponse(BaseModel):
    """更新描述响应模型"""
    code: int
    message: str
    data: Optional[dict] = None

@router.post("/update-dataset-descriptions", response_model=UpdateDescriptionResponse)
async def update_dataset_descriptions(request: UpdateDescriptionRequest):
    """为FastGPT中的知识库批量生成和更新描述
    
    扫描指定飞书app下的所有知识库，并根据知识库中的文件列表生成描述
    
    Args:
        request: 更新请求，包含以下参数：
                - app_id: 应用ID
                - skip_existing: 是否跳过已有描述的知识库，默认True
                  * True: 如果知识库已有描述就跳过
                  * False: 全量覆盖更新所有知识库的描述
                - dry_run: 是否仅预览，默认False
                  * True: 只扫描和分析，不实际更新
                  * False: 实际执行更新操作
        
    Returns:
        UpdateDescriptionResponse: 更新结果
    """
    try:
        strategy_text = "跳过已有描述" if request.skip_existing else "全量覆盖更新"
        mode_text = "预览模式" if request.dry_run else "更新模式"
        logger.info(f"收到知识库描述更新请求 - app_id: {request.app_id}, 策略: {strategy_text}, 模式: {mode_text}")
        
        # 验证app_id是否存在
        app_config = next((app for app in settings.FEISHU_APPS if app.app_id == request.app_id), None)
        if not app_config:
            logger.error(f"未找到应用配置: {request.app_id}")
            return UpdateDescriptionResponse(
                code=400,
                message=f"未找到应用配置: {request.app_id}",
                data=None
            )
        
        # 检查是否配置了FastGPT
        if not app_config.fastgpt_url or not app_config.fastgpt_key:
            logger.error(f"应用 {request.app_id} 未配置FastGPT相关参数")
            return UpdateDescriptionResponse(
                code=400,
                message=f"应用 {request.app_id} 未配置FastGPT相关参数",
                data=None
            )
        
        # 检查摘要LLM配置
        if not all([
            app_config.summary_llm_api_url,
            app_config.summary_llm_api_key,
            app_config.summary_llm_model
        ]):
            logger.error(f"应用 {request.app_id} 未配置摘要LLM相关参数")
            return UpdateDescriptionResponse(
                code=400,
                message=f"应用 {request.app_id} 未配置摘要LLM相关参数，无法生成知识库描述",
                data=None
            )
        
        # 如果是预览模式，记录日志
        if request.dry_run:
            logger.warning("🔍 DRY RUN 模式：将只扫描和分析，不会实际更新任何描述")
        
        # 创建更新工具并执行更新
        updater = FastGPTDatasetUpdater(
            request.app_id, 
            skip_existing=request.skip_existing, 
            dry_run=request.dry_run
        )
        
        try:
            result = await updater.update_dataset_descriptions()
            
            logger.info(f"知识库描述更新完成 - app_id: {request.app_id}, 结果: {result.get('message')}")
            
            return UpdateDescriptionResponse(
                code=result.get("code", 500),
                message=result.get("message", "未知错误"),
                data=result.get("data")
            )
            
        finally:
            # 确保更新工具正确关闭
            await updater.close()
            
    except Exception as e:
        error_msg = f"知识库描述更新过程中发生异常: {str(e)}"
        logger.error(error_msg)
        
        return UpdateDescriptionResponse(
            code=500,
            message=error_msg,
            data=None
        )

@router.get("/description-update-status/{app_id}")
async def get_description_update_status(app_id: str):
    """获取应用的知识库描述更新状态和配置信息
    
    Args:
        app_id: 应用ID
        
    Returns:
        dict: 状态信息
    """
    try:
        logger.info(f"查询知识库描述更新状态 - app_id: {app_id}")
        
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
        has_summary_llm_config = bool(
            app_config.summary_llm_api_url and 
            app_config.summary_llm_api_key and 
            app_config.summary_llm_model
        )
        
        status_data = {
            "app_id": app_id,
            "app_name": app_config.app_name or "未命名应用",
            "has_fastgpt_config": has_fastgpt_config,
            "has_summary_llm_config": has_summary_llm_config,
            "fastgpt_url": app_config.fastgpt_url if has_fastgpt_config else None,
            "summary_llm_model": app_config.summary_llm_model if has_summary_llm_config else None,
            "dataset_sync_enabled": app_config.dataset_sync,
            "ready_for_update": has_fastgpt_config and has_summary_llm_config and app_config.dataset_sync
        }
        
        return {
            "code": 200,
            "message": "查询成功",
            "data": status_data
        }
        
    except Exception as e:
        error_msg = f"查询知识库描述更新状态异常: {str(e)}"
        logger.error(error_msg)
        
        return {
            "code": 500,
            "message": error_msg,
            "data": None
        } 