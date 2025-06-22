from fastapi import APIRouter, HTTPException, Query
from app.services.chat_message_service import chat_message_service
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/group-chats/{app_id}/{chat_id}/stats")
async def get_group_chat_stats(
    app_id: str,
    chat_id: str,
    days: int = Query(default=7, description="统计天数")
):
    """获取群聊统计信息"""
    try:
        stats = await chat_message_service.get_chat_statistics(app_id, chat_id, days)
        return {
            "code": 0,
            "msg": "success",
            "data": stats
        }
    except Exception as e:
        logger.error(f"获取群聊统计失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/group-chats/{app_id}/{chat_id}/messages")
async def get_group_chat_messages(
    app_id: str,
    chat_id: str,
    limit: int = Query(default=10, description="消息数量限制")
):
    """获取群聊最近消息"""
    try:
        messages = await chat_message_service.get_recent_messages(app_id, chat_id, limit)
        group_stats = await chat_message_service.get_chat_statistics(app_id, chat_id)
        
        return {
            "code": 0,
            "msg": "success",
            "data": {
                "messages": messages,
                "stats": group_stats
            }
        }
    except Exception as e:
        logger.error(f"获取群聊消息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/group-chats/{app_id}/{chat_id}/context")
async def get_group_chat_context(
    app_id: str,
    chat_id: str,
    context_limit: int = Query(default=5, description="上下文消息数量")
):
    """获取群聊上下文"""
    try:
        context = await chat_message_service.get_context_for_reply(app_id, chat_id, context_limit)
        group_stats = await chat_message_service.get_chat_statistics(app_id, chat_id)
        
        return {
            "code": 0,
            "msg": "success",
            "data": {
                "context": context,
                "stats": group_stats
            }
        }
    except Exception as e:
        logger.error(f"获取群聊上下文失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
