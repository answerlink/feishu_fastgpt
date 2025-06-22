from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings
from app.db.base import Base
from sqlalchemy.orm import sessionmaker
from app.services.feishu_service import FeishuService

# 创建异步引擎
engine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URI,  # 直接使用配置的URI，不再替换
    echo=settings.SQLALCHEMY_ECHO,
    pool_size=settings.SQLALCHEMY_POOL_SIZE,
    pool_timeout=settings.SQLALCHEMY_POOL_TIMEOUT,
    pool_recycle=settings.SQLALCHEMY_POOL_RECYCLE,
    pool_pre_ping=False,  # 关闭预ping避免异步问题
    pool_reset_on_return='commit',  # 连接返回时重置状态
    # 添加连接清理配置
    max_overflow=0,  # 禁用溢出连接
    connect_args={
        "autocommit": False,
        "charset": "utf8mb4",
        # 添加连接超时设置
        "connect_timeout": 10,
    }
)

# 创建异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def init_db():
    """初始化数据库"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db() -> AsyncSession:
    """异步数据库会话依赖"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
            
async def get_feishu_service():
    """获取FeishuService实例的依赖
    
    使用异步上下文管理器确保客户端会话正确关闭
    """
    from app.services.feishu_service import FeishuService
    
    async with AsyncSessionLocal() as session:
        service = FeishuService(session)
        try:
            yield service
        finally:
            await service.close()
            await session.close()

async def get_fastgpt_service(app_id: str) -> "FastGPTService":
    """获取FastGPT服务实例依赖
    
    Args:
        app_id: 应用ID，用于获取对应的FastGPT配置
        
    Returns:
        FastGPTService: FastGPT服务实例
    """
    from app.services.fastgpt_service import FastGPTService
    
    service = FastGPTService(app_id)
    yield service
    await service.close() 