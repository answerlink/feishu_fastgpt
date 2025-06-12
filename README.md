# Feishu FastGPT

<div align="center">

[![GitHub stars](https://img.shields.io/github/stars/answerlink/feishu_fastgpt?style=flat-square)](https://github.com/answerlink/feishu_fastgpt/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/answerlink/feishu_fastgpt?style=flat-square)](https://github.com/answerlink/feishu_fastgpt/network)
[![GitHub issues](https://img.shields.io/github/issues/answerlink/feishu_fastgpt?style=flat-square)](https://github.com/answerlink/feishu_fastgpt/issues)
[![GitHub license](https://img.shields.io/github/license/answerlink/feishu_fastgpt?style=flat-square)](https://github.com/answerlink/feishu_fastgpt/blob/main/LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.8+-blue?style=flat-square)](https://www.python.org/downloads/)

🚀 **基于飞书开放平台和FastGPT的企业级智能知识管理系统**

[功能特性](#-功能特性) • [快速开始](#-快速开始) • [配置文档](#-配置文档) • [部署指南](#-部署指南) • [贡献指南](#-贡献指南)

</div>

---

## 📋 项目简介

Feishu FastGPT 是一个企业级的智能知识管理系统，深度集成飞书开放平台和FastGPT，为企业提供智能化的知识管理和问答服务。

### 核心能力

- 🤖 **智能机器人问答**：在飞书中直接与AI助手对话，获得基于企业知识库的精准答案
- 📚 **知识库同步**：自动同步飞书云文档、多维表格等内容到FastGPT知识库
- 🖥️ **Web管理界面**：提供可视化的管理界面，支持配置管理、状态监控
- ⚡ **多进程架构**：支持多应用并发处理，高性能稳定运行
- 🔄 **实时同步**：支持文档变更的实时同步和批量导入

## ✨ 功能特性

### 🤖 飞书机器人问答
- **智能对话**：支持私聊和群聊中的AI问答
- **上下文理解**：维持对话上下文，提供连贯的交互体验
- **多媒体支持**：支持文本、图片等多种消息类型
- **权限控制**：精细化的用户和群组权限管理

### 📚 知识库管理
- **多格式支持**：飞书云文档(docx)、多维表格(sheet)、思维导图等
- **智能处理**：自动提取图片并生成描述，优化知识库内容
- **增量同步**：智能识别变更内容，支持增量更新
- **批量导入**：支持整个知识空间的批量同步

### 🖥️ Web管理界面
- **应用管理**：可视化管理多个飞书应用配置
- **状态监控**：实时监控系统运行状态和同步进度
- **日志查看**：集中查看系统日志和错误信息
- **用户友好**：基于Vue 3和Element Plus的现代化界面

### ⚡ 技术架构
- **FastAPI后端**：高性能异步Web框架
- **Vue 3前端**：现代化的前端用户界面
- **多进程支持**：支持多应用实例并发运行
- **数据库集成**：MySQL数据库存储配置和状态

## 🚀 快速开始

### 环境要求

- Python 3.8+
- MySQL 5.7/8.0+
- Node.js 16+
- 飞书开发者账号
- FastGPT服务实例

### 1. 克隆项目

```bash
git clone https://github.com/answerlink/feishu_fastgpt
cd feishu_fastgpt
```

### 2. 安装后端依赖

```bash
pip install -r requirements.txt
```

### 3. 数据库配置

```sql
CREATE DATABASE feishu_plus DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```
注：只须建库，表自动创建，支持 MySQL 5.7/8.0

### 4. 配置应用

```bash
# 复制配置文件
cp config/config.example.json config/config.json

# 编辑配置文件，填入您的配置信息
vim config/config.json
```

### 5. 构建前端

```bash
# 安装前端依赖并构建
cd web
npm install
npm run build
cd ..
```

### 6. 启动服务

```bash
# 启动主服务
python feishu_plus_app.py

# 或使用脚本启动多进程服务
./start.sh
```

### 7. 访问管理界面

启动服务后，打开浏览器访问：

- **Web管理界面**: http://localhost:8000
- **前端开发模式**: `cd web && npm run dev` (开发时使用 http://localhost:5173)

## 📖 配置文档

### 🤖 飞书机器人配置

详细的飞书机器人配置步骤请参考：[飞书机器人配置指南](docs/feishu-bot-setup.md)

- 创建飞书应用
- 权限配置
- 事件回调设置
- 版本发布

### 📚 知识库同步配置

详细的知识库同步配置请参考：[知识库同步指南](docs/knowledge-base-sync.md)

- 权限配置
- 同步策略
- 最佳实践

### ⚙️ 配置文件说明

```json
{
    "APP_NAME": "feishu-plus",                // 应用名称
    "DEBUG": true,                            // 调试模式
    "DB_HOST": "localhost",                   // 数据库地址
    "DB_PORT": 3306,                         // 数据库端口
    "DB_USER": "root",                       // 数据库用户
    "DB_PASSWORD": "password",               // 数据库密码
    "DB_NAME": "feishu_plus",               // 数据库名
    "FEISHU_APPS": [                        // 飞书应用配置列表
        {
            "app_id": "cli_xxx",            // 应用ID
            "app_secret": "xxx",            // 应用密钥
            "fastgpt_url": "http://localhost:3000", // FastGPT地址
            "fastgpt_key": "fastgpt-xxx",   // FastGPT密钥
            "aichat_enable": true,          // 启用AI聊天
            "dataset_sync": true            // 启用知识库同步
        }
    ]
}
```

## 🏗️ 项目结构

```
feishu_fastgpt/
├── app/                   # 后端应用
│   ├── api/               # API路由
│   ├── core/              # 核心配置
│   ├── db/                # 数据库
│   ├── models/            # 数据模型
│   ├── schemas/           # 数据模式
│   ├── services/          # 业务逻辑
│   └── utils/             # 工具函数
├── web/                   # 前端界面
│   ├── src/               # 源代码
│   │   ├── components/    # 组件
│   │   ├── views/         # 页面
│   │   └── api/           # API调用
│   ├── dist/              # 构建输出目录
│   └── public/            # 静态资源
├── config/                # 配置文件
├── docs/                  # 文档
├── logs/                  # 日志
├── temp/                  # 临时文件
├── feishu_plus_app.py     # 主程序入口
├── single_app_worker.py   # 单应用工作进程
├── start.sh               # 启动脚本
└── requirements.txt       # Python依赖
```

## 🚀 部署指南

### 生产环境部署

```bash
# 使用gunicorn部署
pip install gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# 使用nginx反向代理
# 配置nginx.conf
upstream feishu_fastgpt {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://feishu_fastgpt;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 进程管理

项目提供了多进程管理脚本：

```bash
# 启动所有应用
./start.sh

# 查看进程状态
ps aux | grep "feishu"

# 停止所有进程（可以kill 不要使用kill -9）
pkill -f "python.*feishu"
```

## 🤝 贡献指南

我们欢迎所有形式的贡献！请查看 [贡献指南](CONTRIBUTING.md) 了解详情。

## 📝 更新日志

查看 [CHANGELOG.md](CHANGELOG.md) 了解版本更新历史。

### 最新版本 v2.1.0
- ✨ 支持飞书机器人智能问答
- 📚 知识库自动同步功能
- 🖥️ Web管理界面
- ⚡ 多进程架构支持

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源协议。

## 🙏 致谢

- [飞书开放平台](https://open.feishu.cn/) - 提供强大的企业级通讯API
- [FastGPT](https://fastgpt.in/) - 优秀的知识库问答系统
- [FastAPI](https://fastapi.tiangolo.com/) - 现代化的Python Web框架
- [Vue.js](https://vuejs.org/) - 渐进式JavaScript框架

## 📞 支持与反馈

- 🐛 [提交Bug](https://github.com/answerlink/feishu_fastgpt/issues/new?template=bug_report.md)
- 💡 [功能建议](https://github.com/answerlink/feishu_fastgpt/issues/new?template=feature_request.md)
- 📖 [查看文档](https://github.com/answerlink/feishu_fastgpt/wiki)
- 💬 [讨论交流](https://github.com/answerlink/feishu_fastgpt/discussions)

---

<div align="center">

**如果这个项目对您有帮助，请给我们一个 ⭐️ Star！**

Made with ❤️ by [AnswerLink Team](https://github.com/answerlink)

</div>
