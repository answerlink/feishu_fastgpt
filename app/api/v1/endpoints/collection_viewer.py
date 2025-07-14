from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
import json
import aiohttp
from datetime import datetime
from app.core.logger import setup_logger
from app.services.feishu_bot import FeishuBotService
from app.core.config import settings

logger = setup_logger("collection_viewer")

router = APIRouter()

class CollectionData(BaseModel):
    """知识块数据模型"""
    collection: Dict[str, Any]
    q: str = ""
    a: str = ""

# 存储临时数据的字典（实际应用中应该使用数据库或缓存）
temp_data_store = {}

async def get_collection_download_url_direct(collection_id: str, app_config) -> Optional[str]:
    """直接获取collection的下载链接
    
    Args:
        collection_id: collection文件ID
        app_config: 应用配置对象
        
    Returns:
        str: 下载链接，失败返回None
    """
    try:
        # 获取配置
        read_collection_url = getattr(app_config, 'aichat_read_collection_url', None)
        read_collection_key = getattr(app_config, 'aichat_read_collection_key', None)
        client_download_host = getattr(app_config, 'aichat_client_download_host', None)
        
        logger.info(f"下载配置检查: read_collection_url={read_collection_url}")
        logger.info(f"下载配置检查: read_collection_key={'***' if read_collection_key else None}")
        logger.info(f"下载配置检查: client_download_host={client_download_host}")

        if not read_collection_url or not read_collection_key:
            logger.warning("AI Chat读取集合配置不完整，无法获取下载链接")
            return None
        
        headers = {
            "Authorization": f"Bearer {read_collection_key}",
            "Content-Type": "application/json"
        }
        
        body_data = {
            "collectionId": collection_id
        }
        
        # 使用临时的客户端会话
        async with aiohttp.ClientSession() as client:
            async with client.post(read_collection_url, json=body_data, headers=headers) as response:
                result = await response.json()
                
                if result.get("code") == 200:
                    data = result.get("data", {})
                    file_value = data.get("value", "")
                    
                    if file_value and file_value.startswith("/"):
                        # 拼接完整的下载链接
                        download_url = client_download_host.rstrip('/') + file_value
                        logger.info(f"获取到collection下载链接: {download_url}")
                        return download_url
                    else:
                        logger.warning(f"collection返回的value格式不正确: {file_value}")
                        return None
                else:
                    logger.error(f"获取collection下载链接失败: {result}")
                    return None
                    
    except Exception as e:
        logger.error(f"获取collection下载链接异常: {str(e)}")
        return None

