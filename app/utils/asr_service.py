import os
import aiohttp
import logging
from typing import Optional, Dict, Any
from app.core.logger import setup_logger

logger = setup_logger("asr_service")


class ASRService:
    """语音转文字(ASR)服务类"""
    
    def __init__(self, asr_api_url: str, asr_api_key: Optional[str] = None):
        """初始化ASR服务
        
        Args:
            asr_api_url: ASR API的URL
            asr_api_key: ASR API的认证密钥
        """
        self.asr_api_url = asr_api_url.rstrip('/')
        self.asr_api_key = asr_api_key
        logger.info(f"ASR服务初始化: {self.asr_api_url}")
        if asr_api_key:
            logger.info("ASR API Key 已配置")
    
    async def transcribe_audio_file(self, audio_file_path: str, language: str = "auto") -> Dict[str, Any]:
        """转录音频文件为文字
        
        Args:
            audio_file_path: 音频文件路径
            language: 语言代码，默认为auto自动检测
            
        Returns:
            Dict[str, Any]: 包含转录结果的字典
                - success: bool, 是否成功
                - text: str, 转录的文字内容
                - error: str, 错误信息(如果失败)
                - duration: float, 音频时长(如果有)
                - language: str, 检测到的语言(如果有)
        """
        try:
            # 检查文件是否存在
            if not os.path.exists(audio_file_path):
                return {
                    "success": False,
                    "text": "",
                    "error": f"音频文件不存在: {audio_file_path}"
                }
            
            # 检查文件大小
            file_size = os.path.getsize(audio_file_path)
            if file_size == 0:
                return {
                    "success": False,
                    "text": "",
                    "error": f"音频文件为空: {audio_file_path}"
                }
            
            logger.info(f"开始转录音频文件: {audio_file_path}, 文件大小: {file_size} bytes")
            
            # 准备表单数据
            data = aiohttp.FormData()
            
            # 先读取文件内容到内存中，避免文件句柄提前关闭
            with open(audio_file_path, 'rb') as f:
                audio_bytes = f.read()
            
            data.add_field('file', 
                         audio_bytes,
                         filename=os.path.basename(audio_file_path),
                         content_type='audio/opus')
            
            # 如果需要指定语言，可以添加其他参数
            if language and language != "auto":
                data.add_field('language', language)
            
            # 准备请求头
            headers = {}
            if self.asr_api_key:
                headers['Authorization'] = f'Bearer {self.asr_api_key}'
            
            # 发送请求
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
                logger.debug(f"发送ASR请求到: {self.asr_api_url}")
                
                async with session.post(self.asr_api_url, data=data, headers=headers) as response:
                    logger.debug(f"ASR响应状态码: {response.status}")
                    
                    if response.status == 200:
                        result = await response.json()
                        logger.debug(f"ASR响应内容: {result}")
                        
                        # 提取转录文字
                        transcribed_text = result.get("text", "").strip()
                        
                        if transcribed_text:
                            logger.info(f"语音转录成功: {transcribed_text[:100]}...")
                            return {
                                "success": True,
                                "text": transcribed_text,
                                "error": "",
                                "language": result.get("language", ""),
                                "duration": result.get("duration", 0.0)
                            }
                        else:
                            logger.warning("ASR返回空文本")
                            return {
                                "success": False,
                                "text": "",
                                "error": "ASR返回空文本，可能是静音或无法识别的音频"
                            }
                    else:
                        error_text = await response.text()
                        logger.error(f"ASR请求失败: HTTP {response.status}, 响应: {error_text}")
                        return {
                            "success": False,
                            "text": "",
                            "error": f"ASR请求失败: HTTP {response.status}, {error_text}"
                        }
                        
        except aiohttp.ClientError as e:
            error_msg = f"ASR网络请求失败: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "text": "",
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"ASR转录异常: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "text": "",
                "error": error_msg
            }
    
    def check_service_health(self) -> bool:
        """检查ASR服务是否可用
        
        Returns:
            bool: 服务是否可用
        """
        try:
            # 这里可以实现健康检查逻辑
            # 比如发送一个ping请求或者检查服务状态
            return True
        except Exception as e:
            logger.error(f"ASR服务健康检查失败: {str(e)}")
            return False 