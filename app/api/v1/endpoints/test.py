from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.services.feishu_service import FeishuService
from app.core.logger import setup_logger
from app.core.deps import get_feishu_service

router = APIRouter()
logger = setup_logger("api.test")

@router.get("/token/{app_id}")
async def test_token(
    app_id: str,
    feishu_service: FeishuService = Depends(get_feishu_service)
):
    """测试获取tenant_access_token"""
    logger.info(f"测试获取应用[{app_id}]的token")
    try:
        token = await feishu_service.get_tenant_access_token(app_id)
        logger.info(f"获取token成功: {token[:10]}...")
        return {"token": token}
    except Exception as e:
        logger.error(f"获取token失败: {str(e)}")
        raise

@router.get("/apps")
async def list_apps():
    """列出所有配置的应用"""
    from app.core.config import settings
    return {"apps": [{"app_id": app.app_id, "app_name": app.app_name} for app in settings.FEISHU_APPS]} 