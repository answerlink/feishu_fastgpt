from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db, get_feishu_service
from app.services.feishu_service import FeishuService
from typing import Dict, List, Optional
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy import select, update, delete, and_, or_
from sqlalchemy import func
from app.models.doc_subscription import DocSubscription
from app.core.config import settings
from app.core.logger import setup_logger
import os
import tempfile
from pathlib import Path
from app.utils.doc_block_filter import DocBlockFilter
from app.utils.block_to_markdown import BlockToMarkdown

logger = setup_logger("document_api")

router = APIRouter()

# 请求模型
class DocSubscribeRequest(BaseModel):
    app_id: str
    file_token: str
    file_type: str
    space_id: Optional[str] = None  # 所属知识空间ID，可选
    title: Optional[str] = None     # 文档标题，可选
    obj_edit_time: Optional[str] = None  # 文档最后编辑时间，可选

class SpaceSubscribeRequest(BaseModel):
    app_id: str
    space_id: str

class UpdateAIChatTimeRequest(BaseModel):
    app_id: str
    file_token: str
    success: bool = True

class SyncDocToAIChatRequest(BaseModel):
    app_id: str
    file_token: str
    file_type: str
    hierarchy_changed: bool = False  # 新增参数，默认为False

class TestImageRequest(BaseModel):
    app_id: str
    doc_token: str

class TestSheetRequest(BaseModel):
    app_id: str
    sheet_token: str

# 响应模型
class SubscribeResponse(BaseModel):
    code: int
    msg: str = ""
    data: Optional[Dict] = None

