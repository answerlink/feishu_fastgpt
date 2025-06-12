from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict
import os
from pydantic import BaseModel
from app.core.scheduler import scheduler
from app.core.config import settings

router = APIRouter()

class SchedulerResponse(BaseModel):
    code: int
    msg: str

@router.get("/status", response_model=SchedulerResponse)
async def get_scheduler_status():
    """获取调度器运行状态"""
    status = scheduler._running
    
    # 检查单应用模式配置
    single_app_mode = os.environ.get('FEISHU_SINGLE_APP_MODE', 'false').lower() == 'true'
    target_app_id = os.environ.get('FEISHU_SINGLE_APP_ID') if single_app_mode else None
    
    if single_app_mode and target_app_id and scheduler.target_app:
        # 单应用模式
        dataset_sync_enabled = scheduler.target_app.dataset_sync
        app_name = scheduler.target_app.app_name
        
        status_msg = f"调度器状态: {'运行中' if status else '已停止'} (应用: {app_name})"
        if status:
            if dataset_sync_enabled:
                status_msg += "，AI知识库同步功能已启用"
            else:
                status_msg += "，AI知识库同步功能已禁用"
    else:
        # 非单应用模式或配置错误
        status_msg = f"调度器状态: {'运行中' if status else '已停止'}"
        if single_app_mode:
            status_msg += f" (配置错误: 未找到应用 {target_app_id})"
        else:
            status_msg += " (非单应用模式)"
    
    return {
        "code": 0,
        "msg": status_msg
    }

@router.post("/start", response_model=SchedulerResponse)
async def start_scheduler():
    """启动调度器"""
    if scheduler._running:
        return {
            "code": 0,
            "msg": "调度器已经在运行中"
        }
    
    scheduler.start()
    return {
        "code": 0,
        "msg": "调度器已启动"
    }

@router.post("/stop", response_model=SchedulerResponse)
async def stop_scheduler():
    """停止调度器"""
    if not scheduler._running:
        return {
            "code": 0,
            "msg": "调度器已经停止"
        }
    
    scheduler.shutdown()
    return {
        "code": 0,
        "msg": "调度器已停止"
    }

@router.post("/manual-run", response_model=SchedulerResponse)
async def manual_run_scan():
    """手动触发一次订阅扫描任务"""
    try:
        # 检查当前应用是否启用dataset_sync
        if not scheduler.target_app:
            return {
                "code": 0,
                "msg": "当前进程无应用配置，无法执行订阅扫描任务"
            }
        
        if not scheduler.target_app.dataset_sync:
            return {
                "code": 0,
                "msg": f"应用 {scheduler.target_app.app_name} 的dataset_sync已禁用，无需执行订阅扫描任务"
            }
        
        # 直接执行扫描任务，不等待结果
        task = scheduler._scan_subscriptions()
        # 使用asyncio创建任务
        import asyncio
        asyncio.create_task(task)
        
        return {
            "code": 0,
            "msg": f"已触发应用 {scheduler.target_app.app_name} 的订阅扫描任务，请查看日志了解执行情况"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"触发订阅扫描任务失败: {str(e)}")

@router.post("/manual-run-aichat-update", response_model=SchedulerResponse)
async def manual_run_aichat_update():
    """手动触发一次AI知识库更新任务"""
    try:
        # 检查当前应用是否启用dataset_sync
        if not scheduler.target_app:
            return {
                "code": 0,
                "msg": "当前进程无应用配置，无法执行AI知识库更新任务"
            }
        
        if not scheduler.target_app.dataset_sync:
            return {
                "code": 0,
                "msg": f"应用 {scheduler.target_app.app_name} 的dataset_sync已禁用，无需执行AI知识库更新任务"
            }
        
        # 直接执行AI知识库更新任务，不等待结果
        task = scheduler._update_aichat_knowledge_base()
        # 使用asyncio创建任务
        import asyncio
        asyncio.create_task(task)
        
        return {
            "code": 0,
            "msg": f"已触发应用 {scheduler.target_app.app_name} 的AI知识库更新任务，请查看日志了解执行情况"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"触发AI知识库更新任务失败: {str(e)}")

@router.post("/manual-run-fastgpt-check", response_model=SchedulerResponse)
async def manual_run_fastgpt_check():
    """手动触发一次FastGPT文件状态检查任务"""
    try:
        # 检查当前应用是否启用dataset_sync
        if not scheduler.target_app:
            return {
                "code": 0,
                "msg": "当前进程无应用配置，无法执行FastGPT文件状态检查任务"
            }
        
        if not scheduler.target_app.dataset_sync:
            return {
                "code": 0,
                "msg": f"应用 {scheduler.target_app.app_name} 的dataset_sync已禁用，无需执行FastGPT文件状态检查任务"
            }
        
        # 直接执行FastGPT文件状态检查任务，不等待结果
        task = scheduler._check_fastgpt_file_status()
        # 使用asyncio创建任务
        import asyncio
        asyncio.create_task(task)
        
        return {
            "code": 0,
            "msg": f"已触发应用 {scheduler.target_app.app_name} 的FastGPT文件状态检查任务，请查看日志了解执行情况"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"触发FastGPT文件状态检查任务失败: {str(e)}") 