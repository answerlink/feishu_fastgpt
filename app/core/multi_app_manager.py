#!/usr/bin/env python3
"""
多飞书应用进程管理器

为每个配置的飞书应用启动独立的进程，解决飞书SDK单进程单连接的限制。
每个进程运行完整的应用实例，但通过环境变量指定要处理的app_id。
"""

import os
import sys
import time
import signal
import subprocess
import multiprocessing
import socket
from typing import Dict, List, Optional
from pathlib import Path
from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger("multi_app_manager")

class MultiAppManager:
    """多飞书应用进程管理器"""
    
    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}
        self.app_ports: Dict[str, int] = {}  # 存储每个应用分配的端口
        self.running = False
        
    def find_free_port(self, start_port: int = 8000) -> int:
        """查找可用端口"""
        # 如果指定范围内没有可用端口，让系统自动分配
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('localhost', 0))
            return s.getsockname()[1]
        
    def start_all_apps(self):
        """启动所有配置的飞书应用进程"""
        if self.running:
            logger.warning("多应用管理器已在运行中")
            return
        
        logger.info("开始启动多飞书应用进程管理器")
        
        # 获取当前工作目录
        current_dir = os.getcwd()
        
        # 启动每个应用的进程
        for app in settings.FEISHU_APPS:
            self.start_app_process(app.app_id, app.app_name, current_dir)
        
        self.running = True
        logger.info(f"多应用管理器启动完成，共启动 {len(self.processes)} 个应用进程")
    
    def start_app_process(self, app_id: str, app_name: str, working_dir: str):
        """启动单个应用的进程"""
        try:
            logger.info(f"正在启动应用进程: {app_name} ({app_id})")
            
            # 分配可用端口
            port = self.find_free_port()
            self.app_ports[app_id] = port
            
            logger.info(f"为应用 {app_name} 分配端口: {port}")
            
            # 设置环境变量
            env = os.environ.copy()
            env['FEISHU_SINGLE_APP_ID'] = app_id  # 指定该进程只处理这个app_id
            env['FEISHU_SINGLE_APP_MODE'] = 'true'  # 启用单应用模式
            env['FEISHU_SINGLE_APP_PORT'] = str(port)  # 指定分配的端口
            
            # 构建命令
            python_path = sys.executable
            script_path = os.path.join(working_dir, "single_app_worker.py")
            
            cmd = [python_path, script_path]
            
            # 启动进程
            process = subprocess.Popen(
                cmd,
                cwd=working_dir,
                env=env,
                text=True,
                # 在Unix/Linux系统下创建新的进程组，Windows下无需设置
                preexec_fn=os.setsid if os.name != 'nt' else None
            )
            
            self.processes[app_id] = process
            logger.info(f"应用进程启动成功: {app_name} ({app_id}), PID: {process.pid}, 端口: {port}")
            
        except Exception as e:
            logger.error(f"启动应用进程失败: {app_name} ({app_id}), 错误: {str(e)}")
            # 如果启动失败，清理端口记录
            if app_id in self.app_ports:
                del self.app_ports[app_id]
    
    def stop_all_apps(self):
        """停止所有应用进程"""
        if not self.running:
            return
        
        logger.info("开始停止所有应用进程")
        
        for app_id, process in self.processes.items():
            try:
                if process.poll() is None:  # 进程还在运行
                    port = self.app_ports.get(app_id, "未知")
                    logger.info(f"正在停止应用进程: {app_id}, PID: {process.pid}, 端口: {port}")
                    
                    # 发送停止信号
                    if os.name == 'nt':  # Windows
                        process.terminate()
                    else:  # Unix/Linux - 杀死整个进程组
                        try:
                            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                        except (OSError, ProcessLookupError):
                            process.terminate()
                    
                    try:
                        process.wait(timeout=5)
                        logger.info(f"应用进程已正常停止: {app_id}")
                    except subprocess.TimeoutExpired:
                        # 强制杀死
                        if os.name == 'nt':  # Windows
                            process.kill()
                        else:  # Unix/Linux - 强制杀死整个进程组
                            try:
                                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                            except (OSError, ProcessLookupError):
                                process.kill()
                        logger.warning(f"应用进程强制停止: {app_id}")
            except Exception as e:
                logger.error(f"停止应用进程失败: {app_id}, 错误: {str(e)}")
        
        self.processes.clear()
        self.app_ports.clear()  # 清理端口记录
        self.running = False
        logger.info("所有应用进程已停止")
    
    def restart_app(self, app_id: str):
        """重启指定应用的进程"""
        app_config = next((app for app in settings.FEISHU_APPS if app.app_id == app_id), None)
        if not app_config:
            logger.error(f"未找到应用配置: {app_id}")
            return False
        
        # 停止旧进程
        if app_id in self.processes:
            process = self.processes[app_id]
            if process.poll() is None:
                old_port = self.app_ports.get(app_id, "未知")
                logger.info(f"正在停止应用进程: {app_id}, 端口: {old_port}")
                
                # 发送停止信号
                if os.name == 'nt':  # Windows
                    process.terminate()
                else:  # Unix/Linux - 杀死整个进程组
                    try:
                        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    except (OSError, ProcessLookupError):
                        process.terminate()
                
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # 强制杀死
                    if os.name == 'nt':  # Windows
                        process.kill()
                    else:  # Unix/Linux - 强制杀死整个进程组
                        try:
                            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                        except (OSError, ProcessLookupError):
                            process.kill()
            
            del self.processes[app_id]
        
        # 清理旧端口记录
        if app_id in self.app_ports:
            del self.app_ports[app_id]
        
        # 启动新进程（会自动分配新端口）
        self.start_app_process(app_id, app_config.app_name, os.getcwd())
        return True
    
    def get_status(self) -> Dict:
        """获取所有应用进程的状态"""
        status = {
            "running": self.running,
            "total_apps": len(settings.FEISHU_APPS),
            "running_processes": 0,
            "apps": []
        }
        
        for app in settings.FEISHU_APPS:
            app_status = {
                "app_id": app.app_id,
                "app_name": app.app_name,
                "status": "stopped",
                "port": self.app_ports.get(app.app_id)  # 包含分配的端口信息
            }
            
            if app.app_id in self.processes:
                process = self.processes[app.app_id]
                if process.poll() is None:
                    app_status["status"] = "running"
                    app_status["pid"] = process.pid
                    status["running_processes"] += 1
                else:
                    app_status["status"] = "failed"
                    app_status["exit_code"] = process.returncode
            
            status["apps"].append(app_status)
        
        return status
    
    def check_processes(self):
        """检查进程状态，重启失败的进程"""
        for app_id, process in list(self.processes.items()):
            if process.poll() is not None:  # 进程已退出
                exit_code = process.returncode
                old_port = self.app_ports.get(app_id, "未知")
                logger.warning(f"应用进程异常退出: {app_id}, 端口: {old_port}, 退出码: {exit_code}")
                
                # 获取应用配置
                app_config = next((app for app in settings.FEISHU_APPS if app.app_id == app_id), None)
                if app_config:
                    logger.info(f"正在重启应用进程: {app_id}")
                    # 移除旧进程和端口记录
                    del self.processes[app_id]
                    if app_id in self.app_ports:
                        del self.app_ports[app_id]
                    # 启动新进程
                    self.start_app_process(app_id, app_config.app_name, os.getcwd())
    
    def get_app_port(self, app_id: str) -> Optional[int]:
        """获取指定应用的端口号"""
        return self.app_ports.get(app_id)
    
    def get_all_ports(self) -> Dict[str, int]:
        """获取所有应用的端口映射"""
        return self.app_ports.copy()

# 全局实例
multi_app_manager = MultiAppManager() 