async def get_quote_data_from_fastgpt(quote_id: str, app_id: str, chat_id: str) -> Optional[Dict[str, Any]]:
    """从FastGPT获取知识块数据
    
    Args:
        quote_id: 知识块ID
        app_id: 应用ID
        chat_id: 聊天ID
        
    Returns:
        Dict: 知识块数据，失败返回None
    """
    try:
        # 获取应用配置
        app_config = None
        for app in settings.FEISHU_APPS:
            aichat_app_id = getattr(app, 'aichat_app_id', None)
            if aichat_app_id and aichat_app_id == app_id:
                app_config = app
                break
        
        if not app_config:
            logger.warning(f"未找到匹配的应用配置: app_id={app_id}")
            return None
        
        # 使用AI Chat的FastGPT配置（因为我们的app_id实际上是aichat_app_id）
        # 优先使用aichat相关配置，如果没有则回退到主配置
        aichat_url = getattr(app_config, 'aichat_url', None)
        aichat_key = getattr(app_config, 'aichat_key', None)
        
        # 如果有AI Chat配置，则从AI Chat URL构建FastGPT URL
        if aichat_url and aichat_key:
            # 如果aichat_url是FastGPT的完整URL，直接使用
            if "/api/v1/chat/completions" in aichat_url:
                # 从 http://xxx/api/v1/chat/completions 提取基础URL
                fastgpt_url = aichat_url.replace("/api/v1/chat/completions", "")
            else:
                fastgpt_url = aichat_url.rstrip('/')
            fastgpt_key = aichat_key
        else:
            # 回退到主FastGPT配置
            fastgpt_url = getattr(app_config, 'fastgpt_url', None)
            fastgpt_key = getattr(app_config, 'fastgpt_key', None)
        
        if not fastgpt_url or not fastgpt_key:
            logger.warning(f"FastGPT配置不完整，无法获取知识块数据: app_id={app_id}")
            return None
        
        url = f"{fastgpt_url.rstrip('/')}/api/core/dataset/data/getQuoteData"
        headers = {
            "Authorization": f"Bearer {fastgpt_key}",
            "Content-Type": "application/json"
        }
        
        body_data = {
            "id": quote_id,
            "appId": app_id,
            "chatId": chat_id,
            "chatItemDataId": chat_id
        }
        
        logger.info(f"从FastGPT获取知识块数据: quote_id={quote_id}, app_id={app_id}, chat_id={chat_id}")
        logger.info(f"使用URL: {url}")
        logger.info(f"请求数据: {body_data}")
        
        async with aiohttp.ClientSession() as client:
            async with client.post(url, json=body_data, headers=headers) as response:
                response_text = await response.text()
                logger.info(f"FastGPT响应状态: {response.status}")
                logger.info(f"FastGPT响应内容: {response_text}")
                
                try:
                    result = json.loads(response_text)
                except json.JSONDecodeError:
                    logger.error(f"无法解析FastGPT响应为JSON: {response_text}")
                    return None
                
                if result.get("code") == 200:
                    data = result.get("data", {})
                    logger.info(f"获取知识块数据成功: {quote_id}")
                    return data
                else:
                    logger.error(f"获取知识块数据失败: {result}")
                    return None
                    
    except Exception as e:
        logger.error(f"获取知识块数据异常: {str(e)}")
        import traceback
        logger.error(f"异常详情: {traceback.format_exc()}")
        return None

