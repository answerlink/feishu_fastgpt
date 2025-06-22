from fastapi import APIRouter, HTTPException
from typing import Dict, List
from pydantic import BaseModel
from app.core.multi_app_manager import multi_app_manager

router = APIRouter()

class AppStatusResponse(BaseModel):
    app_id: str
    app_name: str
    status: str
    pid: int = None
    port: int = None
    exit_code: int = None

class MultiAppStatusResponse(BaseModel):
    code: int
    msg: str
    data: Dict

@router.get("/status", response_model=MultiAppStatusResponse)
async def get_multi_app_status():
    """获取多应用状态"""
    status = multi_app_manager.get_status()
    
    return {
        "code": 0,
        "msg": "获取状态成功",
        "data": status
    }

@router.post("/check-processes", response_model=MultiAppStatusResponse)
async def check_processes():
    """检查并重启失败的进程"""
    try:
        multi_app_manager.check_processes()
        
        status = multi_app_manager.get_status()
        
        return {
            "code": 0,
            "msg": "进程检查完成",
            "data": status
        }
    except Exception as e:
        return {
            "code": -1,
            "msg": f"进程检查失败: {str(e)}",
            "data": {}
        } 