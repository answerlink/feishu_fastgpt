"""用户记忆管理API端点"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from app.services.user_memory_service import UserMemoryService
from app.core.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()
memory_service = UserMemoryService()


class MemoryExtractionRequest(BaseModel):
    """记忆提取请求"""
    app_id: str = Field(..., description="飞书应用ID")
    user_id: str = Field(..., description="用户ID")
    messages: List[Dict[str, Any]] = Field(..., description="对话消息列表")
    chat_id: Optional[str] = Field(None, description="聊天ID")
    chat_type: Optional[str] = Field(None, description="聊天类型：p2p(私聊) 或 group(群聊)")
    nickname: Optional[str] = Field(None, description="用户昵称")
    immediate: bool = Field(False, description="是否立即执行，否则延迟执行")


class MemorySearchRequest(BaseModel):
    """记忆搜索请求"""
    app_id: str = Field(..., description="飞书应用ID")
    user_id: str = Field(..., description="用户ID")
    query: str = Field(..., description="搜索关键词")
    limit: int = Field(5, description="返回数量限制")


class UserContextRequest(BaseModel):
    """用户上下文请求"""
    app_id: str = Field(..., description="飞书应用ID")
    user_id: str = Field(..., description="用户ID")
    query: Optional[str] = Field(None, description="搜索关键词")
    memory_types: Optional[List[str]] = Field(None, description="记忆类型过滤")
    importance_threshold: int = Field(3, description="重要性阈值")


@router.get("/profile/{app_id}/{user_id}")
async def get_user_profile(app_id: str, user_id: str):
    """获取用户画像"""
    try:
        profile = await memory_service.get_user_profile(app_id, user_id)
        if not profile:
            return {"app_id": app_id, "user_id": user_id, "profile": None, "message": "用户画像不存在"}
        
        return {
            "app_id": app_id,
            "user_id": user_id,
            "profile": profile,
            "message": "获取成功"
        }
        
    except Exception as e:
        logger.error(f"获取用户画像API失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取用户画像失败: {str(e)}")


@router.get("/memories/{app_id}/{user_id}")
async def get_user_memories(
    app_id: str,
    user_id: str,
    memory_types: Optional[str] = Query(None, description="记忆类型，逗号分隔"),
    limit: int = Query(10, description="返回数量限制"),
    importance_threshold: int = Query(3, description="重要性阈值")
):
    """获取用户记忆"""
    try:
        types_list = memory_types.split(",") if memory_types else None
        memories = await memory_service.get_user_memories(
            app_id, user_id, types_list, limit, importance_threshold
        )
        
        return {
            "app_id": app_id,
            "user_id": user_id,
            "memories": memories,
            "count": len(memories),
            "message": "获取成功"
        }
        
    except Exception as e:
        logger.error(f"获取用户记忆API失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取用户记忆失败: {str(e)}")


@router.post("/search")
async def search_memories(request: MemorySearchRequest):
    """搜索用户记忆"""
    try:
        memories = await memory_service.search_memories(
            request.app_id, request.user_id, request.query, request.limit
        )
        
        return {
            "app_id": request.app_id,
            "user_id": request.user_id,
            "query": request.query,
            "memories": memories,
            "count": len(memories),
            "message": "搜索成功"
        }
        
    except Exception as e:
        logger.error(f"搜索用户记忆API失败: {e}")
        raise HTTPException(status_code=500, detail=f"搜索用户记忆失败: {str(e)}")


@router.post("/context")
async def get_user_context(request: UserContextRequest):
    """获取用户上下文（画像+记忆）"""
    try:
        # 获取用户画像
        profile = await memory_service.get_user_profile(request.app_id, request.user_id)
        
        # 获取记忆
        if request.query:
            memories = await memory_service.search_memories(
                request.app_id, request.user_id, request.query, 10
            )
        else:
            memories = await memory_service.get_user_memories(
                request.app_id,
                request.user_id, 
                request.memory_types, 
                10, 
                request.importance_threshold
            )
        
        # 格式化上下文
        context = memory_service.format_user_context(profile, memories)
        
        return {
            "app_id": request.app_id,
            "user_id": request.user_id,
            "profile": profile,
            "memories": memories,
            "context": context,
            "message": "获取成功"
        }
        
    except Exception as e:
        logger.error(f"获取用户上下文API失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取用户上下文失败: {str(e)}")


@router.post("/extract")
async def extract_memories(request: MemoryExtractionRequest):
    """提取记忆"""
    try:
        if request.immediate:
            # 立即执行
            await memory_service.extract_memories(
                request.app_id, request.user_id, request.messages, 
                request.chat_id, request.chat_type, request.nickname
            )
            message = "记忆提取完成"
        else:
            # 延迟执行
            await memory_service.schedule_memory_extraction(
                request.app_id, request.user_id, request.messages, 
                request.chat_id, request.chat_type, request.nickname
            )
            message = f"已调度记忆提取任务，{memory_service.memory_extraction_delay}秒后执行"
        
        return {
            "app_id": request.app_id,
            "user_id": request.user_id,
            "immediate": request.immediate,
            "message": message
        }
        
    except Exception as e:
        logger.error(f"提取记忆API失败: {e}")
        raise HTTPException(status_code=500, detail=f"提取记忆失败: {str(e)}")


@router.get("/stats/{app_id}/{user_id}")
async def get_memory_stats(app_id: str, user_id: str):
    """获取记忆统计信息"""
    try:
        stats = await memory_service.get_memory_stats(app_id, user_id)
        return {
            "stats": stats,
            "message": "获取成功"
        }
        
    except Exception as e:
        logger.error(f"获取记忆统计API失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取记忆统计失败: {str(e)}")


@router.get("/config/memory-types")
async def get_memory_types():
    """获取记忆类型配置"""
    try:
        from app.models.user_memory import UserMemoryConfig
        
        return {
            "memory_types": UserMemoryConfig.MEMORY_TYPES,
            "profile_schema": UserMemoryConfig.PROFILE_SCHEMA,
            "memory_schema": UserMemoryConfig.MEMORY_SCHEMA,
            "message": "获取成功"
        }
        
    except Exception as e:
        logger.error(f"获取记忆类型配置API失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取配置失败: {str(e)}")


@router.delete("/profile/{app_id}/{user_id}")
async def delete_user_profile(app_id: str, user_id: str):
    """删除用户画像（软删除）"""
    try:
        # 使用memory_service来处理删除操作
        if hasattr(memory_service, 'SessionLocal') and memory_service.SessionLocal:
            with memory_service.SessionLocal() as db:
                from app.models.user_memory import UserProfile
                
                profile = db.query(UserProfile).filter(
                    UserProfile.app_id == app_id,
                    UserProfile.user_id == user_id
                ).first()
                
                if profile:
                    profile.is_active = False
                    db.commit()
                    return {"app_id": app_id, "user_id": user_id, "message": "用户画像已删除"}
                else:
                    return {"app_id": app_id, "user_id": user_id, "message": "用户画像不存在"}
        else:
            return {"app_id": app_id, "user_id": user_id, "message": "数据库连接不可用"}
                
    except Exception as e:
        logger.error(f"删除用户画像API失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除用户画像失败: {str(e)}")


@router.delete("/memories/{app_id}/{user_id}")
async def delete_user_memories(
    app_id: str,
    user_id: str,
    memory_types: Optional[str] = Query(None, description="要删除的记忆类型，逗号分隔")
):
    """删除用户记忆（软删除）"""
    try:
        # 使用memory_service来处理删除操作
        if hasattr(memory_service, 'SessionLocal') and memory_service.SessionLocal:
            with memory_service.SessionLocal() as db:
                from app.models.user_memory import UserMemory
                
                query = db.query(UserMemory).filter(
                    UserMemory.app_id == app_id,
                    UserMemory.user_id == user_id,
                    UserMemory.is_active == True
                )
                
                if memory_types:
                    types_list = memory_types.split(",")
                    query = query.filter(UserMemory.memory_type.in_(types_list))
                
                memories = query.all()
                deleted_count = len(memories)
                
                for memory in memories:
                    memory.is_active = False
                
                db.commit()
                
                return {
                    "app_id": app_id,
                    "user_id": user_id,
                    "deleted_count": deleted_count,
                    "memory_types": memory_types,
                    "message": f"已删除 {deleted_count} 条记忆"
                }
        else:
            return {
                "app_id": app_id,
                "user_id": user_id,
                "deleted_count": 0,
                "message": "数据库连接不可用"
            }
                
    except Exception as e:
        logger.error(f"删除用户记忆API失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除用户记忆失败: {str(e)}") 