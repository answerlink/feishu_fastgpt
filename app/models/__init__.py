# 导入所有模型，确保它们被注册到Base.metadata中
from .feishu_token import FeishuToken
from .doc_subscription import DocSubscription
from .space_subscription import SpaceSubscription
from .user_chat_session import UserChatSession
from .user_search_preference import UserSearchPreference
from .user_memory import UserProfile, UserMemory, UserMemoryConfig, ChatMessage, ChatType

__all__ = [
    "FeishuToken",
    "DocSubscription", 
    "SpaceSubscription",
    "UserChatSession",
    "UserSearchPreference",
    "UserProfile",
    "UserMemory",
    "UserMemoryConfig",
    "ChatMessage",
    "ChatType"
] 