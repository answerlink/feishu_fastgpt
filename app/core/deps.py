from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from app.db.session import get_db
from app.services.feishu_service import FeishuService

async def get_feishu_service(db: AsyncSession = Depends(get_db)) -> FeishuService:
    """获取飞书服务实例"""
    service = FeishuService(db)
    try:
        yield service
    finally:
        await service.client.close() 