from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import os
from app.core.logger import setup_logger

logger = setup_logger("static_api")

router = APIRouter()

# 静态文件基础目录
STATIC_BASE_DIR = Path("static")

@router.get("/images/{filename}")
async def get_image(filename: str):
    """获取图片文件
    
    Args:
        filename: 图片文件名（包含扩展名）
        
    Returns:
        FileResponse: 图片文件响应
    """
    try:
        # 构建文件路径
        file_path = STATIC_BASE_DIR / "images" / filename
        
        # 检查文件是否存在
        if not file_path.exists():
            logger.warning(f"图片文件不存在: {file_path}")
            raise HTTPException(status_code=404, detail="图片文件不存在")
        
        # 检查文件是否在允许的目录内（安全检查）
        try:
            file_path.resolve().relative_to(STATIC_BASE_DIR.resolve())
        except ValueError:
            logger.error(f"非法的文件路径访问: {file_path}")
            raise HTTPException(status_code=403, detail="非法的文件路径")
        
        # 获取文件大小
        file_size = file_path.stat().st_size
        
        # 根据文件扩展名设置媒体类型
        extension = file_path.suffix.lower()
        media_type_map = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.svg': 'image/svg+xml'
        }
        media_type = media_type_map.get(extension, 'application/octet-stream')
        
        logger.info(f"提供图片文件: {filename}, 大小: {file_size}字节, 类型: {media_type}")
        
        return FileResponse(
            path=str(file_path),
            media_type=media_type,
            filename=filename
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取图片文件异常: filename={filename}, error={str(e)}")
        raise HTTPException(status_code=500, detail="服务器内部错误")

@router.get("/images/{filename}/info")
async def get_image_info(filename: str):
    """获取图片文件信息
    
    Args:
        filename: 图片文件名（包含扩展名）
        
    Returns:
        dict: 图片文件信息
    """
    try:
        # 构建文件路径
        file_path = STATIC_BASE_DIR / "images" / filename
        
        # 检查文件是否存在
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="图片文件不存在")
        
        # 检查文件是否在允许的目录内（安全检查）
        try:
            file_path.resolve().relative_to(STATIC_BASE_DIR.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="非法的文件路径")
        
        # 获取文件信息
        stat = file_path.stat()
        
        return {
            "filename": filename,
            "size": stat.st_size,
            "created_time": stat.st_ctime,
            "modified_time": stat.st_mtime,
            "url": f"/static/images/{filename}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取图片文件信息异常: filename={filename}, error={str(e)}")
        raise HTTPException(status_code=500, detail="服务器内部错误") 