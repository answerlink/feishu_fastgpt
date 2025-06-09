from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Dict, List, Optional
from pydantic import BaseModel
from app.services.feishu_service import FeishuService
from app.db.session import get_feishu_service

router = APIRouter()

# 请求模型
class SpaceSubscribeRequest(BaseModel):
    app_id: str
    space_id: str

class SpaceSubscriptionUpdateRequest(BaseModel):
    app_id: str
    space_id: str
    status: int  # 1: 已订阅, 0: 已取消

# 响应模型
class WikiResponse(BaseModel):
    code: int
    msg: str = ""
    data: Optional[Dict] = None

@router.get("/spaces", response_model=WikiResponse)
async def get_wiki_spaces(
    app_id: str,
    page_token: Optional[str] = None,
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """获取知识空间列表"""
    result = await feishu_service.get_wiki_spaces(app_id, page_token)
    
    return {
        "code": result.get("code", -1),
        "msg": result.get("msg", ""),
        "data": result.get("data")
    }

@router.get("/spaces/{space_id}", response_model=WikiResponse)
async def get_wiki_space(
    app_id: str,
    space_id: str,
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """获取单个知识空间信息"""
    result = await feishu_service.get_wiki_space(app_id, space_id)
    
    return {
        "code": result.get("code", -1),
        "msg": result.get("msg", ""),
        "data": result.get("data")
    }

@router.get("/spaces/{space_id}/nodes", response_model=WikiResponse)
async def get_wiki_nodes(
    app_id: str,
    space_id: str,
    parent_node_token: Optional[str] = None,
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """获取知识空间节点列表"""
    result = await feishu_service.get_wiki_nodes(app_id, space_id, parent_node_token)
    
    return {
        "code": result.get("code", -1),
        "msg": result.get("msg", ""),
        "data": result.get("data")
    }

@router.get("/subscriptions", response_model=WikiResponse)
async def get_space_subscriptions(
    app_id: str,
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """获取已订阅的知识空间列表"""
    result = await feishu_service.get_space_subscriptions(app_id)
    
    return {
        "code": result.get("code", -1),
        "msg": result.get("msg", ""),
        "data": result.get("data")
    }

@router.post("/subscriptions/update", response_model=WikiResponse)
async def update_space_subscription(
    request: SpaceSubscriptionUpdateRequest,
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """更新知识空间订阅状态"""
    # 如果是订阅操作，需要先获取空间信息
    space_info = None
    if request.status == 1:
        space_result = await feishu_service.get_wiki_space(request.app_id, request.space_id)
        if space_result.get("code") == 0 and space_result.get("data"):
            space_data = space_result.get("data")
            space_obj = space_data.get("space", {})
            space_info = {
                "name": space_obj.get("name"),
                "type": space_obj.get("space_type", "wiki")
            }
    
    result = await feishu_service.update_space_subscription(
        request.app_id,
        request.space_id,
        request.status,
        space_info
    )
    
    return {
        "code": result.get("code", -1),
        "msg": result.get("msg", ""),
        "data": result.get("data")
    }

@router.get("/docs/{doc_token}/content")
async def get_doc_content(
    doc_token: str,
    doc_type: str = Query("docx", description="文档类型，如docx"),
    content_type: str = Query("markdown", description="内容类型，如markdown"),
    lang: str = Query("zh", description="语言"),
    app_id: str = Query(..., description="应用ID"),
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """获取文档内容"""
    return await feishu_service.get_doc_content(app_id, doc_token, doc_type, content_type, lang) 