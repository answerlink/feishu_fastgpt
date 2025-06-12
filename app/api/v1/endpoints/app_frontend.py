from fastapi import APIRouter
from fastapi.responses import HTMLResponse, FileResponse
import os
import mimetypes
from pathlib import Path

router = APIRouter()

# 前端静态文件路径
FRONTEND_DIR = Path(__file__).parent.parent.parent.parent.parent / "web" / "dist"

@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_app_frontend():
    """服务子应用的前端页面"""
    # 优先尝试返回Vue应用
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file, media_type="text/html")
    
    # 如果没有构建的Vue应用，返回简单页面
    # 获取当前应用信息
    app_id = os.environ.get('FEISHU_SINGLE_APP_ID', 'unknown')
    app_mode = os.environ.get('FEISHU_SINGLE_APP_MODE', 'false')
    
    # 从设置中获取应用名称
    app_name = "飞书应用"
    port = "8000"
    
    if app_mode == 'true':
        from app.core.config import settings
        for app in settings.FEISHU_APPS:
            if app.app_id == app_id:
                app_name = app.app_name
                # 计算端口
                port_offset = 0
                for i, a in enumerate(settings.FEISHU_APPS):
                    if a.app_id == app_id:
                        port_offset = i
                        break
                port = str(8000 + port_offset)
                break
    
    return HTMLResponse(f"""
    <html>
        <head>
            <title>{app_name} - 飞书Plus</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    color: white;
                }}
                .container {{
                    max-width: 800px;
                    margin: 0 auto;
                    background: rgba(255, 255, 255, 0.1);
                    padding: 40px;
                    border-radius: 15px;
                    backdrop-filter: blur(10px);
                    border: 1px solid rgba(255, 255, 255, 0.2);
                }}
                h1 {{
                    text-align: center;
                    margin-bottom: 30px;
                    font-size: 2.5em;
                }}
                .status {{
                    background: rgba(0, 255, 0, 0.2);
                    padding: 15px;
                    border-radius: 8px;
                    margin: 20px 0;
                    border-left: 4px solid #00ff00;
                }}
                .links {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 15px;
                    margin: 30px 0;
                }}
                .link-card {{
                    background: rgba(255, 255, 255, 0.15);
                    padding: 20px;
                    border-radius: 10px;
                    text-align: center;
                    transition: transform 0.3s ease;
                }}
                .link-card:hover {{
                    transform: translateY(-5px);
                }}
                .link-card a {{
                    color: white;
                    text-decoration: none;
                    font-weight: bold;
                }}
                .info {{
                    background: rgba(255, 255, 255, 0.1);
                    padding: 20px;
                    border-radius: 8px;
                    margin: 20px 0;
                }}
                .badge {{
                    display: inline-block;
                    background: rgba(0, 255, 0, 0.3);
                    padding: 5px 10px;
                    border-radius: 15px;
                    font-size: 0.8em;
                    margin-left: 10px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🚀 {app_name}</h1>
                
                <div class="status">
                    <strong>✅ 应用状态:</strong> 运行中 <span class="badge">端口 {port}</span>
                </div>
                
                <div class="info">
                    <h3>📋 应用信息</h3>
                    <p><strong>应用ID:</strong> {app_id}</p>
                    <p><strong>应用名称:</strong> {app_name}</p>
                    <p><strong>运行模式:</strong> 独立进程模式</p>
                </div>
                
                <div class="links">
                    <div class="link-card">
                        <h4>📖 API文档</h4>
                        <a href="/docs" target="_blank">查看接口文档</a>
                    </div>
                    
                    <div class="link-card">
                        <h4>🔧 应用管理</h4>
                        <a href="http://localhost:8000" target="_blank">主控制台</a>
                    </div>
                    
                    <div class="link-card">
                        <h4>📊 健康检查</h4>
                        <a href="/api/v1/test/ping" target="_blank">服务状态</a>
                    </div>
                    
                    <div class="link-card">
                        <h4>📝 应用日志</h4>
                        <a href="/api/v1/logs" target="_blank">查看日志</a>
                    </div>
                </div>
                
                <div class="info">
                    <h3>🔗 快速访问</h3>
                    <ul>
                        <li><a href="/api/v1/test/apps" style="color: #ffd700;">应用列表</a></li>
                        <li><a href="/api/v1/wiki" style="color: #ffd700;">知识空间管理</a></li>
                        <li><a href="/api/v1/documents" style="color: #ffd700;">文档管理</a></li>
                        <li><a href="/api/v1/scheduler/status" style="color: #ffd700;">定时任务状态</a></li>
                    </ul>
                </div>
                
                <div style="text-align: center; margin-top: 40px; opacity: 0.8;">
                    <p>🏠 <a href="http://localhost:8000" style="color: #ffd700;">返回主控制台</a></p>
                </div>
                
                <div style="margin-top: 40px; padding: 20px; background-color: rgba(255,255,255,0.1); border-radius: 8px;">
                    <h3>💡 提示</h3>
                    <p>前端构建文件未找到。如需完整的Web界面，请在 <code>web/</code> 目录下运行 <code>npm run build</code>。</p>
                </div>
            </div>
        </body>
    </html>
    """)

@router.get("/assets/{file_path:path}", include_in_schema=False)
async def serve_assets(file_path: str):
    """服务静态资源文件"""
    static_file = FRONTEND_DIR / "assets" / file_path
    if static_file.exists() and static_file.is_file():
        # 根据文件扩展名确定MIME类型
        mime_type, _ = mimetypes.guess_type(str(static_file))
        return FileResponse(static_file, media_type=mime_type)
    return HTMLResponse("Not Found", status_code=404)

@router.get("/favicon.ico", include_in_schema=False)
async def serve_favicon():
    """服务favicon文件"""
    favicon_file = FRONTEND_DIR / "favicon.ico"
    if favicon_file.exists():
        return FileResponse(favicon_file, media_type="image/x-icon")
    return HTMLResponse("Not Found", status_code=404)

@router.get("/{path:path}", response_class=HTMLResponse, include_in_schema=False)
async def serve_app_spa(path: str):
    """处理子应用前端的SPA路由"""
    # 如果是API路径，不处理
    if path.startswith("api/"):
        return None
    
    # 检查是否是静态资源文件
    static_file = FRONTEND_DIR / path
    if static_file.exists() and static_file.is_file():
        mime_type, _ = mimetypes.guess_type(str(static_file))
        return FileResponse(static_file, media_type=mime_type)
    
    # 对于所有其他路径，返回index.html让Vue Router处理
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file, media_type="text/html")
    else:
        # 返回简化的前端页面
        return await serve_app_frontend() 