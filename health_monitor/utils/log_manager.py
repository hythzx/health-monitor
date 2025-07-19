"""
日志管理器模块

提供统一的日志记录功能，支持文件和控制台输出、日志级别配置、
格式化功能和日志轮转。
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from enum import Enum


class LogLevel(Enum):
    """日志级别枚举"""
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class LogManager:
    """
    日志管理器类
    
    提供统一的日志记录功能，支持：
    - 文件和控制台日志输出
    - 日志级别配置
    - 自定义格式化
    - 日志轮转和文件大小管理
    """
    
    _instance: Optional['LogManager'] = None
    _initialized: bool = False
    
    def __new__(cls) -> 'LogManager':
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化日志管理器"""
        if self._initialized:
            return
            
        self._loggers: Dict[str, logging.Logger] = {}
        self._default_format = (
            '%(asctime)s - %(name)s - %(levelname)s - '
            '[%(filename)s:%(lineno)d] - %(message)s'
        )
        self._console_format = (
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        self._date_format = '%Y-%m-%d %H:%M:%S'
        
        # 默认配置
        self._log_level = LogLevel.INFO
        self._log_file: Optional[str] = None
        self._max_file_size = 10 * 1024 * 1024  # 10MB
        self._backup_count = 5
        self._enable_console = True
        self._enable_file = False
        
        self._initialized = True
    
    def configure(self, config: Dict[str, Any]) -> None:
        """
        配置日志管理器
        
        Args:
            config: 日志配置字典，包含以下可选键：
                - log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
                - log_file: 日志文件路径
                - max_file_size: 最大文件大小（字节）
                - backup_count: 备份文件数量
                - enable_console: 是否启用控制台输出
                - enable_file: 是否启用文件输出
                - format: 自定义日志格式
                - console_format: 控制台日志格式
                - date_format: 日期格式
        """
        # 设置日志级别
        if 'log_level' in config:
            level_str = config['log_level'].upper()
            if hasattr(LogLevel, level_str):
                self._log_level = LogLevel[level_str]
            else:
                raise ValueError(f"无效的日志级别: {level_str}")
        
        # 设置日志文件
        if 'log_file' in config:
            self._log_file = config['log_file']
            self._enable_file = True
        
        # 设置文件大小和备份数量
        if 'max_file_size' in config:
            self._max_file_size = config['max_file_size']
        
        if 'backup_count' in config:
            self._backup_count = config['backup_count']
        
        # 设置输出选项
        if 'enable_console' in config:
            self._enable_console = config['enable_console']
        
        if 'enable_file' in config:
            self._enable_file = config['enable_file']
        
        # 设置格式
        if 'format' in config:
            self._default_format = config['format']
        
        if 'console_format' in config:
            self._console_format = config['console_format']
        
        if 'date_format' in config:
            self._date_format = config['date_format']
    
    def get_logger(self, name: str) -> logging.Logger:
        """
        获取指定名称的日志记录器
        
        Args:
            name: 日志记录器名称
            
        Returns:
            配置好的日志记录器实例
        """
        if name in self._loggers:
            return self._loggers[name]
        
        logger = logging.getLogger(name)
        logger.setLevel(self._log_level.value)
        
        # 清除现有的处理器
        logger.handlers.clear()
        
        # 添加控制台处理器
        if self._enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(self._log_level.value)
            console_formatter = logging.Formatter(
                self._console_format,
                datefmt=self._date_format
            )
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)
        
        # 添加文件处理器
        if self._enable_file and self._log_file:
            self._ensure_log_directory()
            
            # 使用RotatingFileHandler实现日志轮转
            file_handler = logging.handlers.RotatingFileHandler(
                self._log_file,
                maxBytes=self._max_file_size,
                backupCount=self._backup_count,
                encoding='utf-8'
            )
            file_handler.setLevel(self._log_level.value)
            file_formatter = logging.Formatter(
                self._default_format,
                datefmt=self._date_format
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        
        # 防止日志向上传播
        logger.propagate = False
        
        self._loggers[name] = logger
        return logger
    
    def _ensure_log_directory(self) -> None:
        """确保日志目录存在"""
        if self._log_file:
            log_dir = Path(self._log_file).parent
            log_dir.mkdir(parents=True, exist_ok=True)
    
    def set_level(self, level: LogLevel) -> None:
        """
        设置全局日志级别
        
        Args:
            level: 新的日志级别
        """
        self._log_level = level
        
        # 更新所有现有日志记录器的级别
        for logger in self._loggers.values():
            logger.setLevel(level.value)
            for handler in logger.handlers:
                handler.setLevel(level.value)
    
    def add_file_handler(self, log_file: str, 
                        max_size: int = None, 
                        backup_count: int = None) -> None:
        """
        为所有日志记录器添加文件处理器
        
        Args:
            log_file: 日志文件路径
            max_size: 最大文件大小（字节）
            backup_count: 备份文件数量
        """
        self._log_file = log_file
        if max_size is not None:
            self._max_file_size = max_size
        if backup_count is not None:
            self._backup_count = backup_count
        
        self._enable_file = True
        self._ensure_log_directory()
        
        # 为所有现有日志记录器添加文件处理器
        for logger in self._loggers.values():
            # 检查是否已有文件处理器
            has_file_handler = any(
                isinstance(handler, logging.handlers.RotatingFileHandler)
                for handler in logger.handlers
            )
            
            if not has_file_handler:
                file_handler = logging.handlers.RotatingFileHandler(
                    self._log_file,
                    maxBytes=self._max_file_size,
                    backupCount=self._backup_count,
                    encoding='utf-8'
                )
                file_handler.setLevel(self._log_level.value)
                file_formatter = logging.Formatter(
                    self._default_format,
                    datefmt=self._date_format
                )
                file_handler.setFormatter(file_formatter)
                logger.addHandler(file_handler)
    
    def remove_file_handler(self) -> None:
        """移除所有日志记录器的文件处理器"""
        self._enable_file = False
        
        for logger in self._loggers.values():
            handlers_to_remove = [
                handler for handler in logger.handlers
                if isinstance(handler, logging.handlers.RotatingFileHandler)
            ]
            
            for handler in handlers_to_remove:
                logger.removeHandler(handler)
                handler.close()
    
    def get_log_stats(self) -> Dict[str, Any]:
        """
        获取日志统计信息
        
        Returns:
            包含日志统计信息的字典
        """
        stats = {
            'loggers_count': len(self._loggers),
            'log_level': self._log_level.name,
            'file_logging_enabled': self._enable_file,
            'console_logging_enabled': self._enable_console,
            'log_file': self._log_file,
            'max_file_size': self._max_file_size,
            'backup_count': self._backup_count
        }
        
        if self._log_file and os.path.exists(self._log_file):
            stats['current_log_size'] = os.path.getsize(self._log_file)
        
        return stats
    
    def cleanup(self) -> None:
        """清理资源"""
        for logger in self._loggers.values():
            for handler in logger.handlers:
                handler.close()
        
        self._loggers.clear()


# 全局日志管理器实例
log_manager = LogManager()


def get_logger(name: str) -> logging.Logger:
    """
    获取日志记录器的便捷函数
    
    Args:
        name: 日志记录器名称
        
    Returns:
        配置好的日志记录器实例
    """
    return log_manager.get_logger(name)


def configure_logging(config: Dict[str, Any]) -> None:
    """
    配置日志系统的便捷函数
    
    Args:
        config: 日志配置字典
    """
    log_manager.configure(config)