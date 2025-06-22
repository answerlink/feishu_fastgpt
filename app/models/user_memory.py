"""用户记忆模型 - 用于构建用户画像和记忆管理"""

from sqlalchemy import Column, String, Integer, Text, DateTime, Boolean, JSON, Index
from sqlalchemy.sql import func
from app.db.base_class import Base
from typing import Dict, Any, Optional, List
from datetime import datetime


class UserProfile(Base):
    """用户画像模型 - Patch模式记忆"""
    __tablename__ = "user_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    app_id = Column(String(255), nullable=False, index=True, comment="飞书应用ID")
    user_id = Column(String(255), nullable=False, index=True, comment="飞书用户ID")
    nickname = Column(String(255), comment="用户昵称")
    user_name = Column(String(255), comment="用户姓名")
    age = Column(Integer, comment="年龄")
    interests = Column(JSON, comment="兴趣爱好列表")
    home = Column(String(500), comment="居住地描述")
    occupation = Column(String(255), comment="职业")
    conversation_preferences = Column(JSON, comment="对话偏好")
    personality_traits = Column(JSON, comment="性格特征")
    work_context = Column(Text, comment="工作环境和背景")
    communication_style = Column(String(255), comment="沟通风格")
    timezone = Column(String(50), comment="时区")
    language_preference = Column(String(50), comment="语言偏好")
    
    # 元数据字段
    created_at = Column(DateTime, default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")
    is_active = Column(Boolean, default=True, comment="是否激活")
    
    # 复合索引：同一个app中的用户ID唯一
    __table_args__ = (
        Index('idx_app_user', 'app_id', 'user_id'),
        Index('idx_app_user_active', 'app_id', 'user_id', 'is_active'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "app_id": self.app_id,
            "user_id": self.user_id,
            "nickname": self.nickname,
            "user_name": self.user_name,
            "age": self.age,
            "interests": self.interests or [],
            "home": self.home,
            "occupation": self.occupation,
            "conversation_preferences": self.conversation_preferences or [],
            "personality_traits": self.personality_traits or [],
            "work_context": self.work_context,
            "communication_style": self.communication_style,
            "timezone": self.timezone,
            "language_preference": self.language_preference,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class UserMemory(Base):
    """用户记忆条目模型 - Insert模式记忆"""
    __tablename__ = "user_memories"
    
    id = Column(Integer, primary_key=True, index=True)
    app_id = Column(String(255), nullable=False, index=True, comment="飞书应用ID")
    user_id = Column(String(255), nullable=False, index=True, comment="飞书用户ID")
    memory_type = Column(String(100), index=True, nullable=False, comment="记忆类型")
    context = Column(Text, nullable=False, comment="记忆的上下文和相关情况")
    content = Column(Text, nullable=False, comment="记忆内容")
    importance = Column(Integer, default=5, comment="重要性评分 1-10")
    tags = Column(JSON, comment="标签列表")
    
    # 聊天来源信息
    source_chat_id = Column(String(255), comment="来源聊天ID")
    source_message_id = Column(String(255), comment="来源消息ID")
    chat_type = Column(String(50), comment="聊天类型：p2p(私聊) 或 group(群聊)")
    
    # 元数据字段
    created_at = Column(DateTime, default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")
    is_active = Column(Boolean, default=True, comment="是否激活")
    
    # 复合索引
    __table_args__ = (
        Index('idx_app_user_memory', 'app_id', 'user_id'),
        Index('idx_app_user_type', 'app_id', 'user_id', 'memory_type'),
        Index('idx_app_user_importance', 'app_id', 'user_id', 'importance'),
        Index('idx_chat_source', 'source_chat_id', 'chat_type'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "id": self.id,
            "app_id": self.app_id,
            "user_id": self.user_id,
            "memory_type": self.memory_type,
            "context": self.context,
            "content": self.content,
            "importance": self.importance,
            "tags": self.tags or [],
            "source_chat_id": self.source_chat_id,
            "source_message_id": self.source_message_id,
            "chat_type": self.chat_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class UserMemoryConfig:
    """用户记忆配置"""
    
    # 记忆类型定义
    MEMORY_TYPES = {
        "preference": "偏好",
        "experience": "经历",
        "skill": "技能",
        "relationship": "关系",
        "goal": "目标",
        "concern": "关注点",
        "habit": "习惯",
        "achievement": "成就",
        "project": "项目",
        "tool": "工具使用"
    }
    
    # 用户画像字段映射
    PROFILE_SCHEMA = {
        "type": "object",
        "properties": {
            "user_name": {
                "type": "string",
                "description": "用户的姓名或昵称"
            },
            "age": {
                "type": "integer",
                "description": "用户年龄"
            },
            "interests": {
                "type": "array",
                "items": {"type": "string"},
                "description": "用户的兴趣爱好列表"
            },
            "home": {
                "type": "string",
                "description": "用户的居住地、城市或地区描述"
            },
            "occupation": {
                "type": "string",
                "description": "用户的职业或工作"
            },
            "conversation_preferences": {
                "type": "array",
                "items": {"type": "string"},
                "description": "用户的对话偏好、沟通风格等"
            },
            "personality_traits": {
                "type": "array",
                "items": {"type": "string"},
                "description": "用户的性格特征和个性描述"
            },
            "work_context": {
                "type": "string",
                "description": "用户的工作环境、团队背景等"
            },
            "communication_style": {
                "type": "string",
                "description": "用户的沟通风格描述"
            },
            "timezone": {
                "type": "string",
                "description": "用户所在时区"
            },
            "language_preference": {
                "type": "string",
                "description": "用户的语言偏好"
            }
        }
    }
    
    # 记忆条目字段映射
    MEMORY_SCHEMA = {
        "type": "object",
        "properties": {
            "memory_type": {
                "type": "string",
                "enum": list(MEMORY_TYPES.keys()),
                "description": "记忆类型"
            },
            "context": {
                "type": "string",
                "description": "记忆的上下文和适用情况，包括任何限制条件"
            },
            "content": {
                "type": "string",
                "description": "具体的记忆内容、偏好或事件"
            },
            "importance": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "description": "重要性评分，1-10分"
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "相关标签"
            }
        },
        "required": ["memory_type", "context", "content"]
    }


class ChatMessage(Base):
    """聊天消息模型 - 统一存储私聊和群聊消息"""
    __tablename__ = "chat_messages"
    
    id = Column(Integer, primary_key=True, index=True, comment="自增ID")
    app_id = Column(String(100), nullable=False, index=True, comment="飞书应用ID")
    message_id = Column(String(100), nullable=False, index=True, comment="飞书消息ID")
    chat_type = Column(String(50), nullable=False, comment="聊天类型 单聊p2p 群聊group")
    chat_id = Column(String(100), nullable=False, index=True, comment="群聊ID")
    chat_name = Column(String(200), nullable=False, comment="群聊名称")
    sender_id = Column(String(100), nullable=False, index=True, comment="发送者ID")
    sender_name = Column(String(200), nullable=False, comment="发送者姓名")
    raw_content = Column(Text, nullable=False, comment="原始消息内容（替换@后）")
    pure_content = Column(Text, nullable=False, comment="纯净消息内容（去除@）")
    message_type = Column(String(50), comment="消息类型")
    mention_users = Column(JSON, comment="@的用户列表")
    mentioned_bot = Column(Boolean, comment="是否@了机器人")
    created_at = Column(DateTime, default=func.now(), comment="记录创建时间")
    
    # 复合索引
    __table_args__ = (
        Index('idx_app_chat_time', 'app_id', 'chat_id', 'created_at'),
        Index('idx_app_sender_time', 'app_id', 'sender_id', 'created_at'),
        Index('idx_chat_type_time', 'chat_type', 'created_at'),
        Index('idx_unique_message', 'app_id', 'message_id', unique=True),
        Index('idx_chat_mention', 'chat_id', 'mentioned_bot', 'created_at'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "id": self.id,
            "app_id": self.app_id,
            "message_id": self.message_id,
            "chat_type": self.chat_type,
            "chat_id": self.chat_id,
            "chat_name": self.chat_name,
            "sender_id": self.sender_id,
            "sender_name": self.sender_name,
            "raw_content": self.raw_content,
            "pure_content": self.pure_content,
            "message_type": self.message_type,
            "mention_users": self.mention_users or [],
            "mentioned_bot": self.mentioned_bot,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


# 聊天类型常量
class ChatType:
    """聊天类型常量"""
    P2P = "p2p"      # 私聊
    GROUP = "group"   # 群聊 