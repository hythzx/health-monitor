"""配置文件监控器"""

import asyncio
import logging
from typing import Callable, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent
from .config_manager import ConfigManager
from ..utils.exceptions import ConfigError


class ConfigFileHandler(FileSystemEventHandler):
    """配置文件变更事件处理器"""
    
    def __init__(self, config_path: str, callback: Callable):
        """
        初始化事件处理器
        
        Args:
            config_path: 配置文件路径
            callback: 配置变更回调函数
        """
        self.config_path = config_path
        self.callback = callback
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """处理文件修改事件"""
        if not event.is_directory and event.src_path == self.config_path:
            self.logger.info(f"检测到配置文件变更: {self.config_path}")
            try:
                self.callback()
            except Exception as e:
                self.logger.error(f"处理配置变更失败: {e}")


class ConfigWatcher:
    """配置文件监控器，支持热更新"""
    
    def __init__(self, config_manager: ConfigManager):
        """
        初始化配置监控器
        
        Args:
            config_manager: 配置管理器实例
        """
        self.config_manager = config_manager
        self.observer: Optional[Observer] = None
        self.logger = logging.getLogger(__name__)
        self.change_callbacks = []
        self._running = False
    
    def add_change_callback(self, callback: Callable):
        """
        添加配置变更回调函数
        
        Args:
            callback: 回调函数，当配置变更时被调用
        """
        self.change_callbacks.append(callback)
    
    def remove_change_callback(self, callback: Callable):
        """
        移除配置变更回调函数
        
        Args:
            callback: 要移除的回调函数
        """
        if callback in self.change_callbacks:
            self.change_callbacks.remove(callback)
    
    def _on_config_changed(self):
        """处理配置文件变更"""
        try:
            # 重新加载配置
            old_config = self.config_manager.config.copy()
            new_config = self.config_manager.reload_config()
            
            self.logger.info("配置文件已重新加载")
            
            # 调用所有回调函数
            for callback in self.change_callbacks:
                try:
                    callback(old_config, new_config)
                except Exception as e:
                    self.logger.error(f"配置变更回调执行失败: {e}")
                    
        except ConfigError as e:
            self.logger.error(f"配置重新加载失败: {e}")
        except Exception as e:
            self.logger.error(f"处理配置变更时发生未知错误: {e}")
    
    def start_watching(self):
        """开始监控配置文件"""
        if self._running:
            self.logger.warning("配置监控器已经在运行")
            return
        
        try:
            import os
            config_dir = os.path.dirname(os.path.abspath(self.config_manager.config_path))
            
            # 创建文件系统观察者
            self.observer = Observer()
            event_handler = ConfigFileHandler(
                os.path.abspath(self.config_manager.config_path),
                self._on_config_changed
            )
            
            self.observer.schedule(event_handler, config_dir, recursive=False)
            self.observer.start()
            self._running = True
            
            self.logger.info(f"开始监控配置文件: {self.config_manager.config_path}")
            
        except Exception as e:
            self.logger.error(f"启动配置监控失败: {e}")
            raise ConfigError(f"启动配置监控失败: {e}")
    
    def stop_watching(self):
        """停止监控配置文件"""
        if not self._running:
            return
        
        try:
            if self.observer:
                self.observer.stop()
                self.observer.join()
                self.observer = None
            
            self._running = False
            self.logger.info("配置文件监控已停止")
            
        except Exception as e:
            self.logger.error(f"停止配置监控失败: {e}")
    
    def is_running(self) -> bool:
        """
        检查监控器是否正在运行
        
        Returns:
            bool: 监控器是否正在运行
        """
        return self._running
    
    async def watch_config_changes_async(self, check_interval: int = 5):
        """
        异步方式监控配置变更（轮询方式）
        
        Args:
            check_interval: 检查间隔（秒）
        """
        self.logger.info(f"开始异步监控配置文件变更，检查间隔: {check_interval}秒")
        
        while True:
            try:
                if self.config_manager.is_config_changed():
                    self.logger.info("检测到配置文件变更")
                    self._on_config_changed()
                
                await asyncio.sleep(check_interval)
                
            except asyncio.CancelledError:
                self.logger.info("配置监控任务已取消")
                break
            except Exception as e:
                self.logger.error(f"配置监控过程中发生错误: {e}")
                await asyncio.sleep(check_interval)
    
    def __enter__(self):
        """上下文管理器入口"""
        self.start_watching()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.stop_watching()