"""用户记忆服务 - 实现用户画像构建和记忆管理"""

import json
import asyncio
import aiohttp
import jieba
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy import and_, desc, func, or_
from app.db.session import AsyncSessionLocal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models.user_memory import UserProfile, UserMemory, UserMemoryConfig
from app.core.logger import setup_logger
from app.core.config import get_config

logger = setup_logger(__name__)


class UserMemoryService:
    """用户记忆服务"""
    
    def __init__(self):
        # 获取全局配置，用于通用LLM配置
        self.config = get_config()
        # 获取第一个应用配置，用于获取通用LLM配置
        self.app_config = settings.FEISHU_APPS[0] if settings.FEISHU_APPS else None
        
        self.memory_extraction_delay = 30  # 30秒延迟处理记忆
        self._pending_extractions = {}  # 存储待处理的记忆提取任务
        
        # 创建同步数据库会话（用于简化数据库操作）
        self._init_sync_db()
        
        # 创建HTTP客户端用于调用通用LLM
        self._client = None
        
        # 初始化中文分词器
        self._init_jieba()
    
    @property
    async def client(self):
        """获取HTTP客户端"""
        if self._client is None:
            self._client = aiohttp.ClientSession()
        return self._client
    
    async def close(self):
        """关闭HTTP客户端"""
        if self._client and not self._client.closed:
            await self._client.close()
            self._client = None
    
    def _init_jieba(self):
        """初始化jieba分词器"""
        try:
            # 设置jieba为安静模式，避免初始化日志
            jieba.setLogLevel(20)
            
            # 添加一些常用的技术词汇
            tech_words = [
                "软件工程师", "产品经理", "数据分析师", "UI设计师", "前端开发", "后端开发",
                "微服务", "数据库", "机器学习", "人工智能", "区块链", "云计算",
                "Python", "Java", "JavaScript", "React", "Vue", "Node.js",
                "MySQL", "MongoDB", "Redis", "Docker", "Kubernetes"
            ]
            
            for word in tech_words:
                jieba.add_word(word)
                
            logger.info("jieba分词器初始化完成")
            
        except Exception as e:
            logger.error(f"jieba分词器初始化失败: {e}")
    
    def _tokenize_query(self, query: str) -> List[str]:
        """对查询字符串进行分词
        
        Args:
            query: 查询字符串
            
        Returns:
            List[str]: 分词结果列表
        """
        try:
            # 清理查询字符串
            query = query.strip()
            if not query:
                return []
            
            # 使用jieba分词
            tokens = list(jieba.cut_for_search(query))
            
            # 过滤停用词和短词
            stop_words = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这'}
            
            # 过滤停用词、长度小于2的词、纯数字、纯英文字母
            filtered_tokens = []
            for token in tokens:
                token = token.strip()
                if (len(token) >= 2 and 
                    token not in stop_words and
                    not token.isdigit() and
                    not re.match(r'^[a-zA-Z]+$', token)):
                    filtered_tokens.append(token)
            
            logger.debug(f"查询分词: '{query}' -> {filtered_tokens}")
            return filtered_tokens
            
        except Exception as e:
            logger.error(f"查询分词失败: {e}")
            return [query]  # 分词失败时返回原查询
    
    def _init_sync_db(self):
        """初始化同步数据库会话"""
        try:
            # 将异步数据库URL转换为同步URL，使用pymysql驱动
            sync_url = settings.SQLALCHEMY_DATABASE_URI.replace('+aiomysql', '+pymysql')
            
            # 创建同步引擎
            self.sync_engine = create_engine(
                sync_url,
                echo=False,
                pool_size=5,
                pool_timeout=30,
                pool_recycle=3600,
                pool_pre_ping=True
            )
            
            # 创建会话工厂
            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.sync_engine
            )
            
            logger.info("同步数据库会话初始化成功")
            
        except Exception as e:
            logger.error(f"初始化同步数据库会话失败: {e}")
            self.SessionLocal = None
    
    async def call_general_llm(self, system_prompt: str, user_prompt: str) -> str:
        """调用通用LLM
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            
        Returns:
            str: LLM响应
        """
        # 检查配置
        if not self.app_config or not all([
            self.app_config.summary_llm_api_url,
            self.app_config.summary_llm_api_key,
            self.app_config.summary_llm_model
        ]):
            logger.warning("通用LLM配置不完整，跳过调用")
            return ""
        
        try:
            # 构建请求数据
            request_data = {
                "model": self.app_config.summary_llm_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 1000,
                "enable_thinking": False,
                "chat_template_kwargs": {
                    "enable_thinking": False
                }
            }
            
            headers = {
                "Authorization": f"Bearer {self.app_config.summary_llm_api_key}",
                "Content-Type": "application/json"
            }
            
            client = await self.client
            async with client.post(
                self.app_config.summary_llm_api_url,
                headers=headers,
                json=request_data
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    content = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    logger.info(f"通用LLM调用成功，响应长度: {len(content)}")
                    return content
                else:
                    error_text = await response.text()
                    logger.error(f"调用通用LLM失败: {response.status} - {error_text}")
                    return ""
        except Exception as e:
            logger.error(f"调用通用LLM异常: {str(e)}")
            return ""
        
    async def get_user_profile(self, app_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户画像"""
        try:
            if not self.SessionLocal:
                return None
                
            with self.SessionLocal() as db:
                profile = db.query(UserProfile).filter(
                    UserProfile.app_id == app_id,
                    UserProfile.user_id == user_id,
                    UserProfile.is_active == True
                ).first()
                
                if profile:
                    return profile.to_dict()
                return None
                
        except Exception as e:
            logger.error(f"获取用户画像失败: {e}")
            return None
    
    async def get_user_memories(
        self, 
        app_id: str,
        user_id: str, 
        memory_types: Optional[List[str]] = None,
        limit: int = 10,
        importance_threshold: int = 3
    ) -> List[Dict[str, Any]]:
        """获取用户记忆"""
        try:
            if not self.SessionLocal:
                return []
                
            with self.SessionLocal() as db:
                query = db.query(UserMemory).filter(
                    UserMemory.app_id == app_id,
                    UserMemory.user_id == user_id,
                    UserMemory.is_active == True,
                    UserMemory.importance >= importance_threshold
                )
                
                if memory_types:
                    query = query.filter(UserMemory.memory_type.in_(memory_types))
                
                memories = query.order_by(
                    desc(UserMemory.importance),
                    desc(UserMemory.updated_at)
                ).limit(limit).all()
                
                return [memory.to_dict() for memory in memories]
                
        except Exception as e:
            logger.error(f"获取用户记忆失败: {e}")
            return []
    
    async def search_memories(
        self, 
        app_id: str,
        user_id: str, 
        query: str, 
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """搜索相关记忆（使用分词器优化）"""
        try:
            if not self.SessionLocal:
                return []
            
            # 对查询进行分词
            query_tokens = self._tokenize_query(query)
            
            if not query_tokens:
                return []
            
            with self.SessionLocal() as db:
                # 构建基础查询
                base_query = db.query(UserMemory).filter(
                    UserMemory.app_id == app_id,
                    UserMemory.user_id == user_id,
                    UserMemory.is_active == True
                )
                
                # 分词匹配策略
                if len(query_tokens) == 1:
                    # 单个词：直接匹配
                    token = query_tokens[0]
                    memories = base_query.filter(
                        or_(
                            UserMemory.content.contains(token),
                            UserMemory.context.contains(token),
                            UserMemory.tags.contains(f'"{token}"')  # JSON数组中的精确匹配
                        )
                    ).order_by(
                        desc(UserMemory.importance),
                        desc(UserMemory.updated_at)
                    ).limit(limit).all()
                    
                else:
                    # 多个词：AND搜索（所有词都要匹配）+ OR搜索（任一词匹配）
                    # 优先返回所有词都匹配的结果
                    and_conditions = []
                    or_conditions = []
                    
                    for token in query_tokens:
                        token_condition = or_(
                            UserMemory.content.contains(token),
                            UserMemory.context.contains(token),
                            UserMemory.tags.contains(f'"{token}"')
                        )
                        and_conditions.append(token_condition)
                        or_conditions.append(token_condition)
                    
                    # 先查找完全匹配的记忆（所有词都包含）
                    exact_memories = base_query.filter(
                        and_(*and_conditions)
                    ).order_by(
                        desc(UserMemory.importance),
                        desc(UserMemory.updated_at)
                    ).limit(limit).all()
                    
                    # 如果完全匹配的结果不够，补充部分匹配的结果
                    if len(exact_memories) < limit:
                        existing_ids = [m.id for m in exact_memories]
                        partial_memories = base_query.filter(
                            or_(*or_conditions),
                            ~UserMemory.id.in_(existing_ids) if existing_ids else True
                        ).order_by(
                            desc(UserMemory.importance),
                            desc(UserMemory.updated_at)
                        ).limit(limit - len(exact_memories)).all()
                        
                        memories = exact_memories + partial_memories
                    else:
                        memories = exact_memories
                
                # 记录搜索日志
                logger.info(f"记忆搜索: '{query}' -> 分词{query_tokens} -> 找到{len(memories)}条记忆")
                
                return [memory.to_dict() for memory in memories]
                
        except Exception as e:
            logger.error(f"搜索用户记忆失败: {e}")
            # 降级为简单搜索
            return await self._simple_search_memories(app_id, user_id, query, limit)
    
    async def _simple_search_memories(
        self, 
        app_id: str, 
        user_id: str, 
        query: str, 
        limit: int
    ) -> List[Dict[str, Any]]:
        """简单关键词搜索（降级方案）"""
        try:
            with self.SessionLocal() as db:
                memories = db.query(UserMemory).filter(
                    UserMemory.app_id == app_id,
                    UserMemory.user_id == user_id,
                    UserMemory.is_active == True,
                    func.concat(UserMemory.content, ' ', UserMemory.context).contains(query)
                ).order_by(
                    desc(UserMemory.importance),
                    desc(UserMemory.updated_at)
                ).limit(limit).all()
                
                return [memory.to_dict() for memory in memories]
        except Exception as e:
            logger.error(f"简单搜索失败: {e}")
            return []
    
    def format_user_context(
        self, 
        profile: Optional[Dict[str, Any]], 
        memories: List[Dict[str, Any]]
    ) -> str:
        """格式化用户上下文"""
        context_parts = []
        
        if profile:
            context_parts.append("## 用户画像")
            profile_info = []
            
            # 基本信息
            if profile.get("user_name"):
                profile_info.append(f"姓名：{profile['user_name']}")
            if profile.get("nickname") and profile.get("nickname") != profile.get("user_name"):
                profile_info.append(f"昵称：{profile['nickname']}")
            if profile.get("age"):
                profile_info.append(f"年龄：{profile['age']}岁")
            if profile.get("occupation"):
                profile_info.append(f"职业：{profile['occupation']}")
            if profile.get("home"):
                profile_info.append(f"居住地：{profile['home']}")
            
            # 兴趣和特征
            if profile.get("interests"):
                interests_list = profile['interests']
                if isinstance(interests_list, list) and interests_list:
                    profile_info.append(f"兴趣：{', '.join(interests_list)}")
            if profile.get("personality_traits"):
                traits_list = profile['personality_traits']
                if isinstance(traits_list, list) and traits_list:
                    profile_info.append(f"性格特征：{', '.join(traits_list)}")
            
            # 沟通和偏好
            if profile.get("communication_style"):
                profile_info.append(f"沟通风格：{profile['communication_style']}")
            if profile.get("conversation_preferences"):
                prefs_list = profile['conversation_preferences']
                if isinstance(prefs_list, list) and prefs_list:
                    profile_info.append(f"对话偏好：{', '.join(prefs_list)}")
            if profile.get("language_preference"):
                profile_info.append(f"语言偏好：{profile['language_preference']}")
            
            # 工作和环境
            if profile.get("work_context"):
                profile_info.append(f"工作背景：{profile['work_context']}")
            if profile.get("timezone"):
                profile_info.append(f"时区：{profile['timezone']}")
                
            if profile_info:
                context_parts.append("\n".join(profile_info))
        
        if memories:
            context_parts.append("## 重要记忆")
            memory_info = []
            
            for memory in memories:
                memory_type_name = UserMemoryConfig.MEMORY_TYPES.get(
                    memory['memory_type'], memory['memory_type']
                )
                memory_info.append(
                    f"[{memory_type_name}] {memory['content']} "
                    f"(上下文：{memory['context'][:50]}...)"
                )
            
            if memory_info:
                context_parts.append("\n".join(memory_info))
        
        return "\n\n".join(context_parts) if context_parts else ""
    
    async def schedule_memory_extraction(
        self, 
        app_id: str,
        user_id: str, 
        messages: List[Dict[str, Any]],
        chat_id: Optional[str] = None,
        chat_type: Optional[str] = None,
        nickname: Optional[str] = None
    ):
        """调度记忆提取任务（带延迟）"""
        # 使用app_id和user_id组合作为key
        extraction_key = f"{app_id}:{user_id}"
        
        # 取消之前的任务
        if extraction_key in self._pending_extractions:
            self._pending_extractions[extraction_key].cancel()
        
        # 创建新的延迟任务
        task = asyncio.create_task(
            self._delayed_memory_extraction(app_id, user_id, messages, chat_id, chat_type, nickname)
        )
        self._pending_extractions[extraction_key] = task
        
        logger.info(f"已调度用户 {user_id}@{app_id} 的记忆提取任务，{self.memory_extraction_delay}秒后执行")
    
    async def _delayed_memory_extraction(
        self, 
        app_id: str,
        user_id: str, 
        messages: List[Dict[str, Any]],
        chat_id: Optional[str] = None,
        chat_type: Optional[str] = None,
        nickname: Optional[str] = None
    ):
        """延迟执行记忆提取"""
        extraction_key = f"{app_id}:{user_id}"
        try:
            await asyncio.sleep(self.memory_extraction_delay)
            await self.extract_memories(app_id, user_id, messages, chat_id, chat_type, nickname)
        except asyncio.CancelledError:
            logger.info(f"用户 {user_id}@{app_id} 的记忆提取任务被取消")
        except Exception as e:
            logger.error(f"延迟记忆提取失败: {e}")
        finally:
            # 清理完成的任务
            if extraction_key in self._pending_extractions:
                del self._pending_extractions[extraction_key]
    
    async def extract_memories(
        self, 
        app_id: str,
        user_id: str, 
        messages: List[Dict[str, Any]],
        chat_id: Optional[str] = None,
        chat_type: Optional[str] = None,
        nickname: Optional[str] = None
    ):
        """从对话中提取记忆"""
        try:
            # 准备对话内容
            conversation_text = self._format_conversation(messages)
            
            # 获取现有用户画像
            current_profile = await self.get_user_profile(app_id, user_id)
            
            # 提取用户画像
            await self._extract_user_profile(app_id, user_id, conversation_text, current_profile, nickname)
            
            # 提取记忆条目
            await self._extract_memory_entries(app_id, user_id, conversation_text, chat_id, chat_type)
            
            logger.info(f"用户 {user_id}@{app_id} 的记忆提取完成")
            
        except Exception as e:
            logger.error(f"记忆提取失败: {e}")
    
    def _format_conversation(self, messages: List[Dict[str, Any]]) -> str:
        """格式化对话内容"""
        formatted_messages = []
        for msg in messages[-10:]:  # 只取最近10条消息
            role = "用户" if msg.get("role") == "user" else "助手"
            content = msg.get("content", "").strip()
            if content:
                formatted_messages.append(f"{role}: {content}")
        
        return "\n".join(formatted_messages)
    
    async def _extract_user_profile(
        self, 
        app_id: str,
        user_id: str, 
        conversation_text: str, 
        current_profile: Optional[Dict[str, Any]],
        nickname: Optional[str] = None
    ):
        """提取并更新用户画像"""
        try:
            # 构建提示
            system_prompt = """你是一个专业的用户画像分析师。根据对话内容，提取和更新用户的个人信息。

请分析对话内容，提取用户的以下信息：
- 姓名或昵称
- 年龄（如果提到）
- 兴趣爱好
- 居住地
- 职业
- 对话偏好和沟通风格
- 性格特征
- 工作环境和背景
- 时区和语言偏好

只提取明确提到的信息，不要推测。如果信息不足，保持相应字段为空。

IMPORTANT: 必须严格按照JSON格式返回，不要包含任何解释文字，只返回纯JSON：
{
    "user_name": "用户姓名或null",
    "age": 年龄数字或null,
    "interests": ["兴趣1", "兴趣2"]或[],
    "home": "居住地描述或null",
    "occupation": "职业或null",
    "conversation_preferences": ["偏好1", "偏好2"]或[],
    "personality_traits": ["特征1", "特征2"]或[],
    "work_context": "工作背景描述或null",
    "communication_style": "沟通风格或null",
    "timezone": "时区或null",
    "language_preference": "语言偏好或null"
}"""

            user_prompt = f"""当前用户画像：
{json.dumps(current_profile, ensure_ascii=False, indent=2) if current_profile else "暂无用户画像"}

最新对话内容：
{conversation_text}

请分析并更新用户画像："""

            # 调用通用LLM
            response = await self.call_general_llm(system_prompt, user_prompt)
            
            if not response:
                logger.warning("通用LLM未可用，跳过用户画像提取")
                return
            
            # 解析响应
            profile_data = self._parse_json_response(response)
            if profile_data:
                await self._update_user_profile(app_id, user_id, profile_data, current_profile, nickname)
                
        except Exception as e:
            logger.error(f"提取用户画像失败: {e}")
    
    async def _extract_memory_entries(
        self, 
        app_id: str,
        user_id: str, 
        conversation_text: str, 
        chat_id: Optional[str] = None,
        chat_type: Optional[str] = None
    ):
        """提取记忆条目"""
        try:
            memory_types_desc = "\n".join([
                f"- {k}: {v}" for k, v in UserMemoryConfig.MEMORY_TYPES.items()
            ])
            
            system_prompt = f"""你是一个专业的记忆管理助手。从对话中识别值得记住的信息，并创建结构化的记忆条目。

记忆类型包括：
{memory_types_desc}

对于每个值得记住的信息，请创建一个记忆条目，包含：
- memory_type: 记忆类型（从上述类型中选择）
- context: 记忆的上下文和适用情况
- content: 具体的记忆内容
- importance: 重要性评分（1-10分）
- tags: 相关标签列表

IMPORTANT: 必须严格按照JSON数组格式返回，不要包含任何解释文字，只返回纯JSON：
[
    {{
        "memory_type": "preference",
        "context": "在讨论工作安排时",
        "content": "用户喜欢在上午处理重要任务",
        "importance": 7,
        "tags": ["工作", "时间管理"]
    }}
]

如果没有值得记住的信息，返回空数组 []。"""

            user_prompt = f"""请分析以下对话内容，提取值得记住的信息：

{conversation_text}"""

            # 调用通用LLM
            response = await self.call_general_llm(system_prompt, user_prompt)
            
            if not response:
                logger.warning("通用LLM未可用，跳过记忆条目提取")
                return
            
            # 解析响应
            memories_data = self._parse_json_response(response)
            if memories_data and isinstance(memories_data, list):
                await self._save_memory_entries(app_id, user_id, memories_data, chat_id, chat_type)
                
        except Exception as e:
            logger.error(f"提取记忆条目失败: {e}")
    
    def _parse_json_response(self, response: str) -> Optional[Any]:
        """解析JSON响应"""
        try:
            response = response.strip()
            
            # 方法1: 提取JSON代码块
            if "```json" in response:
                json_part = response.split("```json")[1].split("```")[0].strip()
                return json.loads(json_part)
            elif "```" in response:
                json_part = response.split("```")[1].strip()
                return json.loads(json_part)
            
            # 方法2: 尝试直接解析
            try:
                return json.loads(response)
            except:
                pass
            
            # 方法3: 查找JSON对象或数组
            import re
            
            # 查找对象格式 {...}
            obj_match = re.search(r'\{.*\}', response, re.DOTALL)
            if obj_match:
                try:
                    return json.loads(obj_match.group())
                except:
                    pass
            
            # 查找数组格式 [...]
            arr_match = re.search(r'\[.*\]', response, re.DOTALL)
            if arr_match:
                try:
                    return json.loads(arr_match.group())
                except:
                    pass
            
            # 方法4: 如果是自然语言回复，尝试转换
            if "用户" in response and ("姓名" in response or "职业" in response):
                # 这是用户画像的自然语言回复，尝试解析
                return self._parse_natural_language_profile(response)
            
            logger.warning(f"无法解析JSON响应，将跳过: {response[:200]}...")
            return None
            
        except Exception as e:
            logger.error(f"解析JSON响应失败: {e}, 响应内容: {response[:200]}...")
            return None
    
    def _parse_natural_language_profile(self, response: str) -> Optional[Dict[str, Any]]:
        """解析自然语言的用户画像"""
        try:
            profile = {}
            
            # 提取用户名
            import re
            name_match = re.search(r'用户名：(.+?)[\n，。]', response)
            if name_match:
                profile['user_name'] = name_match.group(1).strip()
            
            # 提取职业
            job_match = re.search(r'职业：(.+?)[\n，。]', response)
            if job_match:
                profile['occupation'] = job_match.group(1).strip()
            
            # 提取兴趣爱好
            interests_match = re.search(r'兴趣爱好：(.+?)[\n，。]', response)
            if interests_match:
                interests_text = interests_match.group(1).strip()
                profile['interests'] = [i.strip() for i in interests_text.split('、') if i.strip()]
            
            # 提取需求特点/沟通风格
            style_match = re.search(r'需求特点：(.+?)[\n，。]', response)
            if style_match:
                profile['communication_style'] = style_match.group(1).strip()
            
            return profile if profile else None
            
        except Exception as e:
            logger.error(f"解析自然语言用户画像失败: {e}")
            return None
    
    async def _update_user_profile(
        self, 
        app_id: str,
        user_id: str, 
        profile_data: Dict[str, Any],
        current_profile: Optional[Dict[str, Any]],
        nickname: Optional[str] = None
    ):
        """更新用户画像"""
        try:
            if not self.SessionLocal:
                return
                
            with self.SessionLocal() as db:
                profile = db.query(UserProfile).filter(
                    UserProfile.app_id == app_id,
                    UserProfile.user_id == user_id
                ).first()
                
                if not profile:
                    # 创建新的用户画像
                    profile = UserProfile(
                        app_id=app_id,
                        user_id=user_id,
                        nickname=nickname
                    )
                    db.add(profile)
                else:
                    # 更新昵称（如果有新值）
                    if nickname and profile.nickname != nickname:
                        profile.nickname = nickname
                
                # 更新字段（只更新非空值）
                for key, value in profile_data.items():
                    if value is not None and hasattr(profile, key):
                        if isinstance(value, list) and len(value) == 0:
                            continue  # 跳过空列表
                        if isinstance(value, str) and len(value.strip()) == 0:
                            continue  # 跳过空字符串
                        setattr(profile, key, value)
                
                db.commit()
                logger.info(f"用户 {user_id}@{app_id} 的画像已更新")
                
        except Exception as e:
            logger.error(f"更新用户画像失败: {e}")
    
    async def _save_memory_entries(
        self, 
        app_id: str,
        user_id: str, 
        memories_data: List[Dict[str, Any]],
        chat_id: Optional[str] = None,
        chat_type: Optional[str] = None
    ):
        """保存记忆条目"""
        try:
            if not self.SessionLocal:
                return
                
            with self.SessionLocal() as db:
                for memory_data in memories_data:
                    # 验证必需字段
                    if not all(k in memory_data for k in ["memory_type", "context", "content"]):
                        continue
                    
                    # 检查是否已存在相似记忆
                    existing = db.query(UserMemory).filter(
                        UserMemory.app_id == app_id,
                        UserMemory.user_id == user_id,
                        UserMemory.memory_type == memory_data["memory_type"],
                        UserMemory.content == memory_data["content"],
                        UserMemory.is_active == True
                    ).first()
                    
                    if existing:
                        # 更新现有记忆
                        existing.context = memory_data["context"]
                        existing.importance = memory_data.get("importance", 5)
                        existing.tags = memory_data.get("tags", [])
                        existing.updated_at = func.now()
                        if chat_type:
                            existing.chat_type = chat_type
                    else:
                        # 创建新记忆
                        memory = UserMemory(
                            app_id=app_id,
                            user_id=user_id,
                            memory_type=memory_data["memory_type"],
                            context=memory_data["context"],
                            content=memory_data["content"],
                            importance=memory_data.get("importance", 5),
                            tags=memory_data.get("tags", []),
                            source_chat_id=chat_id,
                            chat_type=chat_type
                        )
                        db.add(memory)
                
                db.commit()
                logger.info(f"用户 {user_id}@{app_id} 的记忆条目已保存，共 {len(memories_data)} 条")
                
        except Exception as e:
            logger.error(f"保存记忆条目失败: {e}")
    
    async def get_memory_stats(self, app_id: str, user_id: str) -> Dict[str, Any]:
        """获取记忆统计信息"""
        try:
            if not self.SessionLocal:
                return {
                    "app_id": app_id,
                    "user_id": user_id,
                    "error": "数据库连接不可用"
                }
                
            with self.SessionLocal() as db:
                # 用户画像信息
                profile = db.query(UserProfile).filter(
                    UserProfile.app_id == app_id,
                    UserProfile.user_id == user_id,
                    UserProfile.is_active == True
                ).first()
                
                # 记忆统计
                total_memories = db.query(UserMemory).filter(
                    UserMemory.app_id == app_id,
                    UserMemory.user_id == user_id,
                    UserMemory.is_active == True
                ).count()
                
                # 按类型统计
                type_stats = db.query(
                    UserMemory.memory_type,
                    func.count(UserMemory.id).label('count')
                ).filter(
                    UserMemory.app_id == app_id,
                    UserMemory.user_id == user_id,
                    UserMemory.is_active == True
                ).group_by(UserMemory.memory_type).all()
                
                # 按聊天类型统计
                chat_type_stats = db.query(
                    UserMemory.chat_type,
                    func.count(UserMemory.id).label('count')
                ).filter(
                    UserMemory.app_id == app_id,
                    UserMemory.user_id == user_id,
                    UserMemory.is_active == True
                ).group_by(UserMemory.chat_type).all()
                
                return {
                    "app_id": app_id,
                    "user_id": user_id,
                    "has_profile": profile is not None,
                    "nickname": profile.nickname if profile else None,
                    "profile_updated_at": profile.updated_at.isoformat() if profile else None,
                    "total_memories": total_memories,
                    "memory_types": {
                        row.memory_type: row.count for row in type_stats
                    },
                    "chat_types": {
                        row.chat_type: row.count for row in chat_type_stats if row.chat_type
                    }
                }
                
        except Exception as e:
            logger.error(f"获取记忆统计失败: {e}")
            return {"app_id": app_id, "user_id": user_id, "error": str(e)}
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()
        
    def __del__(self):
        """析构函数，确保客户端会话被关闭"""
        if hasattr(self, '_client') and self._client and not self._client.closed:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.close())
                else:
                    loop.run_until_complete(self.close())
            except Exception as e:
                logger.error(f"关闭客户端会话异常: {str(e)}")