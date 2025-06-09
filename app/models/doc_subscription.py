from sqlalchemy import Column, Integer, String, DateTime, SmallInteger, func, UniqueConstraint, Text, Index
from app.db.base import Base

class DocSubscription(Base):
    """文档订阅模型
    
    用于记录已订阅的云文档信息，包括文档基本信息、订阅状态和同步时间等。
    每个记录代表一个应用订阅了一篇特定的飞书文档。
    
    Attributes:
        id: 自增主键
        app_id: 应用ID，关联到飞书应用
        file_token: 文档Token，飞书文档的唯一标识
        file_type: 文档类型，如docx、sheet等
        space_id: 所属知识空间ID
        title: 文档标题
        hierarchy_path: 文档层级路径，使用###分隔各层级，例如"首页###产品资料###技术建议书"
        status: 订阅状态，1表示已订阅，0表示已取消
        obj_edit_time: 云文档最后编辑时间，用于跟踪文档变更
        aichat_update_time: 更新到AI知识库的时间，用于确定是否需要同步
        collection_id: FastGPT知识库中的文档ID，用于跟踪文档在FastGPT中的位置
        created_at: 记录创建时间
        updated_at: 记录更新时间
    """
    __tablename__ = "doc_subscription"
    
    id = Column(Integer, primary_key=True, index=True, comment="自增主键ID")
    app_id = Column(String(50), nullable=False, index=True, comment="应用ID")
    file_token = Column(String(100), nullable=False, index=True, comment="文档Token，文档唯一标识")
    file_type = Column(String(20), nullable=False, comment="文档类型，如docx、sheet等")
    space_id = Column(String(100), index=True, comment="所属知识空间ID")
    title = Column(String(255), comment="文档标题")
    hierarchy_path = Column(Text, nullable=True, comment="文档层级路径，使用###分隔各层级")
    status = Column(SmallInteger, default=1, comment="订阅状态，1: 已订阅, 0: 已取消")
    obj_edit_time = Column(DateTime, nullable=True, comment="云文档最后更新时间")
    aichat_update_time = Column(DateTime, nullable=True, comment="更新到AI知识库的时间")
    collection_id = Column(String(100), nullable=True, comment="FastGPT知识库中的文档ID")
    created_at = Column(DateTime, default=func.now(), comment="记录创建时间")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment="记录更新时间")
    
    __table_args__ = (
        UniqueConstraint('app_id', 'file_token', name='uix_subscription_app_file'),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci", "comment": "文档订阅表"},
    )