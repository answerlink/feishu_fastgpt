from fastapi import APIRouter, Depends, HTTPException
from app.services.feishu_callback import FeishuCallbackService
from app.core.config import settings
from typing import Dict, List, Optional
from pydantic import BaseModel

router = APIRouter()

# 请求模型
class CallbackServiceRequest(BaseModel):
    app_id: str

# 响应模型
class CallbackServiceStatus(BaseModel):
    app_id: str
    app_name: Optional[str] = ""
    status: str

class CallbackServiceListResponse(BaseModel):
    services: List[CallbackServiceStatus]

# 获取回调服务状态
@router.get("/status", response_model=CallbackServiceListResponse)
def get_callback_status():
    """获取所有飞书回调服务状态"""
    callback_service = FeishuCallbackService()
    
    # 获取当前运行的服务状态
    current_status = callback_service.get_status()
    services = []
    
    # 如果有当前正在运行的服务，添加到列表
    if current_status.get("app_id"):
        services.append(CallbackServiceStatus(
            app_id=current_status.get("app_id", ""),
            app_name=current_status.get("app_name", ""),
            status=current_status.get("status", "unknown")
        ))
    
    # 添加所有配置的应用
    for app in settings.FEISHU_APPS:
        # 如果应用已经在列表中（正在运行），则跳过
        if any(s.app_id == app.app_id for s in services):
            continue
            
        # 判断该应用的状态
        if current_status.get("app_id") == app.app_id:
            status = current_status.get("status", "unknown")
        else:
            status = "not_started"
            
        services.append(CallbackServiceStatus(
            app_id=app.app_id,
            app_name=app.app_name,
            status=status
        ))
    
    return {"services": services}

# 启动单个应用的回调服务
@router.post("/start", response_model=CallbackServiceStatus)
def start_callback_service(request: CallbackServiceRequest):
    """启动指定应用的飞书回调服务"""
    callback_service = FeishuCallbackService()
    
    # 查找应用配置
    app_config = next((app for app in settings.FEISHU_APPS if app.app_id == request.app_id), None)
    if not app_config:
        raise HTTPException(status_code=404, detail=f"未找到应用配置: {request.app_id}")
    
    # 启动回调服务
    success = callback_service.start_callback_service(app_config.app_id, app_config.app_secret, app_config.app_name)
    
    # 获取状态
    status_info = callback_service.get_status()
    
    # 确定状态值
    if success and status_info.get("app_id") == request.app_id:
        status = status_info.get("status", "unknown")
    else:
        status = "failed"
    
    return CallbackServiceStatus(
        app_id=request.app_id,
        app_name=app_config.app_name,
        status=status
    )

# 重启单个应用的回调服务
@router.post("/restart", response_model=CallbackServiceStatus)
def restart_callback_service(request: CallbackServiceRequest):
    """重启指定应用的飞书回调服务"""
    callback_service = FeishuCallbackService()
    
    # 查找应用配置
    app_config = next((app for app in settings.FEISHU_APPS if app.app_id == request.app_id), None)
    if not app_config:
        raise HTTPException(status_code=404, detail=f"未找到应用配置: {request.app_id}")
    
    # 先尝试停止服务
    callback_service.stop_callback_service()
    
    # 然后重新启动服务
    success = callback_service.start_callback_service(app_config.app_id, app_config.app_secret, app_config.app_name)
    
    # 获取状态
    status_info = callback_service.get_status()
    
    # 确定状态值
    if success and status_info.get("app_id") == request.app_id:
        status = status_info.get("status", "unknown")
    else:
        status = "failed"
    
    return CallbackServiceStatus(
        app_id=request.app_id,
        app_name=app_config.app_name,
        status=status
    )

# 停止单个应用的回调服务
@router.post("/stop", response_model=CallbackServiceStatus)
def stop_callback_service(request: CallbackServiceRequest):
    """停止指定应用的飞书回调服务"""
    callback_service = FeishuCallbackService()
    
    # 查找应用配置
    app_config = next((app for app in settings.FEISHU_APPS if app.app_id == request.app_id), None)
    if not app_config:
        raise HTTPException(status_code=404, detail=f"未找到应用配置: {request.app_id}")
    
    # 获取当前状态，检查是否是指定的应用在运行
    current_status = callback_service.get_status()
    if current_status.get("app_id") == request.app_id:
        # 如果是，则停止它
        callback_service.stop_callback_service()
        status = "stopped"
    else:
        # 如果不是，则标记为未启动
        status = "not_started"
    
    return CallbackServiceStatus(
        app_id=request.app_id,
        app_name=app_config.app_name,
        status=status
    )

# 启动所有应用的回调服务
@router.post("/start-all", response_model=CallbackServiceListResponse)
def start_all_callback_services():
    """启动所有应用的飞书回调服务（仅启动第一个应用）"""
    callback_service = FeishuCallbackService()
    callback_service.start_callback_services()
    
    # 获取所有状态
    return get_callback_status()

# 停止所有应用的回调服务
@router.post("/stop-all", response_model=CallbackServiceListResponse)
def stop_all_callback_services():
    """停止所有应用的飞书回调服务"""
    callback_service = FeishuCallbackService()
    callback_service.stop_all_callback_services()
    
    # 获取所有状态
    return get_callback_status() 