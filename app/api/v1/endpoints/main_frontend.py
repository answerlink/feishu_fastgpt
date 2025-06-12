from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import os
from pathlib import Path
import mimetypes

router = APIRouter()

# 前端静态文件路径
FRONTEND_DIR = Path(__file__).parent.parent.parent.parent.parent / "web" / "dist"

@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_main_frontend():
    """服务主控进程的前端页面"""
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file, media_type="text/html")
    else:
        return HTMLResponse(f"""
        <html>
            <head><title>飞书Plus多应用管理系统</title></head>
            <body>
                <h1>🚀 飞书Plus多应用管理系统</h1>
                <h2>📊 系统状态</h2>
                <p><strong>主控进程</strong>: 端口 8000 (当前页面)</p>
                
                <h2>🔗 快速访问</h2>
                <ul>
                    <li><a href="/docs" target="_blank">📖 主控API文档</a></li>
                    <li><a href="/api/v1/multi-app/status" target="_blank">📊 应用状态API</a></li>
                </ul>
                
                <h2>📱 各应用访问入口</h2>
                <ul>
                    <li><strong>飞书知识库Plus</strong>: <a href="http://localhost:8000" target="_blank">http://localhost:8000</a> | <a href="http://localhost:8000/docs" target="_blank">API文档</a></li>
                    <li><strong>布谷应用</strong>: <a href="http://localhost:8001" target="_blank">http://localhost:8001</a> | <a href="http://localhost:8001/docs" target="_blank">API文档</a></li>
                </ul>
                
                <h2>🛠️ 管理功能</h2>
                <p>使用以下API进行应用管理:</p>
                <ul>
                    <li>GET /api/v1/multi-app/status - 获取应用状态</li>
                    <li>POST /api/v1/multi-app/restart - 重启指定应用</li>
                </ul>
                
                <div style="margin-top: 40px; padding: 20px; background-color: #f5f5f5; border-radius: 8px;">
                    <h3>💡 提示</h3>
                    <p>前端构建文件未找到。如需完整的Web界面，请在 <code>web/</code> 目录下运行 <code>npm run build</code>。</p>
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
async def serve_main_spa(path: str):
    """处理主控前端的SPA路由"""
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
        return await serve_main_frontend()

@router.get("/debug", response_class=HTMLResponse, include_in_schema=False)
async def serve_debug_page():
    """调试页面"""
    debug_file = Path(__file__).parent.parent.parent.parent.parent / "debug_frontend.html"
    if debug_file.exists():
        return FileResponse(debug_file, media_type="text/html")
    else:
        return HTMLResponse("""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <title>前端调试</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; }
                .test { margin: 10px 0; padding: 10px; border: 1px solid #ddd; }
            </style>
        </head>
        <body>
            <h1>🔧 前端调试</h1>
            <div class="test">
                <h3>路由测试</h3>
                <a href="/">首页</a> | 
                <a href="/app-status">应用状态</a> | 
                <a href="/wiki-spaces">知识空间</a> | 
                <a href="/log-viewer">系统日志</a>
            </div>
            <div class="test" id="api-test">
                <h3>API测试</h3>
                <button onclick="testAPI()">测试API</button>
                <div id="result"></div>
            </div>
            <script>
                async function testAPI() {
                    try {
                        const response = await fetch('/api/v1/test/apps');
                        const data = await response.json();
                        document.getElementById('result').innerHTML = 
                            '✅ API正常: ' + JSON.stringify(data, null, 2);
                    } catch (error) {
                        document.getElementById('result').innerHTML = 
                            '❌ API错误: ' + error.message;
                    }
                }
            </script>
        </body>
        </html>
        """) 