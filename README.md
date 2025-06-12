# Feishu Plus

一个强大的飞书开放平台API集成工具，提供飞书云文档和知识库的完整管理功能。

## 飞书应用权限配置

申请飞书内建应用地址：https://open.feishu.cn/app

本项目需要创建飞书内建应用并申请以下权限：

### 必需权限
- **文档权限**：
  - `docs:*` - 所有文档相关权限，包括读取、写入
  - `docx:*` - 所有云文档相关权限，包括读取、写入

- **知识库权限**：
  - `wiki:*` - 所有知识库相关权限，包括读取、写入
  - `space:*` - 所有空间相关权限，包括读取、空间管理

### 回调配置
本项目使用长连接方式处理回调，无需配置Webhook地址。在飞书开发者平台中：

1. 进入应用 -> 事件订阅
2. 订阅方式选择"使用长连接接收回调"
3. 添加需要订阅的事件，例如：
   - 卡片回传交互 (card.action.trigger)
   - 链接预览获取 (url.preview.get)

> 注意：该订阅方式只适用于企业自建应用，且每个应用最多建立50个连接。

### 权限申请步骤
1. 登录[飞书开放平台](https://open.feishu.cn/)
2. 创建企业自建应用
3. 进入应用凭证页面，获取App ID和App Secret
4. 进入权限管理页面，搜索并添加上述权限
5. 提交审核，等待管理员审批

### 权限说明
| 权限范围 | 说明 | 用途 |
|---------|------|------|
| `docs:read` | 读取文档内容 | 获取文档内容、元数据 |
| `docs:write` | 写入文档内容 | 更新、创建文档 |
| `wiki:read` | 读取知识库内容 | 获取知识空间列表、节点列表 |
| `wiki:write` | 写入知识库内容 | 更新、创建知识空间内容 |
| `space:read` | 读取空间信息 | 获取空间列表、成员信息 |
| `space:write` | 管理空间 | 创建空间、管理空间成员 |

## 项目架构

```
feishu-plus/
├── app/                    # 主应用目录
│   ├── api/               # API路由层
│   │   ├── v1/           # API版本1
│   │   └── deps.py       # 依赖注入
│   ├── core/             # 核心配置
│   │   ├── config.py     # 配置管理
│   │   └── security.py   # 安全相关
│   ├── db/               # 数据库相关
│   │   ├── base.py      # 数据库基类
│   │   └── session.py   # 数据库会话
│   ├── models/          # 数据模型
│   │   ├── document.py  # 文档模型
│   │   └── wiki.py      # 知识库模型
│   ├── schemas/         # Pydantic模型
│   │   ├── document.py  # 文档模式
│   │   └── wiki.py      # 知识库模式
│   ├── services/        # 业务逻辑层
│   │   ├── document.py  # 文档服务
│   │   └── wiki.py      # 知识库服务
│   └── utils/           # 工具函数
│       ├── feishu.py    # 飞书API工具
│       └── common.py    # 通用工具
├── web/                 # 前端管理界面（可选）
├── logs/               # 日志目录
├── .env               # 环境变量
├── .gitignore        # Git忽略文件
├── requirements.txt   # 项目依赖
└── main.py           # 应用入口
```

## 主要功能模块

### 1. 文档管理模块 (Document Management)
- 文档的创建、读取、更新、删除
- 文档权限管理
- 文档版本控制
- 文档内容同步

### 2. 知识库管理模块 (Wiki Management)
- 知识库的创建和管理
- 知识库内容同步
- 知识库权限控制
- 知识库结构管理

### 3. 事件回调模块 (Event Callback)
- 飞书事件订阅和长连接处理
- 卡片回传交互(card.action.trigger)处理
- 链接预览(url.preview.get)处理
- 回调状态管理API

### 4. 定时任务模块 (Scheduled Tasks)
- 文档定期同步
- 知识库定期更新
- 数据备份

### 5. 认证授权模块 (Authentication)
- 飞书应用认证
- 用户权限管理
- Token管理

## 技术栈

### 后端
- FastAPI: Web框架
- SQLAlchemy: ORM
- Pydantic: 数据验证
- APScheduler: 定时任务

### 前端（可选，用于管理员监控）
- Vue 3: 前端框架
- Element Plus: UI组件库
- Vue Router: 路由管理
- Axios: HTTP客户端

## 开发规范

1. 代码风格遵循PEP 8
2. 使用类型注解
3. 使用异步编程
4. 完善的日志记录
5. 错误处理机制

## 部署要求

- Python 3.8+
- MySQL 8.0+
- 飞书开发者账号
- 飞书应用凭证

## 快速开始

1. 克隆项目
```bash
git clone https://github.com/your-username/feishu-plus.git
cd feishu-plus
```

2. 安装依赖
```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

3. 配置数据库
```sql
CREATE DATABASE feishu_plus;
```

4. 创建配置文件
```bash
cp config/config.example.json config/config.json
# 编辑 config.json，填入您的配置信息
```

5. 启动服务
```bash
uvicorn main:app --reload
```

## 前端管理界面（可选）

项目提供了一个可选的管理界面，用于管理员监控和测试。这个界面不是必需的，但可以帮助管理员更直观地：
- 查看已配置的应用
- 测试应用的Token状态
- 监控系统运行状况

### 启动前端（可选）

1. 安装前端依赖
```bash
cd web
npm install
```

2. 启动开发服务器
```bash
npm run dev
```

3. 访问管理界面
```
http://localhost:5173
```

## API文档

启动服务后，访问以下地址查看API文档：
```
http://localhost:8000/docs
```

### 回调管理API

回调相关的API包括：

- `GET /api/v1/callback/status` - 获取所有回调服务状态
- `POST /api/v1/callback/start` - 启动指定应用的回调服务
- `POST /api/v1/callback/stop` - 停止指定应用的回调服务
- `POST /api/v1/callback/start-all` - 启动所有应用的回调服务
- `POST /api/v1/callback/stop-all` - 停止所有应用的回调服务

## 日志

系统日志位于 `logs` 目录：
- `feishu-plus.log`: 主应用日志
- `feishu_service.log`: 飞书API服务日志
- `feishu_callback.log`: 飞书回调服务日志

## 许可证

[MIT License](LICENSE) 

## 支持的操作

- **订阅文档变更**: 监听指定文档的变更事件
- **获取文档内容**: 获取云文档(docx)、多维表格(sheet)等内容
- **智能聊天**: 与机器人对话，支持文档问答
- **知识库同步**: 自动同步文档到FastGPT知识库
- **图片处理**: 支持文档中的图片提取和描述

## 知识库描述自动生成

### 功能说明

项目新增了知识库描述自动生成功能，在每次更新FastGPT的dataset时，会自动：

1. 获取dataset中的所有collection（文件列表）
2. 根据文件名称调用LLM生成描述
3. 将生成的描述更新到dataset中

### 配置参数

在应用配置中新增了4个LLM相关配置参数：

```json
{
    "summary_llm_api_url": "https://api.siliconflow.cn/v1/chat/completions",
    "summary_llm_api_key": "sk-xxxxx",
    "summary_llm_model": "Qwen/Qwen3-32B",
    "summary_llm_model_prompt": "请给这个文件夹添加一段简洁易懂的描述，让用户可以快速了解这个文件夹的内容。"
}
```

### 触发时机

- **自动触发**: 每次文档同步到FastGPT后自动执行
- **手动触发**: 可通过API接口手动生成描述

### 手动生成API

```bash
POST /api/v1/document/generate-dataset-description?app_id={app_id}&dataset_id={dataset_id}
```

### 注意事项

- 只有设置了`dataset_sync: true`的应用会启用此功能
- 需要配置完整的4个LLM参数才会生效
- 功能异常不会影响文档同步的主流程
