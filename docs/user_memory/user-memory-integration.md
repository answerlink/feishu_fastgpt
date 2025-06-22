# 用户记忆功能集成文档

## 概述

基于 LangGraph Memory Service 开源项目的设计理念，我们为飞书机器人集成了强大的用户记忆功能。该功能能够自动从用户对话中学习并构建用户画像，提供个性化的AI回复体验。

## 核心特性

### 1. 双模式记忆系统

- **Patch模式 - 用户画像**：维护单一的、持续更新的用户画像文档
- **Insert模式 - 记忆条目**：插入独立的记忆条目和事件

### 2. 自动用户画像构建

自动从对话中提取和更新：
- 用户姓名/昵称
- 年龄信息
- 兴趣爱好
- 居住地
- 职业信息
- 对话偏好
- 性格特征
- 工作背景
- 时区和语言偏好

### 3. 智能记忆分类

支持10种记忆类型：
- **preference**: 偏好
- **experience**: 经历
- **skill**: 技能
- **relationship**: 关系
- **goal**: 目标
- **concern**: 关注点
- **habit**: 习惯
- **achievement**: 成就
- **project**: 项目
- **tool**: 工具使用

### 4. Debouncing机制

- 对话结束后延迟30秒处理记忆
- 避免过频繁的AI调用
- 节省成本，提高效率
- 如果用户继续对话，会取消之前的任务并重新调度

### 5. 智能上下文增强

- 根据用户问题搜索相关记忆
- 自动格式化为AI可理解的上下文
- 增强对话的个性化和连续性

## 数据库结构

### 用户画像表 (user_profiles)

```sql
CREATE TABLE user_profiles (
    id INTEGER PRIMARY KEY,
    user_id VARCHAR(255) UNIQUE NOT NULL,
    user_name VARCHAR(255),
    age INTEGER,
    interests JSON,
    home VARCHAR(500),
    occupation VARCHAR(255),
    conversation_preferences JSON,
    personality_traits JSON,
    work_context TEXT,
    communication_style VARCHAR(255),
    timezone VARCHAR(50),
    language_preference VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);
```

### 用户记忆表 (user_memories)

```sql
CREATE TABLE user_memories (
    id INTEGER PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    memory_type VARCHAR(100) NOT NULL,
    context TEXT NOT NULL,
    content TEXT NOT NULL,
    importance INTEGER DEFAULT 5,
    tags JSON,
    source_chat_id VARCHAR(255),
    source_message_id VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);
```

## API接口

### 用户画像管理

- `GET /api/v1/user-memory/profile/{user_id}` - 获取用户画像
- `DELETE /api/v1/user-memory/profile/{user_id}` - 删除用户画像

### 用户记忆管理

- `GET /api/v1/user-memory/memories/{user_id}` - 获取用户记忆
- `POST /api/v1/user-memory/search` - 搜索用户记忆
- `DELETE /api/v1/user-memory/memories/{user_id}` - 删除用户记忆

### 上下文和提取

- `POST /api/v1/user-memory/context` - 获取用户上下文（画像+记忆）
- `POST /api/v1/user-memory/extract` - 手动提取记忆

### 统计和配置

- `GET /api/v1/user-memory/stats/{user_id}` - 获取记忆统计
- `GET /api/v1/user-memory/config/memory-types` - 获取记忆类型配置

## 配置选项

在飞书应用配置中添加以下选项：

```json
{
    "user_memory_enable": true
}
```

- `user_memory_enable`: 是否启用用户记忆功能（默认: true）

## 部署步骤

### 1. 创建数据库表

```bash
python create_user_memory_tables.py
```

### 2. 重启应用

重启飞书机器人服务以加载新功能。

### 3. 验证功能

使用以下API检查功能是否正常：

```bash
# 检查记忆类型配置
curl http://localhost:8000/api/v1/user-memory/config/memory-types

# 获取用户画像（测试用户）
curl http://localhost:8000/api/v1/user-memory/profile/test_user
```

## 工作流程

### 1. 用户发送消息

用户向飞书机器人发送消息。

### 2. 加载记忆上下文

系统自动：
- 加载用户画像
- 搜索相关记忆
- 格式化为AI上下文

### 3. AI生成回复

AI服务使用用户记忆上下文生成个性化回复。

### 4. 调度记忆提取

对话完成后，系统自动调度记忆提取任务。

### 5. 记忆提取和更新

30秒后（如果没有新消息）：
- 分析对话内容
- 更新用户画像
- 创建新的记忆条目

## 示例用法

### 用户上下文示例

```
## 用户画像
姓名：张三
职业：软件工程师
兴趣：编程, 机器学习, 阅读
居住地：北京
沟通风格：简洁明了
对话偏好：技术讨论, 直接问答

## 重要记忆
[偏好] 喜欢使用Python进行开发 (上下文：讨论编程语言时...)
[技能] 熟悉FastAPI框架 (上下文：构建API项目时...)
[目标] 想要学习大语言模型应用开发 (上下文：职业规划讨论...)
```

### API调用示例

```python
# 获取用户上下文
import requests

response = requests.post("http://localhost:8000/api/v1/user-memory/context", json={
    "user_id": "user123",
    "query": "Python开发",
    "importance_threshold": 3
})

result = response.json()
print(result["context"])
```

## 注意事项

1. **隐私保护**：用户记忆包含敏感信息，确保数据安全
2. **性能优化**：大量用户时考虑记忆存储的清理策略
3. **准确性**：AI提取的记忆可能不完全准确，需要验证机制
4. **存储成本**：长期使用会积累大量记忆数据

## 故障排查

### 记忆功能不工作

1. 检查配置：确认 `user_memory_enable` 为 true
2. 检查数据库：确认表已创建且可访问
3. 检查日志：查看记忆提取相关的错误信息

### AI不使用记忆上下文

1. 检查AI服务配置：确认支持 `user_memory_context` 变量
2. 检查提示词：确认AI提示词中包含记忆处理逻辑

### 记忆提取延迟

1. 正常现象：系统设计为30秒延迟
2. 检查异步任务：确认记忆提取任务正常调度

## 扩展功能

### 向量搜索

未来可以集成向量数据库实现语义搜索：

```python
# 示例：使用向量搜索找到相关记忆
async def search_memories_by_embedding(self, user_id: str, query_embedding: List[float]):
    # 实现向量相似度搜索
    pass
```

### 记忆重要性评分

可以根据用户互动频率调整记忆重要性：

```python
# 示例：动态调整记忆重要性
async def update_memory_importance(self, memory_id: int, interaction_count: int):
    # 根据交互次数调整重要性评分
    pass
```

### 记忆过期清理

定期清理过期的低重要性记忆：

```python
# 示例：清理过期记忆
async def cleanup_expired_memories(self, days_threshold: int = 90):
    # 清理指定天数前的低重要性记忆
    pass
```

## 总结

用户记忆功能为飞书机器人提供了强大的个性化能力，通过自动学习用户偏好和行为模式，显著提升了用户体验。该功能设计灵活，支持扩展，为未来的智能化功能提供了坚实基础。 