@router.get("/view/{collection_id}", response_class=HTMLResponse)
async def view_collection(collection_id: str):
    """展示知识块详情页面
    
    Args:
        collection_id: 知识块ID
        
    Returns:
        HTMLResponse: 知识块详情页面
    """
    try:
        html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>知识块详情 - {collection_id}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}
        
        .card {{
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
            overflow: hidden;
            margin-bottom: 20px;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5rem;
            margin-bottom: 10px;
            font-weight: 300;
        }}
        
        .header p {{
            font-size: 1.1rem;
            opacity: 0.9;
        }}
        
        .content {{
            padding: 30px;
        }}
        
        .info-section {{
            margin-bottom: 30px;
        }}
        
        .info-title {{
            font-size: 1.5rem;
            color: #333;
            margin-bottom: 15px;
            padding-bottom: 8px;
            border-bottom: 2px solid #667eea;
        }}
        
        .info-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        
        .info-item {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }}
        
        .info-label {{
            font-weight: 600;
            color: #555;
            margin-bottom: 5px;
        }}
        
        .info-value {{
            color: #333;
            word-break: break-all;
        }}
        
        .content-box {{
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
        }}
        
        .content-title {{
            font-weight: 600;
            color: #333;
            margin-bottom: 10px;
            font-size: 1.1rem;
        }}
        
        .content-text {{
            line-height: 1.8;
            color: #555;
            white-space: pre-wrap;
        }}
        
        .download-section {{
            text-align: center;
            padding: 30px;
            background: #f8f9fa;
            border-top: 1px solid #e9ecef;
        }}
        
        .download-btn {{
            display: inline-flex;
            align-items: center;
            gap: 10px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 30px;
            border: none;
            border-radius: 8px;
            font-size: 1.1rem;
            font-weight: 500;
            text-decoration: none;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
        }}
        
        .download-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
        }}
        
        .download-btn:active {{
            transform: translateY(0);
        }}
        
        .loading {{
            display: none;
            color: #666;
            font-style: italic;
        }}
        
        .error {{
            color: #dc3545;
            background: #f8d7da;
            border: 1px solid #f5c6cb;
            padding: 15px;
            border-radius: 8px;
            margin: 20px 0;
        }}
        
        .success {{
            color: #155724;
            background: #d4edda;
            border: 1px solid #c3e6cb;
            padding: 15px;
            border-radius: 8px;
            margin: 20px 0;
        }}
        
        @media (max-width: 768px) {{
            .container {{
                padding: 10px;
            }}
            
            .header h1 {{
                font-size: 2rem;
            }}
            
            .content {{
                padding: 20px;
            }}
            
            .info-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="header">
                <h1>📚 知识块详情</h1>
                <p>Collection ID: {collection_id}</p>
            </div>
            
            <div class="content">
                <div id="loading" class="loading">
                    正在加载知识块信息...
                </div>
                
                <div id="error" class="error" style="display: none;">
                </div>
                
                <div id="content" style="display: none;">
                    <div class="info-section">
                        <h2 class="info-title">📄 文件信息</h2>
                        <div class="info-grid">
                            <div class="info-item">
                                <div class="info-label">文件名</div>
                                <div class="info-value" id="fileName">-</div>
                            </div>
                            <div class="info-item">
                                <div class="info-label">文件类型</div>
                                <div class="info-value" id="fileType">-</div>
                            </div>
                            <div class="info-item">
                                <div class="info-label">文本长度</div>
                                <div class="info-value" id="textLength">-</div>
                            </div>
                            <div class="info-item">
                                <div class="info-label">分块大小</div>
                                <div class="info-value" id="chunkSize">-</div>
                            </div>
                            <div class="info-item">
                                <div class="info-label">创建时间</div>
                                <div class="info-value" id="createTime">-</div>
                            </div>
                            <div class="info-item">
                                <div class="info-label">更新时间</div>
                                <div class="info-value" id="updateTime">-</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="info-section" id="questionSection" style="display: none;">
                        <h2 class="info-title">❓ 主要内容</h2>
                        <div class="content-box">
                            <div class="content-text" id="questionText"></div>
                        </div>
                    </div>
                    
                    <div class="info-section" id="answerSection" style="display: none;">
                        <h2 class="info-title">💡 附加内容</h2>
                        <div class="content-box">
                            <div class="content-text" id="answerText"></div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="download-section">
                <button id="downloadBtn" class="download-btn" onclick="downloadFile()">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                        <polyline points="7,10 12,15 17,10"></polyline>
                        <line x1="12" y1="15" x2="12" y2="3"></line>
                    </svg>
                    下载原文件
                </button>
                <div id="downloadStatus" style="margin-top: 15px;"></div>
            </div>
        </div>
    </div>

    <script>
        let collectionData = null;
        
        // 页面加载时获取知识块信息
        async function loadCollectionInfo() {{
            try {{
                document.getElementById('loading').style.display = 'block';
                
                const response = await fetch(`/api/v1/collection-viewer/info/{collection_id}`);
                const result = await response.json();
                
                if (result.code === 200) {{
                    collectionData = result.data;
                    displayCollectionInfo(collectionData);
                }} else {{
                    showError('获取知识块信息失败: ' + (result.msg || '未知错误'));
                }}
            }} catch (error) {{
                showError('网络请求失败: ' + error.message);
            }} finally {{
                document.getElementById('loading').style.display = 'none';
            }}
        }}
        
        function displayCollectionInfo(data) {{
            const collection = data.collection || {{}};
            
            // 显示文件信息
            document.getElementById('fileName').textContent = collection.name || '-';
            document.getElementById('fileType').textContent = collection.type || '-';
            document.getElementById('textLength').textContent = formatNumber(collection.rawTextLength) + ' 字符';
            document.getElementById('chunkSize').textContent = collection.chunkSize || '-';
            document.getElementById('createTime').textContent = formatDateTime(collection.createTime);
            document.getElementById('updateTime').textContent = formatDateTime(collection.updateTime);
            
            // 显示问题内容
            if (data.q && data.q.trim()) {{
                document.getElementById('questionText').textContent = data.q;
                document.getElementById('questionSection').style.display = 'block';
            }}
            
            // 显示答案内容
            if (data.a && data.a.trim()) {{
                document.getElementById('answerText').textContent = data.a;
                document.getElementById('answerSection').style.display = 'block';
            }}
            
            document.getElementById('content').style.display = 'block';
        }}
        
        function showError(message) {{
            const errorEl = document.getElementById('error');
            errorEl.textContent = message;
            errorEl.style.display = 'block';
        }}
        
        function formatNumber(num) {{
            if (!num) return '0';
            return num.toLocaleString();
        }}
        
        function formatDateTime(dateStr) {{
            if (!dateStr) return '-';
            try {{
                const date = new Date(dateStr);
                return date.toLocaleString('zh-CN');
            }} catch {{
                return dateStr;
            }}
        }}
        
        async function downloadFile() {{
            if (!collectionData) {{
                showDownloadStatus('请先加载知识块信息', 'error');
                return;
            }}
            
            try {{
                const btn = document.getElementById('downloadBtn');
                btn.disabled = true;
                btn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12,6 12,12 16,14"></polyline></svg> 获取下载链接...';
                
                showDownloadStatus('正在获取下载链接...', 'info');
                
                const response = await fetch(`/api/v1/collection-viewer/download/{collection_id}`);
                const result = await response.json();
                
                if (result.code === 200 && result.data && result.data.download_url) {{
                    showDownloadStatus('下载链接获取成功，正在下载...', 'success');
                    
                    // 创建下载链接
                    const link = document.createElement('a');
                    link.href = result.data.download_url;
                    link.download = collectionData.collection.name || 'download';
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                    
                    showDownloadStatus('文件下载已开始', 'success');
                }} else {{
                    showDownloadStatus('获取下载链接失败: ' + (result.msg || '未知错误'), 'error');
                }}
            }} catch (error) {{
                showDownloadStatus('下载失败: ' + error.message, 'error');
            }} finally {{
                const btn = document.getElementById('downloadBtn');
                btn.disabled = false;
                btn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7,10 12,15 17,10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg> 下载原文件';
            }}
        }}
        
        function showDownloadStatus(message, type) {{
            const statusEl = document.getElementById('downloadStatus');
            statusEl.textContent = message;
            statusEl.className = type || '';
        }}
        
        // 页面加载完成后自动获取信息
        window.addEventListener('DOMContentLoaded', loadCollectionInfo);
    </script>
</body>
</html>
        """
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"生成知识块展示页面失败: collection_id={collection_id}, error={str(e)}")
        raise HTTPException(status_code=500, detail=f"生成页面失败: {str(e)}")

@router.get("/view-quote/{quote_id}", response_class=HTMLResponse)
async def view_quote(quote_id: str, app_id: str = Query(..., description="应用ID"), chat_id: str = Query(..., description="聊天ID")):
    """展示知识块详情页面（直接从FastGPT获取数据）
    
    Args:
        quote_id: 知识块ID
        app_id: 应用ID
        chat_id: 聊天ID
        
    Returns:
        HTMLResponse: 知识块详情页面
    """
    try:
        html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>知识块详情 - {quote_id}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}
        
        .card {{
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
            overflow: hidden;
            margin-bottom: 20px;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5rem;
            margin-bottom: 10px;
            font-weight: 300;
        }}
        
        .header p {{
            font-size: 1.1rem;
            opacity: 0.9;
        }}
        
        .content {{
            padding: 30px;
        }}
        
        .loading {{
            text-align: center;
            padding: 40px;
            color: #666;
        }}
        
        .info-section {{
            margin-bottom: 30px;
            display: none;
        }}
        
        .info-title {{
            font-size: 1.5rem;
            color: #333;
            margin-bottom: 15px;
            padding-bottom: 8px;
            border-bottom: 2px solid #667eea;
        }}
        
        .info-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        
        .info-item {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }}
        
        .info-label {{
            font-weight: 600;
            color: #555;
            margin-bottom: 5px;
        }}
        
        .info-value {{
            color: #333;
            word-break: break-all;
        }}
        
        .content-box {{
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
        }}
        
        .content-title {{
            font-weight: 600;
            color: #333;
            margin-bottom: 10px;
            font-size: 1.1rem;
        }}
        
        .content-text {{
            line-height: 1.8;
            color: #555;
            white-space: pre-wrap;
        }}
        
        .download-section {{
            text-align: center;
            padding: 30px;
            background: #f8f9fa;
            border-top: 1px solid #e9ecef;
            display: none;
        }}
        
        .download-btn {{
            display: inline-flex;
            align-items: center;
            gap: 10px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 30px;
            border: none;
            border-radius: 8px;
            font-size: 1.1rem;
            font-weight: 500;
            text-decoration: none;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
        }}
        
        .download-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
        }}
        
        .download-btn:active {{
            transform: translateY(0);
        }}
        
        .error {{
            color: #dc3545;
            background: #f8d7da;
            border: 1px solid #f5c6cb;
            padding: 15px;
            border-radius: 8px;
            margin: 20px 0;
            display: none;
        }}
        
        .success {{
            color: #155724;
            background: #d4edda;
            border: 1px solid #c3e6cb;
            padding: 15px;
            border-radius: 8px;
            margin: 20px 0;
        }}
        
        .spinner {{
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            width: 30px;
            height: 30px;
            animation: spin 1s linear infinite;
            display: inline-block;
            margin-right: 10px;
        }}
        
        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
        
        @media (max-width: 768px) {{
            .container {{
                padding: 10px;
            }}
            
            .header h1 {{
                font-size: 1.8rem;
            }}
            
            .content {{
                padding: 20px;
            }}
            
            .info-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="header">
                <h1>📚 知识块详情</h1>
                <p>AI 知识库智能问答系统</p>
            </div>
            
            <div class="content">
                <div class="loading" id="loadingSection">
                    <div class="spinner"></div>
                    正在加载知识块信息...
                </div>
                
                <div class="error" id="errorSection">
                    加载失败，请稍后重试。
                </div>
                
                <div class="info-section" id="infoSection">
                    <div class="info-title">📄 文档信息</div>
                    <div class="info-grid">
                        <div class="info-item">
                            <div class="info-label">文件名称</div>
                            <div class="info-value" id="fileName">-</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">文件类型</div>
                            <div class="info-value" id="fileType">-</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">文件大小</div>
                            <div class="info-value" id="fileSize">-</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">创建时间</div>
                            <div class="info-value" id="createTime">-</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">知识块ID</div>
                            <div class="info-value" id="quoteId">{quote_id}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">文件ID</div>
                            <div class="info-value" id="fileId">-</div>
                        </div>
                    </div>
                    
                    <div class="content-box" id="questionBox" style="display: none;">
                        <div class="content-title">💬 主要内容</div>
                        <div class="content-text" id="questionContent"></div>
                    </div>
                    
                    <div class="content-box" id="answerBox" style="display: none;">
                        <div class="content-title">💡 附加内容</div>
                        <div class="content-text" id="answerContent"></div>
                    </div>
                </div>
            </div>
            
            <div class="download-section" id="downloadSection">
                <button class="download-btn" id="downloadBtn" onclick="downloadFile()">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                        <polyline points="7,10 12,15 17,10"></polyline>
                        <line x1="12" y1="15" x2="12" y2="3"></line>
                    </svg>
                    下载原文件
                </button>
                <div id="downloadStatus" class="loading"></div>
            </div>
        </div>
    </div>

    <script>
        // 从URL参数获取必要信息
        const quoteId = '{quote_id}';
        const appId = '{app_id}';
        const chatId = '{chat_id}';
        
        async function loadQuoteInfo() {{
            try {{
                const response = await fetch(`/api/v1/collection-viewer/quote-info/${{quoteId}}?app_id=${{appId}}&chat_id=${{chatId}}`);
                const result = await response.json();
                
                if (result.code === 200 && result.data) {{
                    displayQuoteInfo(result.data);
                }} else {{
                    showError(result.msg || '获取知识块信息失败');
                }}
            }} catch (error) {{
                console.error('获取知识块信息失败:', error);
                showError('网络错误，请稍后重试');
            }}
        }}
        
        function displayQuoteInfo(data) {{
            const loadingEl = document.getElementById('loadingSection');
            const infoEl = document.getElementById('infoSection');
            const downloadEl = document.getElementById('downloadSection');
            
            loadingEl.style.display = 'none';
            infoEl.style.display = 'block';
            downloadEl.style.display = 'block';
            
            // 显示文档信息
            const collection = data.collection || {{}};
            document.getElementById('fileName').textContent = collection.name || '未知文件';
            document.getElementById('fileType').textContent = collection.type || '未知类型';
            document.getElementById('fileSize').textContent = collection.rawTextLength ? `${{collection.rawTextLength}} 字符` : '-';
            document.getElementById('createTime').textContent = collection.createTime ? new Date(collection.createTime).toLocaleString('zh-CN') : '-';
            document.getElementById('fileId').textContent = collection._id || '-';
            
            // 显示问题内容
            if (data.q && data.q.trim()) {{
                const questionBox = document.getElementById('questionBox');
                const questionContent = document.getElementById('questionContent');
                questionBox.style.display = 'block';
                questionContent.textContent = data.q;
            }}
            
            // 显示答案内容
            if (data.a && data.a.trim()) {{
                const answerBox = document.getElementById('answerBox');
                const answerContent = document.getElementById('answerContent');
                answerBox.style.display = 'block';
                answerContent.textContent = data.a;
            }}
        }}
        
        function showError(message) {{
            const loadingEl = document.getElementById('loadingSection');
            const errorEl = document.getElementById('errorSection');
            
            loadingEl.style.display = 'none';
            errorEl.style.display = 'block';
            errorEl.textContent = message;
        }}
        
        async function downloadFile() {{
            const btn = document.getElementById('downloadBtn');
            const statusEl = document.getElementById('downloadStatus');
            
            btn.disabled = true;
            btn.innerHTML = '<div class="spinner"></div> 准备下载...';
            statusEl.style.display = 'block';
            statusEl.textContent = '正在获取下载链接...';
            statusEl.className = 'loading';
            
            try {{
                // 从知识块信息中获取collection_id
                const infoResponse = await fetch(`/api/v1/collection-viewer/quote-info/${{quoteId}}?app_id=${{appId}}&chat_id=${{chatId}}`);
                const infoResult = await infoResponse.json();
                
                if (infoResult.code !== 200 || !infoResult.data || !infoResult.data.collection) {{
                    throw new Error('无法获取文件信息');
                }}
                
                const collectionId = infoResult.data.collection._id;
                if (!collectionId) {{
                    throw new Error('文件ID不存在');
                }}
                
                const downloadResponse = await fetch(`/api/v1/collection-viewer/download/${{collectionId}}?app_id=${{appId}}`);
                const downloadResult = await downloadResponse.json();
                
                if (downloadResult.code === 200 && downloadResult.data && downloadResult.data.download_url) {{
                    statusEl.textContent = '下载开始...';
                    statusEl.className = 'success';
                    
                    // 打开下载链接
                    window.open(downloadResult.data.download_url, '_blank');
                    
                    setTimeout(() => {{
                        statusEl.style.display = 'none';
                    }}, 3000);
                }} else {{
                    throw new Error(downloadResult.msg || '获取下载链接失败');
                }}
            }} catch (error) {{
                console.error('下载失败:', error);
                statusEl.textContent = '下载失败: ' + error.message;
                statusEl.className = 'error';
            }} finally {{
                const btn = document.getElementById('downloadBtn');
                btn.disabled = false;
                btn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7,10 12,15 17,10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg> 下载原文件';
            }}
        }}
        
        // 页面加载完成后自动获取信息
        window.addEventListener('DOMContentLoaded', loadQuoteInfo);
    </script>
</body>
</html>
        """
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"生成知识块展示页面失败: quote_id={quote_id}, app_id={app_id}, chat_id={chat_id}, error={str(e)}")
        raise HTTPException(status_code=500, detail=f"生成页面失败: {str(e)}")

@router.get("/quote-info/{quote_id}")
async def get_quote_info(quote_id: str, app_id: str = Query(..., description="应用ID"), chat_id: str = Query(..., description="聊天ID")):
    """获取知识块信息（从FastGPT获取）
    
    Args:
        quote_id: 知识块ID
        app_id: 应用ID
        chat_id: 聊天ID
        
    Returns:
        JSONResponse: 知识块详细信息
    """
    try:
        # 从FastGPT获取知识块数据
        quote_data = await get_quote_data_from_fastgpt(quote_id, app_id, chat_id)
        
        if quote_data:
            return JSONResponse(content={
                "code": 200,
                "msg": "获取知识块信息成功",
                "data": quote_data
            })
        else:
            return JSONResponse(content={
                "code": -1,
                "msg": "无法获取知识块信息，请检查参数是否正确",
                "data": None
            })
            
    except Exception as e:
        logger.error(f"获取知识块信息失败: quote_id={quote_id}, app_id={app_id}, chat_id={chat_id}, error={str(e)}")
        return JSONResponse(content={
            "code": -1,
            "msg": f"获取知识块信息失败: {str(e)}",
            "data": None
        })

@router.post("/preview")
async def preview_quote(data: CollectionData):
    """预览知识块数据
    知识块包含其所属的collection（文件）信息，用户可以查看知识块内容并下载所属文件。
    
    Args:
        data: 知识块数据（包含collection信息、主要内容q、附加内容a）
        
    Returns:
        JSONResponse: 包含访问链接的响应
    """
    try:
        # 从知识块数据中获取所属collection的ID
        collection_id = data.collection.get("_id", "unknown")
        
        # 存储知识块数据到临时存储（以collection_id为键）
        temp_data_store[collection_id] = data.dict()
        
        # 返回预览链接
        preview_url = f"/api/v1/collection-viewer/view/{collection_id}"
        
        logger.info(f"创建知识块预览: collection_id={collection_id}, name={data.collection.get('name', 'unknown')}")
        
        return JSONResponse(content={
            "code": 200,
            "msg": "创建预览成功",
            "data": {
                "collection_id": collection_id,
                "preview_url": preview_url,
                "collection_name": data.collection.get("name", "未知文档")
            }
        })
        
    except Exception as e:
        logger.error(f"创建知识块预览失败: error={str(e)}")
        return JSONResponse(content={
            "code": -1,
            "msg": f"创建预览失败: {str(e)}",
            "data": None
        })

@router.get("/info/{collection_id}")
async def get_collection_info(collection_id: str):
    """获取知识块信息
    
    Args:
        collection_id: 知识块ID
        
    Returns:
        JSONResponse: 知识块详细信息
    """
    try:
        # 优先从临时存储中获取数据
        if collection_id in temp_data_store:
            stored_data = temp_data_store[collection_id]
            logger.info(f"从临时存储获取知识块信息: collection_id={collection_id}")
            
            return JSONResponse(content={
                "code": 200,
                "statusText": "",
                "message": "",
                "data": stored_data
            })
        
        # 如果临时存储中没有，返回示例数据（向后兼容）
        sample_data = {
            "collection": {
                "_id": collection_id,
                "parentId": None,
                "teamId": "6822b6b24ff4b469a502ff30",
                "tmbId": "6822b6b24ff4b469a502ff39", 
                "datasetId": "6846ea5cf7cf3ed0262dbe60",
                "type": "file",
                "name": "ACS Technical Proposal_202409v1.1.docx",
                "tags": [],
                "fileId": "6846fb68f7cf3ed02636ba96",
                "rawTextLength": 58203,
                "hashRawText": "72f77bd2b6185366173b29cfc240a8660980231140604fe724dd166814c2571b",
                "metadata": {
                    "relatedImgId": "umb6H3MOglMhNTzW"
                },
                "trainingType": "chunk",
                "paragraphChunkDeep": 0,
                "chunkSize": 512,
                "qaPrompt": "",
                "createTime": "2025-06-09T15:19:04.584Z",
                "updateTime": "2025-06-09T15:19:04.584Z",
                "__v": 0
            },
            "q": """1.  View the DNS information

Purpose: Whether the home gateway obtains the correct DNS.

Operation: Read DNS information through the interface.

1.  The user cannot access the Internet through wireless SSID
2.  View link information

Purpose: To check whether the link is normal.

Operation: Read the home gateway line information through the interface: link status, line protocol, upstream and downstream rate and compare with the standard value (standard value acquisition method: opening work order, industry standard), if there is a difference, the system should give the corresponding prompt

1.  Check whether the dialing was successful.""",
            "a": ""
        }
        
        logger.info(f"使用示例数据: collection_id={collection_id}")
        
        return JSONResponse(content={
            "code": 200,
            "statusText": "",
            "message": "",
            "data": sample_data
        })
        
    except Exception as e:
        logger.error(f"获取知识块信息失败: collection_id={collection_id}, error={str(e)}")
        return JSONResponse(content={
            "code": -1,
            "msg": f"获取知识块信息失败: {str(e)}",
            "data": None
        })

@router.get("/download/{collection_id}")
async def get_collection_download(collection_id: str, app_id: str = Query(None, description="应用ID，用于获取下载链接")):
    """获取知识块所属文件的下载链接
    
    Args:
        collection_id: collection文件ID
        app_id: 应用ID（可选，可能是aichat_app_id）
        
    Returns:
        JSONResponse: collection文件的下载链接信息
    """
    try:
        # 查找应用配置 - 支持根据aichat_app_id查找
        logger.info(f"开始查找应用配置: app_id={app_id}")
        target_app_config = None
        target_app_id = None
        
        if app_id:
            # 先尝试根据aichat_app_id查找，如果没找到再根据app_id查找
            for app in settings.FEISHU_APPS:
                aichat_app_id = getattr(app, 'aichat_app_id', None)
                if aichat_app_id and aichat_app_id == app_id:
                    target_app_config = app
                    target_app_id = app.app_id  # 使用真正的app_id
                    break
            
            # 如果根据aichat_app_id没找到，再根据app_id查找
            if not target_app_config:
                for app in settings.FEISHU_APPS:
                    if app.app_id == app_id:
                        target_app_config = app
                        target_app_id = app.app_id
                        break
        else:
            # 如果没有提供app_id，使用第一个可用的应用
            if settings.FEISHU_APPS:
                target_app_config = settings.FEISHU_APPS[0]
                target_app_id = target_app_config.app_id
        
        if not target_app_config or not target_app_id:
            return JSONResponse(content={
                "code": -1,
                "msg": "未找到可用的应用配置",
                "data": None
            })
        
        # 直接调用下载方法，避免创建FeishuBotService实例的复杂性
        download_url = await get_collection_download_url_direct(collection_id, target_app_config)
        
        if download_url:
            return JSONResponse(content={
                "code": 200,
                "msg": "获取下载链接成功",
                "data": {
                    "collection_id": collection_id,
                    "download_url": download_url
                }
            })
        else:
            return JSONResponse(content={
                "code": -1,
                "msg": "无法获取下载链接，请检查collection_id是否正确或配置是否完整",
                "data": None
            })
            
    except Exception as e:
        logger.error(f"获取知识块下载链接失败: collection_id={collection_id}, error={str(e)}")
        return JSONResponse(content={
            "code": -1,
            "msg": f"获取下载链接失败: {str(e)}",
            "data": None
        })