# 订阅文档事件
@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe_document_events(
    request: DocSubscribeRequest,
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """订阅云文档事件
    
    订阅后，当文档发生编辑、标题更新、权限变更等事件时，
    将通过回调接口推送通知
    """
    result = await feishu_service.subscribe_doc_events(
        request.app_id, 
        request.file_token,
        request.file_type,
        request.title,  # 传递title参数
        request.space_id,  # 传递space_id参数
        request.obj_edit_time  # 传递obj_edit_time参数
    )
    
    return {
        "code": result.get("code", -1),
        "msg": result.get("msg", ""),
        "data": result.get("data")
    }

# 订阅知识空间下所有文档事件
@router.post("/subscribe-space", response_model=SubscribeResponse)
async def subscribe_space_documents(
    request: SpaceSubscribeRequest,
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """订阅知识空间下所有文档事件
    
    遍历指定知识空间下的所有文档并订阅事件，
    仅订阅docx类型的文档
    """
    result = await feishu_service.subscribe_space_documents(
        request.app_id,
        request.space_id
    )
    
    return {
        "code": result.get("code", 0),
        "msg": result.get("msg", ""),
        "data": result.get("data")
    }

# 取消订阅文档事件
@router.post("/unsubscribe", response_model=SubscribeResponse)
async def unsubscribe_document_events(
    request: DocSubscribeRequest,
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """取消订阅云文档事件"""
    result = await feishu_service.unsubscribe_doc_events(
        request.app_id, 
        request.file_token,
        request.file_type
    )
    
    return {
        "code": result.get("code", -1),
        "msg": result.get("msg", ""),
        "data": result.get("data")
    }

# 获取文档内容
@router.get("/{app_id}/{doc_token}", response_model=SubscribeResponse)
async def get_document_content(
    app_id: str,
    doc_token: str,
    doc_type: str = "docx",
    content_type: str = "markdown",
    use_filtered_blocks: bool = Query(True, description="是否使用我们自己实现的filtered-blocks处理逻辑"),
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """获取文档内容"""
    result = await feishu_service.get_doc_content(
        app_id,
        doc_token,
        doc_type,
        content_type,
        use_filtered_blocks=use_filtered_blocks
    )
    
    return {
        "code": result.get("code", -1),
        "msg": result.get("msg", ""),
        "data": result.get("data")
    }

# 获取已订阅文档列表
@router.get("/subscribed", response_model=SubscribeResponse)
async def get_subscribed_documents(
    app_id: str,
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """获取已订阅的文档列表
    
    从数据库中查询已订阅的文档列表，无需调用飞书API
    """
    result = await feishu_service.get_subscribed_documents(app_id)
    
    return {
        "code": result.get("code", -1),
        "msg": result.get("msg", ""),
        "data": result.get("data")
    }

# 更新文档AI知识库时间
@router.post("/update-aichat-time", response_model=SubscribeResponse)
async def update_document_aichat_time(
    request: UpdateAIChatTimeRequest,
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """更新文档AI知识库同步时间
    
    在文档内容成功同步到AI知识库后调用此接口，记录同步时间
    """
    success = await feishu_service.update_doc_aichat_time(
        request.app_id,
        request.file_token,
        request.success
    )
    
    if success:
        return {
            "code": 0,
            "msg": "更新AI知识库同步时间成功"
        }
    else:
        return {
            "code": -1,
            "msg": "更新AI知识库同步时间失败"
        }

# 获取需要同步到AI知识库的文档列表
@router.get("/aichat-sync", response_model=SubscribeResponse)
async def get_documents_for_aichat_sync(
    app_id: str,
    limit: int = Query(100, description="返回的最大文档数量"),
    file_token: str = Query(None, description="指定文档Token，可选"),
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """获取需要同步到AI知识库的文档列表
    
    获取满足以下条件的文档:
    1. 已订阅
    2. obj_edit_time > aichat_update_time 或 aichat_update_time为空
    
    如果指定file_token，则只返回该文档的信息，不考虑上述条件
    """
    # 检查指定应用是否启用了dataset_sync
    app_config = next((app for app in settings.FEISHU_APPS if app.app_id == app_id), None)
    
    if not app_config:
        return {
            "code": -1,
            "msg": f"找不到应用配置: {app_id}",
            "data": None
        }
    
    if not app_config.dataset_sync:
        return {
            "code": 0,
            "msg": f"应用 {app_id} 的dataset_sync功能已禁用",
            "data": {
                "total": 0,
                "items": [],
                "dataset_sync_disabled": True
            }
        }
    
    result = await feishu_service.get_docs_for_aichat_sync(app_id, limit, file_token)
    
    return {
        "code": result.get("code", -1),
        "msg": result.get("msg", ""),
        "data": result.get("data")
    }

# 手动和自动同步文档到AI知识库
@router.post("/sync-to-aichat", response_model=SubscribeResponse)
async def manual_sync_to_aichat(
    request: SyncDocToAIChatRequest,
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """手动同步文档到AI知识库
    
    支持两种类型的文件：
    1. 云文档类型(docx)：读取文档内容，转为markdown上传
    2. PDF文件：下载文件后直接上传到FastGPT
    
    同步过程包括：
    1. 获取文档内容或下载PDF文件
    2. 查找或创建与app_name同名的文件夹
    3. 根据知识空间名称创建子文件夹
    4. 根据配置创建产品资料、项目资料等固定文件夹
    5. 同步文档内容到知识库
    6. 更新文档同步时间
    """
    # 检查指定应用是否启用了dataset_sync
    app_config = next((app for app in settings.FEISHU_APPS if app.app_id == request.app_id), None)
    
    if not app_config:
        return {
            "code": -1,
            "msg": f"找不到应用配置: {request.app_id}",
            "data": None
        }
    
    if not app_config.dataset_sync:
        return {
            "code": 0,
            "msg": f"应用 {request.app_id} 的dataset_sync功能已禁用，跳过同步",
            "data": {
                "file_token": request.file_token,
                "dataset_sync_disabled": True
            }
        }
    
    # 直接调用同步函数
    result = await sync_document_to_aichat(request, feishu_service)
    
    return {
        "code": result.get("code", -1),
        "msg": result.get("msg", ""),
        "data": result.get("data")
    }

# 获取文档中的所有图片信息
@router.get("/{app_id}/{doc_token}/images", response_model=SubscribeResponse)
async def get_document_images(
    app_id: str,
    doc_token: str,
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """获取文档中的所有图片信息
    
    获取云文档中的所有图片块，返回包含block_id、image_token等信息的列表
    """
    result = await feishu_service.get_document_images(app_id, doc_token)
    
    return {
        "code": result.get("code", -1),
        "msg": result.get("msg", ""),
        "data": result.get("data")
    }

# 下载文档中的图片
@router.get("/{app_id}/image/{image_token}/download", response_model=SubscribeResponse)
async def download_image(
    app_id: str,
    image_token: str,
    filename: str = Query(None, description="图片保存的文件名，不提供则使用image_token作为文件名"),
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """下载文档中的图片
    
    基于image_token下载图片，保存到临时目录并返回文件路径
    """
    # 如果未提供文件名，使用image_token
    if not filename:
        filename = f"{image_token}.png"  # 默认使用png扩展名
    
    # 创建temp/images目录用于保存图片
    import os
    from pathlib import Path
    temp_dir = Path("temp/images")
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # 构建输出路径
    output_path = str(temp_dir / filename)
    
    # 下载图片
    result = await feishu_service.download_image(app_id, image_token, output_path)
    
    if result.get("code") == 0:
        # 添加文件URL信息
        file_path = result.get("data", {}).get("file_path")
        if file_path:
            # 构建相对URL路径，不暴露服务器绝对路径
            relative_path = os.path.relpath(file_path).replace("\\", "/")
            result["data"]["url"] = f"/static/{relative_path}"
    
    return {
        "code": result.get("code", -1),
        "msg": result.get("msg", ""),
        "data": result.get("data")
    }

# 获取文档所有块（原始数据）
@router.get("/{app_id}/{doc_token}/blocks", response_model=SubscribeResponse)
async def get_document_blocks(
    app_id: str,
    doc_token: str,
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """获取文档所有块
    
    获取文档所有块的原始数据，包括文本块、图片块等
    """
    result = await feishu_service.get_all_document_blocks(app_id, doc_token)
    
    return {
        "code": result.get("code", -1),
        "msg": result.get("msg", ""),
        "data": result.get("data")
    }

# 测试文档图片功能
@router.post("/test-image", response_model=SubscribeResponse)
async def test_document_image(
    request: TestImageRequest,
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """测试获取文档图片功能
    
    1. 获取文档中所有图片信息
    2. 下载第一张图片
    3. 返回处理结果
    """
    app_id = request.app_id
    doc_token = request.doc_token
    
    logger.info(f"开始测试文档图片功能: app_id={app_id}, doc_token={doc_token}")
    
    # 步骤1: 获取文档所有图片
    images_result = await feishu_service.get_document_images(app_id, doc_token)
    
    if images_result.get("code") != 0:
        logger.error(f"获取文档图片失败: {images_result.get('msg')}")
        return {
            "code": -1,
            "msg": f"获取文档图片失败: {images_result.get('msg')}",
            "data": None
        }
    
    # 获取图片列表
    images = images_result.get("data", {}).get("items", [])
    total_images = len(images)
    
    logger.info(f"文档共有{total_images}张图片")
    
    if total_images == 0:
        return {
            "code": 0,
            "msg": "文档中没有图片",
            "data": {
                "total_images": 0,
                "images": []
            }
        }
    
    # 步骤2: 下载第一张图片
    first_image = images[0]
    image_token = first_image.get("image_token")
    
    if not image_token:
        logger.error("图片token为空")
        return {
            "code": -1,
            "msg": "图片token为空",
            "data": {
                "total_images": total_images,
                "images": images
            }
        }
    
    # 创建临时目录用于保存图片
    import os
    from pathlib import Path
    temp_dir = Path("temp/images")
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # 构建输出路径
    filename = f"test_{image_token[:8]}.png"
    output_path = str(temp_dir / filename)
    
    # 下载图片
    download_result = await feishu_service.download_image(app_id, image_token, output_path)
    
    if download_result.get("code") != 0:
        logger.error(f"[文件处理] 下载文件失败: file_token={request.file_token}, 错误={download_result.get('msg')}")
        await fastgpt_service.close()
        
        # 根据错误类型返回不同的信息
        error_msg = download_result.get('msg', '下载失败')
        status_code = download_result.get('status_code')
        
        if status_code == 404 or "文件不存在或已被删除" in error_msg:
            return {
                "code": -1,
                "msg": f"文件不存在或已被删除，可能是文件token已过期: {error_msg}",
                "data": {
                    "file_token": request.file_token,
                    "error_type": "file_not_found",
                    "recoverable": False
                }
            }
        elif status_code == 403 or "无权限访问" in error_msg:
            return {
                "code": -1,
                "msg": f"无权限访问文件: {error_msg}",
                "data": {
                    "file_token": request.file_token,
                    "error_type": "permission_denied",
                    "recoverable": True
                }
            }
        else:
            return {
                "code": -1,
                "msg": f"下载文件失败: {error_msg}",
                "data": {
                    "file_token": request.file_token,
                    "error_type": "download_failed",
                    "recoverable": True
                }
            }

    # 构建图片URL
    file_path = download_result.get("data", {}).get("file_path")
    relative_path = os.path.relpath(file_path).replace("\\", "/")
    image_url = f"/static/{relative_path}"
    
    # 返回结果
    return {
        "code": 0,
        "msg": "成功获取文档图片",
        "data": {
            "total_images": total_images,
            "images": images,
            "first_image": {
                "image_token": image_token,
                "file_path": file_path,
                "file_size": download_result.get("data", {}).get("file_size"),
                "image_url": image_url
            }
        }
    }

# 获取过滤后的文档块
@router.post("/filtered-blocks", response_model=SubscribeResponse)
async def get_filtered_blocks(
    request: TestImageRequest,
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """获取过滤后的文档块
    
    1. 获取文档所有块
    2. 使用DocBlockFilter过滤只保留可转为Markdown的通用块
    3. 返回过滤后的块和树状结构
    """
    app_id = request.app_id
    doc_token = request.doc_token
    
    logger.info(f"开始获取并过滤文档块: app_id={app_id}, doc_token={doc_token}")
    
    # 获取所有块
    blocks_result = await feishu_service.get_all_document_blocks(app_id, doc_token)
    
    if blocks_result.get("code") != 0:
        logger.error(f"获取文档块失败: {blocks_result.get('msg')}")
        return {
            "code": -1,
            "msg": f"获取文档块失败: {blocks_result.get('msg')}",
            "data": None
        }
    
    # 获取文档块列表
    blocks = blocks_result.get("data", {}).get("items", [])
    total_blocks = len(blocks)
    
    logger.info(f"成功获取文档块: doc_token={doc_token}, 总块数={total_blocks}")
    
    if total_blocks == 0:
        return {
            "code": 0,
            "msg": "文档中没有块",
            "data": {
                "total_blocks": 0,
                "blocks": []
            }
        }
    
    # 使用DocBlockFilter组织块
    organized_result = DocBlockFilter.organize_blocks(blocks)
    filtered_blocks = organized_result["blocks"]
    block_tree = organized_result["tree"]
    
    # 使用BlockToMarkdown将块转换为Markdown
    markdown_content = await BlockToMarkdown.convert(filtered_blocks, app_id=app_id)
    
    # 返回结果
    return {
        "code": 0,
        "msg": "成功获取并过滤文档块",
        "data": {
            "total_blocks": total_blocks,
            "filtered_blocks_count": len(filtered_blocks),
            "filtered_blocks": filtered_blocks,
            "block_tree": block_tree,
            "md": markdown_content
        }
    }

# 测试FastGPT知识库功能
@router.post("/test-fastgpt", response_model=SubscribeResponse)
async def test_fastgpt_integration(
    request: DocSubscribeRequest,
    db: AsyncSession = Depends(get_db)
):
    """测试FastGPT知识库集成功能
    
    获取文档内容并尝试同步到FastGPT知识库
    """
    try:
        # 创建飞书服务实例
        feishu_service = FeishuService(db)
        
        # 直接调用更新AI知识库方法
        success = await feishu_service.update_doc_aichat_time(
            request.app_id,
            request.file_token,
            True
        )
        
        # 关闭服务实例
        await feishu_service.close()
        
        if success:
            return {
                "code": 0,
                "msg": "成功测试FastGPT知识库集成，请查看日志了解详情",
                "data": {
                    "file_token": request.file_token,
                    "success": True
                }
            }
        else:
            return {
                "code": -1,
                "msg": "FastGPT知识库集成测试失败，请查看日志了解详情",
                "data": {
                    "file_token": request.file_token,
                    "success": False
                }
            }
            
    except Exception as e:
        return {
            "code": -1,
            "msg": f"测试FastGPT知识库集成时发生错误: {str(e)}",
            "data": None
        } 

# 同步文档到AI知识库的核心函数
async def sync_document_to_aichat(request: SyncDocToAIChatRequest, feishu_service: FeishuService) -> dict:
    """同步文档到AI知识库
    
    1. 获取文档内容
    2. 查找或创建与app_name同名的文件夹
    3. 根据知识空间名称创建子文件夹
    4. 根据配置创建产品资料、项目资料等固定文件夹
    5. 同步文档内容到知识库
    6. 更新文档同步时间
    Args:
        request: 同步请求
        feishu_service: 飞书服务实例
        
    Returns:
        dict: 同步结果
    """
    try:
        # 获取应用配置，以便获取app_name
        app_config = next((app for app in settings.FEISHU_APPS if app.app_id == request.app_id), None)
        
        if not app_config:
            return {
                "code": -1,
                "msg": f"找不到应用配置: {request.app_id}",
                "data": None
            }
        
        # 检查是否启用了dataset_sync
        if not app_config.dataset_sync:
            return {
                "code": 0,
                "msg": f"应用 {request.app_id} 的dataset_sync功能已禁用，跳过同步",
                "data": {
                    "file_token": request.file_token,
                    "dataset_sync_disabled": True
                }
            }
        
        # 初始化FastGPT服务
        from app.services.fastgpt_service import FastGPTService
        fastgpt_service = FastGPTService(request.app_id)
        
        try:
            # 获取文档信息
            query = await feishu_service.db.execute(
                select(DocSubscription).where(
                    DocSubscription.app_id == request.app_id,
                    DocSubscription.file_token == request.file_token
                )
            )
            doc = query.scalar_one_or_none()
            
            if not doc:
                await fastgpt_service.close()
                return {
                    "code": -1,
                    "msg": f"找不到文档记录: {request.file_token}",
                    "data": None
                }
            
            # 更新文件类型判断变量
            is_direct_file_upload = (request.file_type.lower() == "file" and doc.title and (
                doc.title.lower().endswith('.pdf') or 
                doc.title.lower().endswith('.docx') or 
                doc.title.lower().endswith('.xlsx') or
                doc.title.lower().endswith('.pptx')
            )) or request.file_type.lower() == "pdf"
            is_markdown_doc = request.file_type in ["docx", "sheet"]      # 云文档和电子表格，转换为markdown后上传
            
            # 对于file类型但不是支持的文件格式，优雅地跳过处理
            if request.file_type.lower() == "file" and not is_direct_file_upload:
                logger.info(f"文档类型不支持，跳过处理: {request.file_type}, 标题: {doc.title}")
                await fastgpt_service.close()
                return {
                    "code": 0,
                    "msg": f"文档类型不支持，已跳过处理: {doc.title}",
                    "data": {
                        "file_token": request.file_token,
                        "skipped": True,
                        "reason": "不支持的文件类型"
                    }
                }
            
            # 如果既不是直接文件上传也不是markdown文档，跳过处理
            if not is_direct_file_upload and not is_markdown_doc:
                logger.info(f"文档类型不支持，跳过处理: {request.file_type}")
                await fastgpt_service.close()
                return {
                    "code": 0,
                    "msg": f"文档类型不支持，已跳过处理: {request.file_type}",
                    "data": {
                        "file_token": request.file_token,
                        "skipped": True,
                        "reason": "不支持的文件类型"
                    }
                }
            
            # 如果目录发生变化，先删除旧的知识文件记录
            if doc.collection_id:
                try:
                    delete_result = await fastgpt_service.delete_collection(doc.collection_id)
                    if delete_result.get("code") == 200:  # 修改判断条件
                        logger.info(f"成功删除旧的知识库记录: collection_id={doc.collection_id}")
                    else:
                        logger.error(f"删除旧的知识库记录失败: {delete_result.get('msg')}")
                except Exception as e:
                    logger.error(f"删除旧的知识库记录异常: {str(e)}")
            
            document_content = ""
            temp_file_path = None
            
            # 获取文档内容或下载文件
            try:
                # 根据文件类型选择不同的处理方式
                if is_direct_file_upload:
                    # 文件需要下载后处理
                    temp_dir = Path("temp")
                    temp_dir.mkdir(exist_ok=True)
                    
                    # 使用文档标题创建临时文件名（保留原始扩展名）
                    doc_title = doc.title or f"文档-{request.file_token}"
                    
                    # 确保文件名有效，同时保留原始扩展名
                    file_extension = ""
                    if doc.title.lower().endswith('.pdf'):
                        file_extension = '.pdf'
                    elif doc.title.lower().endswith('.docx'):
                        file_extension = '.docx'
                    elif doc.title.lower().endswith('.xlsx'):
                        file_extension = '.xlsx'
                    elif doc.title.lower().endswith('.pptx'):
                        file_extension = '.pptx'
                    
                    # 对于file类型，需要先去掉扩展名再处理文件名
                    doc_title_base = doc_title[:-len(file_extension)] if file_extension else doc_title
                    doc_title_safe = "".join(c for c in doc_title_base if c.isalnum() or c in [' ', '.', '_', '-']).strip()
                    if not doc_title_safe:
                        doc_title_safe = f"doc_{request.file_token}"
                        
                    # 添加回文件扩展名
                    if file_extension:
                        doc_title_safe = f"{doc_title_safe}{file_extension}"
                    
                    temp_file_path = temp_dir / doc_title_safe
                    
                    # 记录文件处理开始
                    logger.info(f"[文件处理] 开始处理文件: file_token={request.file_token}, 标题={doc_title}, 类型={file_extension}")
                    
                    # 下载文件
                    logger.info(f"[文件处理] 开始下载文件: file_token={request.file_token}, 目标路径={temp_file_path}")
                    download_result = await feishu_service.download_file(
                        request.app_id,
                        request.file_token,
                        str(temp_file_path)
                    )
                    
                    if download_result.get("code") != 0:
                        logger.error(f"[文件处理] 下载文件失败: file_token={request.file_token}, 错误={download_result.get('msg')}")
                        await fastgpt_service.close()
                        
                        # 根据错误类型返回不同的信息
                        error_msg = download_result.get('msg', '下载失败')
                        status_code = download_result.get('status_code')
                        
                        if status_code == 404 or "文件不存在或已被删除" in error_msg:
                            return {
                                "code": -1,
                                "msg": f"文件不存在或已被删除，可能是文件token已过期: {error_msg}",
                                "data": {
                                    "file_token": request.file_token,
                                    "error_type": "file_not_found",
                                    "recoverable": False
                                }
                            }
                        elif status_code == 403 or "无权限访问" in error_msg:
                            return {
                                "code": -1,
                                "msg": f"无权限访问文件: {error_msg}",
                                "data": {
                                    "file_token": request.file_token,
                                    "error_type": "permission_denied",
                                    "recoverable": True
                                }
                            }
                        else:
                            return {
                                "code": -1,
                                "msg": f"下载文件失败: {error_msg}",
                                "data": {
                                    "file_token": request.file_token,
                                    "error_type": "download_failed",
                                    "recoverable": True
                                }
                            }
                    
                    # 检查文件是否成功下载及文件大小
                    if temp_file_path.exists():
                        file_size = temp_file_path.stat().st_size
                        logger.info(f"[文件处理] 成功下载文件: file_token={request.file_token}, 本地路径={temp_file_path}, 文件大小={file_size}字节")
                    else:
                        logger.error(f"[文件处理] 下载后未找到文件: {temp_file_path}")
                        await fastgpt_service.close()
                        return {
                            "code": -1,
                            "msg": f"下载文件后未找到文件: {temp_file_path}",
                            "data": None
                        }
                    
                    # 对于这些文件类型，不需要获取内容，直接上传文件
                    doc_title = doc.title or f"文档-{request.file_token}"
                elif is_markdown_doc:
                    # 对于docx、sheet等云文档，获取文档内容
                    content_result = await feishu_service.get_doc_content(
                        request.app_id, 
                        request.file_token, 
                        request.file_type,
                        use_filtered_blocks=True  # 默认使用我们自己实现的filtered-blocks处理逻辑
                    )
                    
                    if content_result.get("code") != 0:
                        logger.error(f"[内容获取] 获取文档内容失败: file_token={request.file_token}, 错误={content_result.get('msg')}")
                        await fastgpt_service.close()
                        return {
                            "code": -1,
                            "msg": f"获取文档内容失败: {content_result.get('msg', '未知错误')}",
                            "data": None
                        }
                    
                    # 提取文档内容
                    document_content = content_result.get("data", {}).get("content", "")
                    content_method = content_result.get("data", {}).get("method", "unknown")
                    
                    logger.info(f"[内容获取] 成功获取{request.file_type}文档内容: file_token={request.file_token}, 方法={content_method}, 内容长度={len(document_content)}")
                    
                    doc_title = doc.title or f"文档-{request.file_token}"
                    
                    # 检查是否是占位文件：如果markdown内容只有一行并且是#开头，说明是空的占位文件 如果是获取所有块模式则直接是空
                    if not document_content or (document_content.strip().startswith("#") and len(document_content.strip().split("\n")) == 1):
                        logger.info(f"检测到占位文件，跳过同步到FastGPT: 文档标题='{doc_title}', 内容='{document_content.strip()}'")
                        
                        # 标记为已同步，但不实际同步到FastGPT
                        success = await feishu_service.update_doc_aichat_time(
                            request.app_id,
                            request.file_token,
                            True
                        )
                        
                        await fastgpt_service.close()
                        
                        if success:
                            return {
                                "code": 0,
                                "msg": "检测到占位文件，已标记为同步完成",
                                "data": {
                                    "file_token": request.file_token,
                                    "placeholder_file": True,
                                    "skipped_sync": True,
                                    "reason": "文档内容与标题相同，判断为占位文件"
                                }
                            }
                        else:
                            return {
                                "code": -1,
                                "msg": "更新占位文件同步状态失败",
                                "data": None
                            }
                    
                    # 对于云文档和电子表格，需要将内容保存到临时文件
                    temp_dir = Path("temp")
                    temp_dir.mkdir(exist_ok=True)
                    
                    # 使用文档标题创建临时文件名，确保文件名有效
                    doc_title_safe = "".join(c for c in doc_title if c.isalnum() or c in [' ', '.', '_', '-']).strip()
                    if not doc_title_safe:
                        doc_title_safe = f"doc_{request.file_token}"
                    
                    temp_file_path = temp_dir / f"{doc_title_safe}.md"
                    
                    # 写入文档内容到临时文件
                    try:
                        with open(temp_file_path, "w", encoding="utf-8") as f:
                            f.write(document_content)
                        logger.info(f"成功将{request.file_type}文档内容保存到临时文件: {temp_file_path}")
                    except Exception as e:
                        logger.error(f"保存{request.file_type}文档内容到临时文件失败: {str(e)}")
                        raise
                else:
                    logger.error(f"文档类型不支持: {request.file_type}")
                    await fastgpt_service.close()
                    return {
                        "code": -1,
                        "msg": f"文档类型不支持: {request.file_type}",
                        "data": None
                    }
            except Exception as e:
                logger.error(f"获取文档内容时发生异常: {str(e)}")
                await fastgpt_service.close()
                return {
                    "code": -1,
                    "msg": "获取文档内容失败",
                    "data": None
                }
            
            # 使用app_name作为根文件夹名称
            root_folder_name = app_config.app_name or f"飞书文档-{request.app_id}"
            
            # 查询根目录下是否有app_name同名文件夹
            list_result = await fastgpt_service.get_dataset_list()
            
            root_folder_id = None
            if list_result.get("code") == 200:
                # 查找同名文件夹
                items = list_result.get("data", [])
                for item in items:
                    if item.get("name") == root_folder_name and item.get("type") == "folder":
                        root_folder_id = item.get("_id")
                        logger.info(f"找到已存在的根文件夹: {root_folder_name}, ID: {root_folder_id}")
                        break
            
            # 如果没有找到同名文件夹，则创建
            if not root_folder_id:
                create_result = await fastgpt_service.create_folder(root_folder_name)
                if create_result.get("code") == 200:
                    root_folder_id = create_result.get("data")
                    logger.info(f"成功创建根文件夹: {root_folder_name}, ID: {root_folder_id}")
                else:
                    logger.error(f"创建根文件夹失败: {root_folder_name}, 错误: {create_result.get('message')}")
                    await fastgpt_service.close()
                    return {
                        "code": -1,
                        "msg": f"创建FastGPT根文件夹失败: {create_result.get('message', '未知错误')}",
                        "data": None
                    }
            
            # 获取知识空间信息
            wiki_space_name = "未知知识空间"
            if doc.space_id:
                logger.info(f"尝试获取知识空间信息，space_id: {doc.space_id}")
                space_info = await feishu_service.get_wiki_space(request.app_id, doc.space_id)
                logger.info(f"获取知识空间信息结果: code={space_info.get('code')}, data={space_info.get('data', {})}")
                
                if space_info.get("code") == 0 and space_info.get("data"):
                    # 飞书API返回的数据是嵌套的，name字段在space对象中
                    space_data = space_info.get("data", {})
                    # 正确获取嵌套字段
                    space_obj = space_data.get("space", {})
                    wiki_space_name = space_obj.get("name", "未知知识空间")
                    logger.info(f"成功获取知识空间名称: {wiki_space_name}")
                else:
                    logger.error(f"获取知识空间信息失败: {space_info.get('msg', '未知错误')}")
            else:
                logger.warning(f"文档 {doc.file_token} 没有关联的space_id，无法获取知识空间名称")
            
            # 在根文件夹下创建知识空间对应的文件夹
            wiki_folder_id = None
            wiki_folder_name = f"{wiki_space_name} - 飞书知识库"
            
            # 查询在根文件夹下是否已有知识空间文件夹
            wiki_folders_result = await fastgpt_service.get_dataset_list(parent_id=root_folder_id)
            
            if wiki_folders_result.get("code") == 200:
                # 查找同名知识空间文件夹
                items = wiki_folders_result.get("data", [])
                for item in items:
                    if item.get("name") == wiki_folder_name and item.get("type") == "folder":
                        wiki_folder_id = item.get("_id")
                        logger.info(f"找到已存在的知识空间文件夹: {wiki_folder_name}, ID: {wiki_folder_id}")
                        break
            
            # 如果没有找到知识空间文件夹，则创建
            if not wiki_folder_id:
                create_result = await fastgpt_service.create_folder(wiki_folder_name, parent_id=root_folder_id)
                if create_result.get("code") == 200:
                    wiki_folder_id = create_result.get("data")
                    logger.info(f"成功创建知识空间文件夹: {wiki_folder_name}, ID: {wiki_folder_id}")
                else:
                    logger.error(f"创建知识空间文件夹失败: {wiki_folder_name}, 错误: {create_result.get('message')}")
                    # 不中断流程，仍使用根文件夹
                    wiki_folder_id = root_folder_id
            
            # 获取文档的层级路径，如果有的话
            hierarchy_path = doc.hierarchy_path
            
            # 记录在日志中
            if hierarchy_path:
                logger.info(f"文档层级路径: {hierarchy_path}")
            
            # 记录当前文档处理类型
            logger.info(f"文档处理类型: direct_file_upload={is_direct_file_upload}, markdown_doc={is_markdown_doc}")
            
            logger.info(f"已创建完整目录结构:")
            logger.info(f"根文件夹: {root_folder_name} (ID: {root_folder_id})")
            logger.info(f"知识空间文件夹: {wiki_folder_name} (ID: {wiki_folder_id})")
            
            # 尝试将文档添加到目标位置
            try:
                # 处理所有文档 - 根据hierarchy_path的一级目录创建知识库
                if hierarchy_path:
                    # 检查是否是一级目录（不包含分隔符）
                    is_first_level = "###" not in hierarchy_path
                    
                    # 获取一级目录名称
                    first_level_name = hierarchy_path if is_first_level else hierarchy_path.split("###")[0]
                    logger.info(f"文档 '{doc_title}' 层级路径: {hierarchy_path}, {'一级目录' if is_first_level else '多级目录'}，一级目录名: {first_level_name}")
                    
                    # 确保一级目录名不为空
                    if first_level_name and first_level_name.strip():
                        # 创建知识库名称
                        first_level_dataset_name = f"{first_level_name} - 知识库"
                        first_level_dataset_id = None
                        
                        # 查询在知识空间文件夹下是否已有该一级目录对应的知识库
                        datasets_result = await fastgpt_service.get_dataset_list(parent_id=wiki_folder_id)
                        
                        if datasets_result.get("code") == 200:
                            items = datasets_result.get("data", [])
                            for item in items:
                                if item.get("name") == first_level_dataset_name and item.get("type") == "dataset":
                                    first_level_dataset_id = item.get("_id")
                                    logger.info(f"找到已存在的一级目录知识库: {first_level_dataset_name}, ID: {first_level_dataset_id}")
                                    break
                        
                        # 如果没有找到，则创建知识库
                        if not first_level_dataset_id:
                            create_result = await fastgpt_service.create_dataset(
                                name=first_level_dataset_name,
                                intro=f"{first_level_dataset_name}",
                                parent_id=wiki_folder_id
                            )
                            
                            if create_result.get("code") == 200:
                                first_level_dataset_id = create_result.get("data")
                                logger.info(f"成功创建一级目录知识库: {first_level_dataset_name}, ID: {first_level_dataset_id}")
                            else:
                                logger.error(f"创建一级目录知识库失败: {first_level_dataset_name}, 错误: {create_result.get('message')}")
                        
                        # 如果成功获取或创建知识库ID，上传文档
                        if first_level_dataset_id and temp_file_path:
                            # 步骤1：先根据hierarchy_path和obj_edit_time进行去重
                            if hierarchy_path and doc.obj_edit_time:
                                logger.info(f"[层级路径去重] 开始检查相同层级路径的旧版本文档: hierarchy_path={hierarchy_path}")
                                
                                try:
                                    # 查询同一应用下，相同hierarchy_path但obj_edit_time更早的记录
                                    old_docs_query = await feishu_service.db.execute(
                                        select(DocSubscription).where(
                                            DocSubscription.app_id == request.app_id,
                                            DocSubscription.hierarchy_path == hierarchy_path,
                                            DocSubscription.obj_edit_time < doc.obj_edit_time,
                                            DocSubscription.file_token != request.file_token,  # 排除当前文档
                                            DocSubscription.collection_id.isnot(None)  # 只处理有collection_id的记录
                                        )
                                    )
                                    old_docs = old_docs_query.scalars().all()
                                    
                                    if old_docs:
                                        logger.info(f"[层级路径去重] 发现 {len(old_docs)} 个需要删除的旧版本文档")
                                        
                                        deleted_collections = 0
                                        deleted_records = 0
                                        
                                        for old_doc in old_docs:
                                            try:
                                                # 删除FastGPT中的collection
                                                if old_doc.collection_id:
                                                    delete_result = await fastgpt_service.delete_collection(old_doc.collection_id)
                                                    if delete_result.get("code") == 200:
                                                        deleted_collections += 1
                                                        logger.info(f"[层级路径去重] 成功删除旧版本collection: file_token={old_doc.file_token}, collection_id={old_doc.collection_id}")
                                                    else:
                                                        logger.warning(f"[层级路径去重] 删除collection失败: {delete_result.get('msg')}")
                                                
                                                # 删除数据库记录
                                                await feishu_service.db.execute(
                                                    delete(DocSubscription).where(DocSubscription.id == old_doc.id)
                                                )
                                                deleted_records += 1
                                                logger.info(f"[层级路径去重] 成功删除旧版本记录: file_token={old_doc.file_token}, title={old_doc.title}")
                                                
                                            except Exception as e:
                                                logger.error(f"[层级路径去重] 删除旧版本文档异常: file_token={old_doc.file_token}, error={str(e)}")
                                        
                                        # 提交数据库更改
                                        await feishu_service.db.commit()
                                        
                                        logger.info(f"[层级路径去重] 完成旧版本清理: 删除了 {deleted_collections} 个collection, {deleted_records} 条记录")
                                    else:
                                        logger.info(f"[层级路径去重] 未发现需要删除的旧版本文档")
                                        
                                except Exception as e:
                                    logger.error(f"[层级路径去重] 执行层级路径去重时发生异常: {str(e)}")
                                    # 去重失败不影响后续上传流程，继续执行
                            
                            # 步骤2：按文件名删除可能存在的重复文档
                            doc_title_for_dedup = doc.title or f"文档-{request.file_token}"
                            
                            logger.info(f"[文件去重] 开始检查重复文档: filename={doc_title_for_dedup}, dataset_id={first_level_dataset_id}")
                            
                            try:
                                # 按文件名删除重复的文档
                                dedup_result = await fastgpt_service.delete_collections_by_name(
                                    dataset_id=first_level_dataset_id,
                                    filename=doc_title_for_dedup,  # 直接使用完整文件名（包含扩展名）
                                    parent_id=None
                                )
                                
                                if dedup_result.get("code") == 0:
                                    deleted_count = dedup_result.get("deleted_count", 0)
                                    if deleted_count > 0:
                                        logger.info(f"[文件去重] 成功删除 {deleted_count} 个重复文档: {doc_title_for_dedup}")
                                    else:
                                        logger.info(f"[文件去重] 未发现重复文档: {doc_title_for_dedup}")
                                else:
                                    logger.warning(f"[文件去重] 去重检查失败: {dedup_result.get('msg')}")
                            except Exception as e:
                                logger.error(f"[文件去重] 执行去重时发生异常: {str(e)}")
                                # 去重失败不影响后续上传流程，继续执行
                            
                            if is_direct_file_upload:
                                # 文件处理 - 直接上传原始文件
                                logger.info(f"[文件处理] 准备上传{temp_file_path.suffix}文件到一级目录知识库: dataset_id={first_level_dataset_id}, file_path={temp_file_path}, 文件大小={temp_file_path.stat().st_size}字节")
                                try:
                                    upload_result = await fastgpt_service.upload_file_to_dataset(
                                        dataset_id=first_level_dataset_id,
                                        file_path=str(temp_file_path)
                                    )
                                    logger.info(f"[文件处理] FastGPT上传响应: {upload_result}")
                                except Exception as e:
                                    logger.error(f"[文件处理] 上传{temp_file_path.suffix}文件到FastGPT时发生异常: {str(e)}")
                                    raise
                            else:
                                # Markdown文件的处理
                                # 为sheet类型文档设置更大的chunk_size
                                chunk_size = 5120 if request.file_type == "sheet" else 512
                                logger.info(f"[Markdown处理] 文档类型: {request.file_type}, chunk_size: {chunk_size}")
                                
                                upload_result = await fastgpt_service.upload_file_to_dataset(
                                    dataset_id=first_level_dataset_id,
                                    file_path=str(temp_file_path),
                                    chunk_size=chunk_size
                                )
                            
                            if upload_result.get("code") == 200:
                                collection_id = upload_result.get("data", {}).get("collectionId")
                                if collection_id:
                                    # 更新数据库中的FastGPT知识库ID
                                    await feishu_service.db.execute(
                                        update(DocSubscription)
                                        .where(
                                            DocSubscription.app_id == request.app_id,
                                            DocSubscription.file_token == request.file_token
                                        )
                                        .values(collection_id=collection_id)
                                    )
                                    await feishu_service.db.commit()
                                    logger.info(f"成功更新文档的FastGPT知识库ID: {collection_id}")
                                    
                                    # 添加到文件名目录索引
                                    if hierarchy_path:
                                        try:
                                            index_result = await fastgpt_service.add_to_filename_directory_index(
                                                hierarchy_path=hierarchy_path,
                                                collection_id=collection_id
                                            )
                                            if index_result.get("code") == 200:
                                                logger.info(f"成功添加文件名目录索引: hierarchy_path={hierarchy_path}, collection_id={collection_id}")
                                            else:
                                                logger.warning(f"添加文件名目录索引失败，但不影响主流程: {index_result.get('message')}")
                                        except Exception as e:
                                            logger.warning(f"添加文件名目录索引时发生异常，但不影响主流程: {str(e)}")
                                
                                # 生成并更新dataset描述
                                try:
                                    if first_level_dataset_id:
                                        desc_result = await fastgpt_service.generate_and_update_dataset_description(first_level_dataset_id)
                                        if desc_result.get("code") == 200:
                                            logger.info(f"成功生成并更新dataset描述: dataset_id={first_level_dataset_id}, description={desc_result.get('data', {}).get('description', '')}")
                                        else:
                                            logger.info(f"生成dataset描述结果: {desc_result.get('message', '未知')}")
                                except Exception as e:
                                    logger.warning(f"生成dataset描述时发生异常，但不影响主流程: {str(e)}")
                                
                                logger.info(f"成功上传文档到一级目录知识库: {doc_title}, collection_id: {collection_id}")
                            else:
                                logger.error(f"上传文档到一级目录知识库失败: {doc_title}, 错误: {upload_result.get('message')}")
                        else:
                            logger.error(f"无法上传文档：未成功创建或获取一级目录知识库ID")
                    else:
                        logger.error(f"文档一级目录名称为空，无法处理: {hierarchy_path}")
                else:
                    logger.info(f"文档 '{doc_title}' 没有层级路径信息，无法确定归属的一级目录")
            except Exception as e:
                logger.error(f"添加文档时发生异常: {str(e)}")

            # 清理临时文件
            if temp_file_path and temp_file_path.exists():
                try:
                    import os
                    os.remove(temp_file_path)
                    logger.info(f"已清理临时文件: {temp_file_path}")
                except Exception as e:
                    logger.warning(f"清理临时文件失败: {str(e)}")
            
            
            # 更新文档同步时间
            success = await feishu_service.update_doc_aichat_time(
                request.app_id,
                request.file_token,
                True
            )
            
            if not success:
                await fastgpt_service.close()
                return {
                    "code": -1,
                    "msg": "更新AI知识库同步时间失败",
                    "data": None
                }
                
            # 关闭FastGPT服务
            await fastgpt_service.close()
            
            return {
                "code": 0,
                "msg": "成功处理文档同步请求",
                "data": {
                    "file_token": request.file_token,
                    "root_folder_id": root_folder_id,
                    "root_folder_name": root_folder_name,
                    "wiki_folder_id": wiki_folder_id,
                    "wiki_folder_name": wiki_folder_name,
                    "hierarchy_path": hierarchy_path,
                    "file_type": request.file_type
                }
            }
        except Exception as e:
            logger.error(f"同步文档到AI知识库时发生错误: {str(e)}")
            # 确保关闭FastGPT服务
            await fastgpt_service.close()
            raise
    except Exception as e:
        return {
            "code": -1,
            "msg": f"同步文档到AI知识库时发生错误: {str(e)}",
            "data": None
        } 

# 批量重置docx文件的AI知识库更新时间
@router.post("/reset-docx-aichat-time", response_model=SubscribeResponse)
async def reset_docx_aichat_update_time(
    app_id: str,
    db: AsyncSession = Depends(get_db)
):
    """重置docx文档的aichat_update_time为None，使其能够被重新同步
    
    仅影响docx类型的文档，用于强制重新同步所有docx文档
    """
    try:
        # 更新数据库中docx类型文档的aichat_update_time为None
        await db.execute(
            update(DocSubscription)
            .where(
                DocSubscription.app_id == app_id,
                DocSubscription.file_type == "docx"
            )
            .values(aichat_update_time=None)
        )
        await db.commit()
        
        # 查询受影响的文档数量
        count_query = await db.execute(
            select(func.count())
            .select_from(DocSubscription)
            .where(
                DocSubscription.app_id == app_id,
                DocSubscription.file_type == "docx",
                DocSubscription.status == 1
            )
        )
        affected_count = count_query.scalar_one() or 0
        
        logger.info(f"成功重置docx文档AI知识库更新时间: app_id={app_id}, 影响文档数={affected_count}")
        
        return {
            "code": 0,
            "msg": f"成功重置{affected_count}个docx文档的AI知识库更新时间",
            "data": {"affected_count": affected_count}
        }
        
    except Exception as e:
        logger.error(f"重置docx文档AI知识库更新时间失败: app_id={app_id}, error={str(e)}")
        return {
            "code": -1,
            "msg": f"重置失败: {str(e)}"
        }

# 测试sheet文档处理
@router.post("/test-sheet", response_model=SubscribeResponse)
async def test_sheet_processing(
    request: TestSheetRequest,
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """测试飞书电子表格文档处理功能
    
    这个接口可以用来测试sheet类型文档的处理流程：
    1. 获取电子表格的所有工作表列表
    2. 读取每个工作表的内容
    3. 转换为Markdown格式
    
    Args:
        request: 包含app_id和sheet_token的请求
        
    Returns:
        处理后的Markdown内容和详细的处理信息
    """
    try:
        logger.info(f"开始测试sheet文档处理: app_id={request.app_id}, sheet_token={request.sheet_token}")
        
        # 1. 获取工作表列表
        sheets_result = await feishu_service.get_spreadsheet_sheets(request.app_id, request.sheet_token)
        if sheets_result.get("code") != 0:
            return {
                "code": sheets_result.get("code", -1),
                "msg": f"获取工作表列表失败: {sheets_result.get('msg')}",
                "data": None
            }
        
        sheets = sheets_result.get("data", {}).get("sheets", [])
        logger.info(f"成功获取工作表列表: 共{len(sheets)}个工作表")
        
        # 2. 获取完整文档内容（使用已有的方法）
        content_result = await feishu_service.get_sheet_doc_content(request.app_id, request.sheet_token)
        
        if content_result.get("code") != 0:
            return {
                "code": content_result.get("code", -1),
                "msg": f"获取文档内容失败: {content_result.get('msg')}",
                "data": None
            }
        
        # 3. 准备详细的响应数据
        markdown_content = content_result.get("data", {}).get("content", "")
        
        # 获取每个工作表的基本信息
        sheets_info = []
        for sheet in sheets:
            sheet_info = {
                "sheet_id": sheet.get("sheet_id"),
                "title": sheet.get("title"),
                "index": sheet.get("index"),
                "hidden": sheet.get("hidden", False),
                "grid_properties": sheet.get("grid_properties", {})
            }
            sheets_info.append(sheet_info)
        
        logger.info(f"成功处理sheet文档: sheet_token={request.sheet_token}, 内容长度={len(markdown_content)}")
        
        return {
            "code": 0,
            "msg": "成功处理电子表格文档",
            "data": {
                "sheet_token": request.sheet_token,
                "total_sheets": len(sheets),
                "sheets_info": sheets_info,
                "markdown_content": markdown_content,
                "content_length": len(markdown_content),
                "method": "sheet-api"
            }
        }
        
    except Exception as e:
        logger.error(f"测试sheet文档处理异常: app_id={request.app_id}, sheet_token={request.sheet_token}, error={str(e)}")
        return {
            "code": -1,
            "msg": f"处理异常: {str(e)}",
            "data": None
        }

# 获取电子表格工作表列表
@router.get("/{app_id}/sheet/{sheet_token}/sheets", response_model=SubscribeResponse)
async def get_sheet_list(
    app_id: str,
    sheet_token: str,
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """获取电子表格的工作表列表
    
    Args:
        app_id: 应用ID
        sheet_token: 电子表格Token
        
    Returns:
        工作表列表信息
    """
    result = await feishu_service.get_spreadsheet_sheets(app_id, sheet_token)
    
    return {
        "code": result.get("code", -1),
        "msg": result.get("msg", ""),
        "data": result.get("data")
    }

# 获取单个工作表内容
@router.get("/{app_id}/sheet/{sheet_token}/{sheet_id}", response_model=SubscribeResponse)
async def get_sheet_content(
    app_id: str,
    sheet_token: str,
    sheet_id: str,
    range_str: str = Query(None, description="读取范围，如A1:Z100，为空则读取整个工作表"),
    value_render_option: str = Query("FormattedValue", description="单元格数据格式：ToString、Formula、FormattedValue、UnformattedValue"),
    date_time_render_option: str = Query("FormattedString", description="日期时间格式：FormattedString"),
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """获取单个工作表的内容
    
    Args:
        app_id: 应用ID
        sheet_token: 电子表格Token
        sheet_id: 工作表ID
        range_str: 读取范围（可选）
        value_render_option: 单元格数据格式
        date_time_render_option: 日期时间格式
        
    Returns:
        工作表内容数据
    """
    result = await feishu_service.get_sheet_content(
        app_id, 
        sheet_token, 
        sheet_id, 
        range_str,
        value_render_option,
        date_time_render_option
    )
    
    return {
        "code": result.get("code", -1),
        "msg": result.get("msg", ""),
        "data": result.get("data")
    }

# 手动生成dataset描述
class TestDirectoryIndexRequest(BaseModel):
    app_id: str
    file_token: str
    file_type: str = "docx"  # 默认为docx，也可以是sheet、pdf等
    force_subscribe: bool = False  # 是否强制订阅文档（如果未订阅的话）

@router.post("/test-directory-index", response_model=SubscribeResponse)
async def test_directory_index_sync(
    request: TestDirectoryIndexRequest,
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """测试文件名目录索引功能
    
    手动输入app_id和file_token，测试文档同步和目录索引创建功能
    
    Args:
        request: 包含app_id、file_token、file_type等参数的请求体
        
    Returns:
        SubscribeResponse: 测试结果
    """
    try:
        logger.info(f"开始测试文件名目录索引功能: app_id={request.app_id}, file_token={request.file_token}, file_type={request.file_type}")
        
        # 查询文档信息
        query = await feishu_service.db.execute(
            select(DocSubscription).where(
                DocSubscription.app_id == request.app_id,
                DocSubscription.file_token == request.file_token
            )
        )
        doc = query.scalar_one_or_none()
        
        # 如果文档不存在且设置了强制订阅，先尝试订阅
        if not doc and request.force_subscribe:
            logger.info(f"文档未订阅，尝试先订阅文档: {request.file_token}")
            try:
                # 获取文档信息
                doc_info = await feishu_service.get_document_meta(request.app_id, request.file_token)
                if doc_info.get("code") == 0:
                    doc_data = doc_info.get("data", {})
                    title = doc_data.get("title", f"测试文档-{request.file_token}")
                    
                    # 订阅文档
                    subscribe_result = await feishu_service.subscribe_doc_events(
                        app_id=request.app_id,
                        file_token=request.file_token,
                        file_type=request.file_type,
                        title=title
                    )
                    
                    if subscribe_result.get("code") == 0:
                        logger.info(f"成功订阅文档: {title}")
                        # 重新查询文档
                        query = await feishu_service.db.execute(
                            select(DocSubscription).where(
                                DocSubscription.app_id == request.app_id,
                                DocSubscription.file_token == request.file_token
                            )
                        )
                        doc = query.scalar_one_or_none()
                    else:
                        logger.error(f"订阅文档失败: {subscribe_result.get('msg')}")
            except Exception as e:
                logger.error(f"尝试订阅文档时发生错误: {str(e)}")
        
        if not doc:
            return {
                "code": -1,
                "msg": f"找不到文档记录，请确保文档已订阅，或设置force_subscribe=true: app_id={request.app_id}, file_token={request.file_token}",
                "data": {
                    "suggestion": "你可以先调用订阅接口订阅文档，或者在请求中设置force_subscribe=true"
                }
            }
        
        logger.info(f"找到文档记录: title={doc.title}, file_type={doc.file_type}, hierarchy_path={doc.hierarchy_path}")
        
        # 创建同步请求
        sync_request = SyncDocToAIChatRequest(
            app_id=request.app_id,
            file_token=request.file_token,
            file_type=doc.file_type
        )
        
        # 调用同步函数
        result = await sync_document_to_aichat(sync_request, feishu_service)
        
        if result.get("code") == 0:
            return {
                "code": 0,
                "msg": "测试成功！文档已同步到FastGPT并创建了文件名目录索引",
                "data": {
                    "app_id": request.app_id,
                    "file_token": request.file_token,
                    "document_title": doc.title,
                    "hierarchy_path": doc.hierarchy_path,
                    "file_type": doc.file_type,
                    "collection_id": doc.collection_id,
                    "sync_result": result
                }
            }
        else:
            return {
                "code": result.get("code", -1),
                "msg": f"测试失败: {result.get('msg', '未知错误')}",
                "data": {
                    "app_id": request.app_id,
                    "file_token": request.file_token,
                    "error_details": result
                }
            }
            
    except Exception as e:
        logger.error(f"测试文件名目录索引功能时发生错误: {str(e)}")
        return {
            "code": -1,
            "msg": f"测试过程中发生错误: {str(e)}",
            "data": {
                "app_id": request.app_id,
                "file_token": request.file_token
            }
        }

@router.post("/test-index-only", response_model=SubscribeResponse)
async def test_index_only(
    hierarchy_path: str,
    collection_id: str,
    app_id: str
):
    """仅测试文件名目录索引功能（不进行文档同步）
    
    直接测试添加文件名目录索引，不需要实际的文档同步过程
    
    Args:
        hierarchy_path: 文档层级路径，如"AI产品资料###AI产品说明书###AI Product Description.docx"
        collection_id: FastGPT中的collection ID
        app_id: 应用ID
        
    Returns:
        SubscribeResponse: 测试结果
    """
    try:
        logger.info(f"开始测试文件名目录索引功能: hierarchy_path={hierarchy_path}, collection_id={collection_id}")
        
        # 初始化FastGPT服务
        from app.services.fastgpt_service import FastGPTService
        fastgpt_service = FastGPTService(app_id)
        
        try:
            # 直接调用索引功能
            result = await fastgpt_service.add_to_filename_directory_index(
                hierarchy_path=hierarchy_path,
                collection_id=collection_id
            )
            
            if result.get("code") == 200:
                return {
                    "code": 0,
                    "msg": "测试成功！文件名目录索引已创建",
                    "data": {
                        "hierarchy_path": hierarchy_path,
                        "collection_id": collection_id,
                        "index_result": result.get("data", {}),
                        "index_dataset_id": result.get("data", {}).get("index_dataset_id"),
                        "index_collection_id": result.get("data", {}).get("index_collection_id")
                    }
                }
            else:
                return {
                    "code": -1,
                    "msg": f"测试失败: {result.get('message', '未知错误')}",
                    "data": {
                        "hierarchy_path": hierarchy_path,
                        "collection_id": collection_id,
                        "error_details": result
                    }
                }
        finally:
            await fastgpt_service.close()
            
    except Exception as e:
        logger.error(f"测试文件名目录索引功能时发生错误: {str(e)}")
        return {
            "code": -1,
            "msg": f"测试过程中发生错误: {str(e)}",
            "data": {
                "hierarchy_path": hierarchy_path,
                "collection_id": collection_id
            }
        }

@router.post("/generate-dataset-description", response_model=SubscribeResponse)
async def generate_dataset_description(
    app_id: str,
    dataset_id: str
):
    """手动生成并更新dataset描述
    
    根据dataset中的collection列表调用LLM生成描述，并更新到dataset中
    
    Args:
        app_id: 应用ID
        dataset_id: 知识库ID
        
    Returns:
        dict: 生成结果
    """
    try:
        # 检查指定应用是否启用了dataset_sync
        app_config = next((app for app in settings.FEISHU_APPS if app.app_id == app_id), None)
        
        if not app_config:
            return {
                "code": -1,
                "msg": f"找不到应用配置: {app_id}",
                "data": None
            }
        
        if not app_config.dataset_sync:
            return {
                "code": 0,
                "msg": f"应用 {app_id} 的dataset_sync功能已禁用，跳过描述生成",
                "data": {
                    "dataset_sync_disabled": True
                }
            }
        
        # 初始化FastGPT服务
        from app.services.fastgpt_service import FastGPTService
        fastgpt_service = FastGPTService(app_id)
        
        try:
            # 生成并更新dataset描述
            result = await fastgpt_service.generate_and_update_dataset_description(dataset_id)
            
            return {
                "code": result.get("code", -1),
                "msg": result.get("message", ""),
                "data": result.get("data")
            }
        finally:
            # 确保关闭FastGPT服务
            await fastgpt_service.close()
            
    except Exception as e:
        logger.error(f"手动生成dataset描述失败: app_id={app_id}, dataset_id={dataset_id}, error={str(e)}")
        return {
            "code": -1,
            "msg": f"生成dataset描述失败: {str(e)}",
            "data": None
        }


class RebuildDirectoryIndexRequest(BaseModel):
    app_id: str
    space_id: Optional[str] = None  # 选填，如果提供则只处理该空间的文档
    dry_run: Optional[bool] = False  # 是否仅预览，不实际创建


@router.post("/rebuild-directory-index", response_model=SubscribeResponse)
async def rebuild_directory_index(
    request: RebuildDirectoryIndexRequest,
    db: AsyncSession = Depends(get_db)
):
    """重建文件名目录索引
    
    扫描doc_subscription表中符合条件的文档记录，检查并创建缺失的文件名目录索引
    
    Args:
        request: 重建请求，包含以下参数：
                - app_id: 飞书应用ID（必填）
                - space_id: 知识空间ID（选填），如果提供则只处理该空间的文档
                - dry_run: 是否仅预览（默认False）
                  * True: 只扫描和分析，不实际创建索引
                  * False: 实际执行创建操作
                  
    Returns:
        SubscribeResponse: 重建结果
    """
    try:
        mode_text = "预览模式" if request.dry_run else "执行模式"
        space_filter = f"空间ID: {request.space_id}" if request.space_id else "全部空间"
        logger.info(f"🔧 收到文件名目录索引重建请求 - app_id: {request.app_id}, {space_filter}, {mode_text}")
        
        if request.dry_run:
            logger.warning("🔍 DRY RUN 模式：将只扫描和分析，不会实际创建任何索引")
        
        # 构建查询条件
        query_conditions = [
            DocSubscription.app_id == request.app_id,
            DocSubscription.status == 1,  # 必须是已订阅状态
            DocSubscription.hierarchy_path.isnot(None),  # 必须有层级路径
            DocSubscription.hierarchy_path != "",  # 层级路径不能为空
            DocSubscription.collection_id.isnot(None),  # 必须有collection_id
            DocSubscription.collection_id != ""  # collection_id不能为空
        ]
        
        # 如果指定了空间ID，添加空间过滤条件
        if request.space_id:
            query_conditions.append(DocSubscription.space_id == request.space_id)
        
        # 查询符合条件的文档记录
        logger.info(f"📊 开始扫描doc_subscription表...")
        query = await db.execute(
            select(DocSubscription).where(and_(*query_conditions))
        )
        documents = query.scalars().all()
        
        total_count = len(documents)
        logger.info(f"📊 扫描完成，找到 {total_count} 条符合条件的文档记录")
        
        if total_count == 0:
            return {
                "code": 0,
                "msg": "没有找到符合条件的文档记录",
                "data": {
                    "total_documents": 0,
                    "processed": 0,
                    "skipped": 0,
                    "created": 0,
                    "errors": 0
                }
            }
        
        # 创建FastGPT服务
        from app.services.fastgpt_service import FastGPTService
        fastgpt_service = FastGPTService(request.app_id)
        
        # 统计信息
        stats = {
            "total_documents": total_count,
            "processed": 0,
            "skipped": 0,
            "created": 0,
            "errors": 0,
            "error_details": []
        }
        
        try:
            logger.info(f"🚀 开始处理文档索引...")
            
            for i, doc in enumerate(documents, 1):
                try:
                    logger.info(f"[{i}/{total_count}] 处理文档: {doc.title or '未命名'} (token: {doc.file_token})")
                    stats["processed"] += 1
                    
                    # 检查索引是否已存在
                    index_exists = await check_index_exists(fastgpt_service, doc.collection_id)
                    
                    if index_exists:
                        logger.info(f"[{i}/{total_count}] ✓ 索引已存在，跳过: {doc.collection_id}.txt")
                        stats["skipped"] += 1
                        continue
                    
                    if request.dry_run:
                        logger.info(f"[{i}/{total_count}] 🔍 [预览] 将创建索引: {doc.hierarchy_path} -> {doc.collection_id}.txt")
                        stats["created"] += 1
                    else:
                        # 创建索引
                        logger.info(f"[{i}/{total_count}] 📝 创建索引: {doc.hierarchy_path} -> {doc.collection_id}.txt")
                        result = await fastgpt_service.add_to_filename_directory_index(
                            doc.hierarchy_path, 
                            doc.collection_id
                        )
                        
                        if result.get("code") == 200:
                            logger.info(f"[{i}/{total_count}] ✅ 成功创建索引: {doc.collection_id}.txt")
                            stats["created"] += 1
                        else:
                            error_msg = f"创建索引失败: {result.get('message', '未知错误')}"
                            logger.error(f"[{i}/{total_count}] ❌ {error_msg}")
                            stats["errors"] += 1
                            stats["error_details"].append({
                                "file_token": doc.file_token,
                                "title": doc.title,
                                "collection_id": doc.collection_id,
                                "error": error_msg
                            })
                
                except Exception as e:
                    error_msg = f"处理文档异常: {str(e)}"
                    logger.error(f"[{i}/{total_count}] ❌ {error_msg}")
                    stats["errors"] += 1
                    stats["error_details"].append({
                        "file_token": doc.file_token,
                        "title": doc.title,
                        "collection_id": doc.collection_id,
                        "error": error_msg
                    })
            
            # 输出最终统计
            logger.info("=" * 60)
            logger.info(f"📊 文件名目录索引重建完成统计")
            logger.info("=" * 60)
            logger.info(f"总文档数量: {stats['total_documents']}")
            logger.info(f"已处理数量: {stats['processed']}")
            logger.info(f"跳过数量（已存在）: {stats['skipped']}")
            logger.info(f"{'预计创建' if request.dry_run else '成功创建'}数量: {stats['created']}")
            logger.info(f"错误数量: {stats['errors']}")
            
            if stats['errors'] > 0:
                logger.warning("❌ 错误详情:")
                for i, error in enumerate(stats['error_details'], 1):
                    logger.warning(f"  {i}. {error['title']} ({error['file_token']}): {error['error']}")
            
            logger.info("=" * 60)
            
            # 移除error_details中的详细信息，避免响应过大
            response_data = stats.copy()
            response_data["error_count"] = len(stats["error_details"])
            if not request.dry_run:
                del response_data["error_details"]  # 只在实际执行时移除详细错误信息
            
            success_rate = (stats['created'] + stats['skipped']) / stats['total_documents'] if stats['total_documents'] > 0 else 0
            operation = "预览" if request.dry_run else "重建"
            
            return {
                "code": 0,
                "msg": f"文件名目录索引{operation}完成，成功率: {success_rate:.1%}",
                "data": response_data
            }
            
        finally:
            await fastgpt_service.close()
            
    except Exception as e:
        error_msg = f"文件名目录索引重建过程中发生异常: {str(e)}"
        logger.error(error_msg)
        
        return {
            "code": -1,
            "msg": error_msg,
            "data": None
        }


async def check_index_exists(fastgpt_service, collection_id: str) -> bool:
    """检查指定collection_id的索引是否已存在
    
    Args:
        fastgpt_service: FastGPT服务实例
        collection_id: 要检查的collection ID
        
    Returns:
        bool: 索引是否存在
    """
    try:
        # 获取应用名称作为文件夹名
        app_folder_name = getattr(fastgpt_service.app_config, 'app_name', None) or f"飞书应用-{fastgpt_service.app_id}"
        
        # 查找应用根文件夹
        app_folder_id = await fastgpt_service.find_or_create_folder(app_folder_name)
        if not app_folder_id:
            return False
        
        # 查找"文件名目录索引"知识库
        index_dataset_id = await fastgpt_service.find_or_create_dataset("文件名目录索引", parent_id=app_folder_id)
        if not index_dataset_id:
            return False
        
        # 搜索指定的索引文件
        search_filename = f"{collection_id}.txt"
        search_result = await fastgpt_service.get_collection_list(
            dataset_id=index_dataset_id,
            parent_id=None,
            search_text=search_filename
        )
        
        if search_result.get("code") != 200:
            return False
        
        collections = search_result.get("data", {}).get("list", [])
        return len(collections) > 0
        
    except Exception as e:
        logger.warning(f"检查索引存在性异常: {str(e)}")
        return False 