# 飞书机器人配置指南

本文档详细介绍如何配置飞书机器人，包括创建应用、权限配置、事件回调设置以及项目配置文件的修改。

## 目录
- [创建飞书机器人应用](#创建飞书机器人应用)
- [权限配置](#权限配置)
- [开启事件回调](#开启事件回调)
- [版本发布](#版本发布)
- [配置文件修改](#配置文件修改)
- [常见问题](#常见问题)

## 创建飞书机器人应用

### 1. 进入飞书开放平台
访问 [飞书开放平台](https://open.feishu.cn/) 并登录您的飞书账号。

### 2. 创建应用
1. 进入开发者后台
2. 选择「企业自建应用」
3. 点击「创建应用」
4. 填写应用名称和描述
5. 创建完成后进入应用详情页

### 3. 添加机器人能力
1. 在左侧面板中找到「应用能力」
2. 点击「添加应用能力」
3. 选择「机器人」并确认添加

### 4. 配置机器人自定义菜单
1. 在左侧面板中找到「机器人」-「机器人自定义菜单」
2. 点击「开启」
3. 展示形式选择「悬浮菜单」
4. 配置以下菜单项：

#### 搜索模式切换功能

**主菜单**：🔍 搜索模式
> 注：先配置子菜单，后配置主菜单

**子菜单配置**：
- **子菜单1**
  - 名称：📚 知识库
  - 推送事件：`bot_search_dataset`
  
- **子菜单2**
  - 名称：🌐 联网检索
  - 推送事件：`bot_search_web`
  
- **子菜单3**
  - 名称：♾️ 知识库+联网
  - 推送事件：`bot_search_all`

#### 模型选择功能

**主菜单**：🤖 模型选择
> 注：先配置子菜单，后配置主菜单

**子菜单配置示例**：
- **子菜单1**
  - 名称：GPT-4
  - 推送事件：`bot_select_model_GPT-4#gpt-4`
  
- **子菜单2**
  - 名称：Claude-3
  - 推送事件：`bot_select_model_Claude-3#claude-3`
  
- **子菜单3**
  - 名称：DeepSeek-V3
  - 推送事件：`bot_select_model_DeepSeek-V3#deepseek-v3-250324`

> 💡 **模型选择说明**：
> - 推送事件格式：`bot_select_model_[模型显示名称]#[模型ID]`
> - 使用 `#` 作为分隔符，前半部分是显示名称，后半部分是模型ID
> - 模型显示名称：用于在确认消息中展示给用户，如：`GPT-4`、`DeepSeek-V3`
> - 模型ID：用于存储到数据库和调用AI接口，如：`gpt-4`、`deepseek-v3-250324`
> - 用户选择模型后，模型ID会在调用AI接口时通过 `variables.model_id` 传递
> - 模型偏好会保存到数据库，用户在该应用的所有会话中都会使用选择的模型
> - 如果事件中没有 `#` 分隔符，则整个字符串既作为显示名称也作为模型ID

#### 新会话功能

**主菜单**：🔄 新会话
- 推送事件：`bot_new_chat`

> ⚠️ **注意**：这些功能需要先开启卡片回传交互权限才能正常使用。

## 权限配置

在左侧面板中找到「开发配置」-「权限管理」，点击「开通权限」，选择「应用身份权限」，搜索并添加以下权限：

### 必需权限列表

```
im:message
im:message.p2p_msg:readonly
im:message.group_msg
im:chat
contact:contact.base:readonly
contact:user.employee_id:readonly
contact:user.base:readonly
contact:user.phone:readonly
contact:user.email:readonly
cardkit:card:write
```

### 权限说明

| 权限名称 | 说明 |
|---------|------|
| `im:message` | 发送消息到单聊和群聊必备权限 |
| `im:message.p2p_msg:readonly` | 获取单聊信息的只读权限 |
| `im:message.group_msg` | 获取群聊信息的权限 |
| `im:chat` | 获取与更新群组信息，用于读取群聊名称 |
| `contact:contact.base:readonly` | 读取飞书用户基础信息，用于识别发言人 |
| `contact:user.employee_id:readonly` | 读取飞书用户员工ID，用于识别发言人 |
| `contact:user.base:readonly` | 读取飞书用户基础信息 |
| `contact:user.phone:readonly` | 读取飞书用户手机号信息 |
| `contact:user.email:readonly` | 读取飞书用户邮箱信息 |
| `cardkit:card:write` | 创建和发送消息卡片的权限 |

> ⚠️ **注意**：权限配置后需要重新发布应用版本才能生效。

## 开启事件回调

### 1. 配置事件订阅方式
1. 在左侧面板中找到「开发配置」-「事件与回调」
2. 点击「事件配置」/「回调配置」
3. 选择「使用长连接接收事件」
4. 点击「保存」

### 2. 添加订阅事件
1. 点击「添加事件」
2. 选择「应用身份订阅」
3. 搜索并添加以下事件/回调：

#### 事件配置

**基础消息事件**
```
im.message.receive_v1
```

**机器人自定义菜单事件**
```
application.bot.menu_v6
```

#### 回调配置

**卡片回传交互**
```
card.action.trigger
```

### 事件说明

| 事件名称 | 说明 | 用途 |
|---------|------|------|
| `im.message.receive_v1` | 机器人可以接收到用户私聊和群聊消息 | 基础对话功能 |
| `application.bot.menu_v6` | 机器人自定义菜单事件 | 支持切换搜索模式、支持开启新会话 |
| `card.action.trigger` | 卡片回传交互事件 | 支持回答过程中停止回答 |

> 💡 **提示**：
> - 事件配置完成后需要重新发布应用才能生效
> - 如果事件不生效，请检查飞书应用是否需要发布
> - 卡片回传交互功能需要配置 `aichat_support_stop_streaming: true` 才会显示停止按钮

## 版本发布

### 发布步骤
1. 在左侧面板中找到「应用发布」-「版本管理与发布」
2. 填写版本信息：
   - 版本号
   - 更新说明
   - 可用范围（建议先选择部分用户测试）
3. 点击「保存」
4. 点击「发布」

### 发布注意事项
- 首次发布需要管理员审核
- 权限变更后需要重新发布
- 建议先发布到测试环境验证功能

## 配置文件修改

### 1. 复制配置文件
将 `config/config.example.json` 复制为 `config/config.json`：

```bash
cp config/config.example.json config/config.json
```

### 2. 配置文件详解

```json
{
    "APP_NAME": "feishu-plus",                    // 应用名称
    "DEBUG": true,                                // 调试模式开关
    "API_V1_STR": "/api/v1",                     // API版本前缀

    // 数据库配置
    "DB_HOST": "localhost",                       // 数据库主机地址
    "DB_PORT": 3306,                             // 数据库端口
    "DB_USER": "root",                           // 数据库用户名
    "DB_PASSWORD": "your_password",              // 数据库密码
    "DB_NAME": "feishu_plus",                    // 数据库名称
    "SQLALCHEMY_ECHO": false,                    // SQL调试输出开关
    "SQLALCHEMY_POOL_SIZE": 5,                   // 数据库连接池大小
    "SQLALCHEMY_POOL_TIMEOUT": 10,               // 连接池超时时间（秒）
    "SQLALCHEMY_POOL_RECYCLE": 3600,             // 连接池回收时间（秒）

    // 飞书应用配置列表
    "FEISHU_APPS": [
        {
            "dataset_sync": false,                           // 数据集同步开关
            "app_id": "cli_a0163xxx",               // 飞书应用ID
            "app_secret": "v11k8wGEOdxxx", // 飞书应用密钥
            "app_name": "测试应用1",                         // 应用显示名称
            "fastgpt_url": "http://127.0.0.1:3000",        // FastGPT服务地址
            "fastgpt_key": "fastgpt-aQ3Vr4M8Sxxx", // FastGPT API密钥
            "vector_model": "m3e-base",                      // 向量化模型
            "agent_model": "qwen3-8b",                    // 对话模型
            "vlm_model": "Qwen2.5-VL-7B-Instruct",         // 视觉语言模型
            "image_bed_base_url": "http://127.0.0.1:8000",  // 图床服务地址
            "image_bed_vlm_api_url": "https://xxx/v1/chat/completions", // 图像理解API地址
            "image_bed_vlm_api_key": "sk-blkqrxxx", // 图像理解API密钥
            "image_bed_vlm_model": "Qwen2.5-VL-7B-Instruct", // 图像理解模型
            "image_bed_vlm_model_prompt": "请用20字以内简洁描述这张图片内容，不要加任何前缀，直接给出描述，参考论文引用图例的格式。", // 图像描述提示词
            "aichat_enable": false,                          // AI聊天功能开关
            "aichat_url": "http://127.0.0.1:3000/api/v1/chat/completions", // AI聊天API地址
            "aichat_key": "fastgpt-ipUSgnlYvxxx", // AI聊天API密钥
            "aichat_support_stop_streaming": false,          // 是否支持停止流式回答（默认false）
            "aichat_client_download_host": "http://127.0.0.1:3000", // 客户端下载地址
            "aichat_read_collection_url": "https://xxx/api/core/dataset/collection/read", // 知识库读取API
            "aichat_read_collection_key": "fastgpt-pkBusvYZJxxx", // 知识库API密钥
            "aichat_reply_p2p": true,                        // 私聊自动回复开关
            "aichat_reply_group": false                      // 群聊自动回复开关
        }
    ]
}
```

### 3. 关键配置项说明

#### 飞书应用配置
- `app_id` 和 `app_secret`：从飞书开放平台应用详情页的「凭证与基础信息」中获取
- `app_name`：自定义的应用名称，用于日志和管理

#### FastGPT集成
- `fastgpt_url`：FastGPT服务的访问地址
- `fastgpt_key`：FastGPT的API密钥，用于调用AI服务

#### 聊天功能配置
- `aichat_reply_p2p`：控制是否在私聊中自动回复
- `aichat_reply_group`：控制是否在群聊中自动回复
- `aichat_enable`：总开关，控制AI聊天功能是否启用
- `aichat_support_stop_streaming`：控制是否支持停止流式回答功能，为`false`时卡片中不会显示"停止回答"按钮

## 常见问题

### Q1: 机器人无法接收消息
**解决方案**：
1. 检查事件订阅是否正确配置
2. 确认应用已发布且权限已生效
3. 检查长连接状态是否正常

### Q2: 权限不足错误
**解决方案**：
1. 确认所有必需权限都已添加
2. 重新发布应用版本
3. 等待权限生效（通常需要几分钟）

### Q3: 配置文件错误
**解决方案**：
1. 检查JSON格式是否正确
2. 确认所有必填字段都已配置
3. 验证API密钥和URL的有效性

### Q4: 数据库连接失败
**解决方案**：
1. 检查数据库服务是否启动
2. 验证数据库连接参数
3. 确认数据库用户权限

## 下一步

配置完成后，您可以：
1. 启动应用服务
2. 在飞书中@机器人进行测试
3. 查看日志确认功能正常
4. 根据需要调整配置参数

如需更多帮助，请参考 [FastGPT官方文档](https://doc.fastgpt.in/) 或 [飞书开放平台文档](https://open.feishu.cn/document/)。 