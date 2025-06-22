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
    page: int
    page_size: int
    total_pages: int

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
    page: int = Query(1, description="页码，从1开始"),
    page_size: int = Query(1000, description="每页行数，默认1000行"),
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
        return LogsResponse(logs=[], total=0, page=page, page_size=page_size, total_pages=0)
    
    try:
        # 尝试多种编码方式读取文件
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin1']
        all_lines = None
        
        for encoding in encodings:
            try:
                with open(log_file_path, "r", encoding=encoding, errors='ignore') as f:
                    all_lines = f.readlines()
                break
            except UnicodeDecodeError:
                continue
        
        if all_lines is None:
            # 如果所有编码都失败，使用二进制模式读取并忽略错误
            with open(log_file_path, "rb") as f:
                content = f.read()
                # 尝试解码，忽略无法解码的字符
                try:
                    text_content = content.decode('utf-8', errors='ignore')
                except:
                    text_content = content.decode('latin1', errors='ignore')
                all_lines = text_content.splitlines(keepends=True)
        
        # 过滤日志
        if type == "error":
            # 只显示错误日志
            filtered_lines = [line for line in all_lines if "[ERROR]" in line or "[CRITICAL]" in line]
        else:
            filtered_lines = all_lines
        
        # 搜索过滤
        if search:
            filtered_lines = [line for line in filtered_lines if search.lower() in line.lower()]
        
        # 计算总数和分页
        total_lines = len(filtered_lines)
        total_pages = (total_lines + page_size - 1) // page_size if total_lines > 0 else 0
        
        # 确保页码有效
        if page < 1:
            page = 1
        elif page > total_pages and total_pages > 0:
            page = total_pages
        
        # 计算分页范围（从最新的日志开始，即文件末尾）
        start_index = max(0, total_lines - page * page_size)
        end_index = max(0, total_lines - (page - 1) * page_size)
        
        # 获取当前页的日志（倒序，最新的在前）
        page_lines = filtered_lines[start_index:end_index]
        page_lines.reverse()  # 反转，让最新的日志在前面
        
        # 清理换行符并确保所有行都是有效的字符串
        result_lines = []
        for line in page_lines:
            try:
                # 清理换行符
                clean_line = line.rstrip('\n\r')
                # 确保是有效的UTF-8字符串
                clean_line.encode('utf-8')
                result_lines.append(clean_line)
            except UnicodeEncodeError:
                # 如果仍然有编码问题，替换问题字符
                clean_line = line.rstrip('\n\r').encode('utf-8', errors='replace').decode('utf-8')
                result_lines.append(clean_line)
        
        return LogsResponse(
            logs=result_lines, 
            total=total_lines, 
            page=page, 
            page_size=page_size, 
            total_pages=total_pages
        )
        
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
            # 尝试多种编码方式读取文件
            encodings = ['utf-8', 'gbk', 'gb2312', 'latin1']
            
            for encoding in encodings:
                try:
                    with open(log_file_path, "r", encoding=encoding, errors='ignore') as f:
                        if type == "error":
                            # 只输出错误日志
                            for line in f:
                                if "[ERROR]" in line or "[CRITICAL]" in line:
                                    yield line
                        else:
                            # 输出全部日志
                            for line in f:
                                yield line
                    return
                except UnicodeDecodeError:
                    continue
            
            # 如果所有编码都失败，使用二进制模式
            with open(log_file_path, "rb") as f:
                content = f.read()
                try:
                    text_content = content.decode('utf-8', errors='ignore')
                except:
                    text_content = content.decode('latin1', errors='ignore')
                
                lines = text_content.splitlines(keepends=True)
                if type == "error":
                    for line in lines:
                        if "[ERROR]" in line or "[CRITICAL]" in line:
                            yield line
                else:
                    for line in lines:
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
        with open(log_file_path, "w", encoding="utf-8", errors='ignore') as f:
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