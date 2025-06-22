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

@router.get("/files/{filename}")
async def get_file(filename: str):
    """获取文件
    
    Args:
        filename: 文件名（包含扩展名）
        
    Returns:
        FileResponse: 文件响应（下载模式）
    """
    try:
        # 构建文件路径
        file_path = STATIC_BASE_DIR / "files" / filename
        
        # 检查文件是否存在
        if not file_path.exists():
            logger.warning(f"文件不存在: {file_path}")
            raise HTTPException(status_code=404, detail="文件不存在")
        
        # 检查文件是否在允许的目录内（安全检查）
        try:
            file_path.resolve().relative_to(STATIC_BASE_DIR.resolve())
        except ValueError:
            logger.error(f"非法的文件路径访问: {file_path}")
            raise HTTPException(status_code=403, detail="非法的文件路径")
        
        # 获取文件大小
        file_size = file_path.stat().st_size
        
        # 尝试读取原始文件名映射
        original_filename = filename  # 默认使用安全文件名
        mapping_file = STATIC_BASE_DIR / "files" / f"{filename}.meta"
        if mapping_file.exists():
            try:
                import json
                with open(mapping_file, 'r', encoding='utf-8') as f:
                    mapping_data = json.load(f)
                    original_filename = mapping_data.get("original_name", filename)
                    logger.info(f"读取到原始文件名映射: {filename} -> {original_filename}")
            except Exception as e:
                logger.warning(f"读取文件名映射失败: {e}")
        
        # 根据文件扩展名设置媒体类型
        extension = file_path.suffix.lower()
        media_type_map = {
            # 文档类型
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            # 文本类型
            '.txt': 'text/plain',
            '.json': 'application/json',
            '.xml': 'application/xml',
            '.csv': 'text/csv',
            # 压缩类型
            '.zip': 'application/zip',
            '.rar': 'application/x-rar-compressed',
            '.7z': 'application/x-7z-compressed',
            # 图片类型
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.svg': 'image/svg+xml'
        }
        media_type = media_type_map.get(extension, 'application/octet-stream')
        
        # 对中文文件名进行URL编码
        import urllib.parse
        encoded_filename = urllib.parse.quote(original_filename.encode('utf-8'))
        
        logger.info(f"提供文件下载: {original_filename}, 大小: {file_size}字节, 类型: {media_type}")
        
        return FileResponse(
            path=str(file_path),
            media_type=media_type,
            filename=original_filename,
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文件异常: filename={filename}, error={str(e)}")
        raise HTTPException(status_code=500, detail="服务器内部错误")

@router.get("/files/{filename}/info")
async def get_file_info(filename: str):
    """获取文件信息
    
    Args:
        filename: 文件名（包含扩展名）
        
    Returns:
        dict: 文件信息
    """
    try:
        # 构建文件路径
        file_path = STATIC_BASE_DIR / "files" / filename
        
        # 检查文件是否存在
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")
        
        # 检查文件是否在允许的目录内（安全检查）
        try:
            file_path.resolve().relative_to(STATIC_BASE_DIR.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="非法的文件路径")
        
        # 获取文件信息
        stat = file_path.stat()
        
        # 尝试读取原始文件名映射
        original_filename = filename  # 默认使用安全文件名
        mapping_file = STATIC_BASE_DIR / "files" / f"{filename}.meta"
        if mapping_file.exists():
            try:
                import json
                with open(mapping_file, 'r', encoding='utf-8') as f:
                    mapping_data = json.load(f)
                    original_filename = mapping_data.get("original_name", filename)
            except Exception as e:
                logger.warning(f"读取文件名映射失败: {e}")
        
        return {
            "filename": filename,
            "original_filename": original_filename,
            "size": stat.st_size,
            "created_time": stat.st_ctime,
            "modified_time": stat.st_mtime,
            "url": f"/api/v1/static/files/{filename}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文件信息异常: filename={filename}, error={str(e)}")
        raise HTTPException(status_code=500, detail="服务器内部错误")





 