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

## 权限配置

在左侧面板中找到「开发配置」-「权限管理」，点击「开通权限」，选择「应用身份权限」，搜索并添加以下权限：

### 必需权限列表

```
im:message
im:message.p2p_msg:readonly
im:message.group_msg
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
2. 点击「事件配置」
3. 选择「使用长连接接收事件」
4. 点击「保存」

### 2. 添加订阅事件
1. 点击「添加事件」
2. 选择「应用身份订阅」
3. 搜索并添加以下事件：

```
im.message.receive_v1
```

### 事件说明

| 事件名称 | 说明 |
|---------|------|
| `im.message.receive_v1` | 机器人可以接收到用户私聊和群聊消息 |

> 💡 **提示**：如果需要接收其他类型的事件，可以根据业务需求添加相应的事件订阅。

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