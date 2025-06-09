from fastapi import APIRouter, Depends, HTTPException
from typing import Dict
from pydantic import BaseModel
from app.core.scheduler import scheduler

router = APIRouter()

class SchedulerResponse(BaseModel):
    code: int
    msg: str

@router.get("/status", response_model=SchedulerResponse)
async def get_scheduler_status():
    """获取调度器运行状态"""
    status = scheduler._running
    return {
        "code": 0,
        "msg": f"调度器状态: {'运行中' if status else '已停止'}"
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
        # 直接执行扫描任务，不等待结果
        task = scheduler._scan_subscriptions()
        # 使用asyncio创建任务
        import asyncio
        asyncio.create_task(task)
        
        return {
            "code": 0,
            "msg": "已触发订阅扫描任务，请查看日志了解执行情况"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"触发订阅扫描任务失败: {str(e)}")

@router.post("/manual-run-aichat-update", response_model=SchedulerResponse)
async def manual_run_aichat_update():
    """手动触发一次AI知识库更新任务"""
    try:
        # 直接执行AI知识库更新任务，不等待结果
        task = scheduler._update_aichat_knowledge_base()
        # 使用asyncio创建任务
        import asyncio
        asyncio.create_task(task)
        
        return {
            "code": 0,
            "msg": "已触发AI知识库更新任务，请查看日志了解执行情况"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"触发AI知识库更新任务失败: {str(e)}") 