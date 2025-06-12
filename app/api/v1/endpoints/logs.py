from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import List, Dict, Any
from pathlib import Path
import os
import io
import re
from pydantic import BaseModel
from app.core.logger import get_app_log_files

router = APIRouter()

# 日志目录
LOG_DIR = Path("logs")

# 主应用日志文件
MAIN_LOG_FILE = "feishu-plus.log"

class LogsResponse(BaseModel):
    logs: List[str]
    total: int

class LogTypesResponse(BaseModel):
    """日志类型响应"""
    types: List[Dict[str, str]]

@router.get("/types", response_model=LogTypesResponse)
async def get_log_types():
    """获取可用的日志类型"""
    log_types = [
        {"type": "all", "name": "全部日志"},
        {"type": "error", "name": "错误日志"}
    ]
    
    # 添加应用专用日志
    app_logs = get_app_log_files()
    for app_log in app_logs:
        log_types.append({
            "type": f"app_{app_log['app_id']}",
            "name": app_log['display_name']
        })
    
    return {"types": log_types}

@router.get("/", response_model=LogsResponse)
async def get_logs(
    type: str = Query("all", description="日志类型：all(全部), error(错误), app_{app_id}(应用专用)"),
    lines: int = Query(1000, description="返回行数，默认1000行"),
    search: str = Query(None, description="搜索关键词")
):
    """获取日志内容"""
    
    # 确定要读取的日志文件
    log_file_path = None
    
    if type == "all":
        log_file_path = LOG_DIR / MAIN_LOG_FILE
    elif type == "error":
        log_file_path = LOG_DIR / MAIN_LOG_FILE
    elif type.startswith("app_"):
        # 应用专用日志
        app_id = type[4:]  # 去掉 "app_" 前缀
        app_logs = get_app_log_files()
        
        target_app_log = None
        for app_log in app_logs:
            if app_log['app_id'] == app_id:
                target_app_log = app_log
                break
        
        if target_app_log:
            log_file_path = Path(target_app_log['file_path'])
        else:
            raise HTTPException(status_code=404, detail=f"未找到应用日志: {app_id}")
    else:
        raise HTTPException(status_code=400, detail=f"不支持的日志类型: {type}")
    
    if not log_file_path.exists():
        return LogsResponse(logs=[], total=0)
    
    try:
        with open(log_file_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        
        # 过滤日志
        if type == "error":
            # 只显示错误日志
            filtered_lines = [line for line in all_lines if "[ERROR]" in line or "[CRITICAL]" in line]
        else:
            filtered_lines = all_lines
        
        # 搜索过滤
        if search:
            filtered_lines = [line for line in filtered_lines if search.lower() in line.lower()]
        
        # 取最后N行
        result_lines = filtered_lines[-lines:] if len(filtered_lines) > lines else filtered_lines
        
        # 清理换行符
        result_lines = [line.rstrip('\n\r') for line in result_lines]
        
        return LogsResponse(logs=result_lines, total=len(result_lines))
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取日志文件失败: {str(e)}")

@router.get("/download")
async def download_logs(type: str = Query("all", description="日志类型")):
    """下载日志文件"""
    
    # 确定要下载的日志文件
    log_file_path = None
    filename = None
    
    if type == "all":
        log_file_path = LOG_DIR / MAIN_LOG_FILE
        filename = "feishu-plus-all.log"
    elif type == "error":
        log_file_path = LOG_DIR / MAIN_LOG_FILE
        filename = "feishu-plus-error.log"
    elif type.startswith("app_"):
        # 应用专用日志
        app_id = type[4:]  # 去掉 "app_" 前缀
        app_logs = get_app_log_files()
        
        target_app_log = None
        for app_log in app_logs:
            if app_log['app_id'] == app_id:
                target_app_log = app_log
                break
        
        if target_app_log:
            log_file_path = Path(target_app_log['file_path'])
            filename = f"{target_app_log['app_name']}-{app_id}.log"
        else:
            raise HTTPException(status_code=404, detail=f"未找到应用日志: {app_id}")
    else:
        raise HTTPException(status_code=400, detail=f"不支持的日志类型: {type}")
    
    if not log_file_path.exists():
        raise HTTPException(status_code=404, detail="日志文件不存在")
    
    try:
        def generate_log_content():
            with open(log_file_path, "r", encoding="utf-8") as f:
                if type == "error":
                    # 只输出错误日志
                    for line in f:
                        if "[ERROR]" in line or "[CRITICAL]" in line:
                            yield line
                else:
                    # 输出全部日志
                    for line in f:
                        yield line
        
        return StreamingResponse(
            generate_log_content(),
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载日志文件失败: {str(e)}")

@router.post("/clear")
async def clear_logs(type: str = Query("all", description="日志类型")):
    """清空日志文件"""
    
    # 确定要清空的日志文件
    log_file_path = None
    
    if type == "all":
        log_file_path = LOG_DIR / MAIN_LOG_FILE
    elif type == "error":
        raise HTTPException(status_code=400, detail="错误日志无法单独清空，请清空对应的完整日志")
    elif type.startswith("app_"):
        # 应用专用日志
        app_id = type[4:]  # 去掉 "app_" 前缀
        app_logs = get_app_log_files()
        
        target_app_log = None
        for app_log in app_logs:
            if app_log['app_id'] == app_id:
                target_app_log = app_log
                break
        
        if target_app_log:
            log_file_path = Path(target_app_log['file_path'])
        else:
            raise HTTPException(status_code=404, detail=f"未找到应用日志: {app_id}")
    else:
        raise HTTPException(status_code=400, detail=f"不支持的日志类型: {type}")
    
    if not log_file_path.exists():
        return {"message": "日志文件不存在"}
    
    try:
        # 清空文件内容
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write("")
        
        if type == "all":
            return {"message": "已清空全部日志"}
        elif type.startswith("app_"):
            app_id = type[4:]
            app_logs = get_app_log_files()
            app_name = "应用"
            for app_log in app_logs:
                if app_log['app_id'] == app_id:
                    app_name = app_log['app_name']
                    break
            return {"message": f"已清空{app_name}日志"}
        else:
            return {"message": f"已清空{type}日志"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清空日志文件失败: {str(e)}") 