from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import List, Dict, Any
from pathlib import Path
import os
import io
from pydantic import BaseModel

router = APIRouter()

# 日志目录
LOG_DIR = Path("logs")

# 日志类型映射
LOG_FILES = {
    "subscription_scheduler": "subscription_scheduler.log",
    "feishu_service": "feishu_service.log",
    "feishu_callback": "feishu_callback.log",
    "feishu-plus": "feishu-plus.log"
}

class LogsResponse(BaseModel):
    logs: List[str]
    total: int

@router.get("/view", response_model=LogsResponse)
async def view_logs(
    type: str = Query(..., description="日志类型"),
    page: int = Query(1, description="页码"),
    page_size: int = Query(100, description="每页行数")
):
    """查看指定类型的日志"""
    if type not in LOG_FILES:
        raise HTTPException(status_code=400, detail=f"不支持的日志类型: {type}")
    
    log_file = LOG_DIR / LOG_FILES[type]
    
    if not log_file.exists():
        return {"logs": [], "total": 0}
    
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            all_logs = f.readlines()
            
        # 计算总行数和分页
        total_lines = len(all_logs)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        
        # 获取当前页的日志
        page_logs = all_logs[start_idx:end_idx] if start_idx < total_lines else []
        
        return {"logs": page_logs, "total": total_lines}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取日志文件失败: {str(e)}")

@router.get("/download")
async def download_logs(type: str = Query(..., description="日志类型")):
    """下载指定类型的日志文件"""
    if type not in LOG_FILES:
        raise HTTPException(status_code=400, detail=f"不支持的日志类型: {type}")
    
    log_file = LOG_DIR / LOG_FILES[type]
    
    if not log_file.exists():
        raise HTTPException(status_code=404, detail="日志文件不存在")
    
    try:
        with open(log_file, "rb") as f:
            content = f.read()
        
        # 创建内存文件流
        stream = io.BytesIO(content)
        
        # 返回文件流
        return StreamingResponse(
            stream, 
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename={LOG_FILES[type]}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载日志文件失败: {str(e)}")

@router.post("/clear")
async def clear_logs(type: str = Query(..., description="日志类型")):
    """清空指定类型的日志文件"""
    if type not in LOG_FILES:
        raise HTTPException(status_code=400, detail=f"不支持的日志类型: {type}")
    
    log_file = LOG_DIR / LOG_FILES[type]
    
    if not log_file.exists():
        return {"message": "日志文件不存在"}
    
    try:
        # 清空文件内容
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("")
        
        return {"message": f"已清空 {type} 日志"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清空日志文件失败: {str(e)}") 