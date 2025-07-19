"""
日志管理器测试模块
"""

import os
import tempfile
import logging
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from health_monitor.utils.log_manager import (
    LogManager, LogLevel, get_logger, configure_logging, log_manager
)


class TestLogManager:
    """日志管理器测试类"""
    
    def setup_method(self):
        """每个测试方法前的设置"""
        # 重置单例实例
        LogManager._instance = None
        LogManager._initialized = False
    
    def test_singleton_pattern(self):
        """测试单例模式"""
        manager1 = LogManager()
        manager2 = LogManager()
        
        assert manager1 is manager2
        assert id(manager1) == id(manager2)
    
    def test_default_configuration(self):
        """测试默认配置"""
        manager = LogManager()
        
        assert manager._log_level == LogLevel.INFO
        assert manager._log_file is None
        assert manager._max_file_size == 10 * 1024 * 1024
        assert manager._backup_count == 5
        assert manager._enable_console is True
        assert manager._enable_file is False
    
    def test_configure_log_level(self):
        """测试日志级别配置"""
        manager = LogManager()
        
        # 测试有效的日志级别
        config = {'log_level': 'DEBUG'}
        manager.configure(config)
        assert manager._log_level == LogLevel.DEBUG
        
        config = {'log_level': 'error'}  # 测试小写
        manager.configure(config)
        assert manager._log_level == LogLevel.ERROR
        
        # 测试无效的日志级别
        config = {'log_level': 'INVALID'}
        with pytest.raises(ValueError, match="无效的日志级别"):
            manager.configure(config)
    
    def test_configure_file_settings(self):
        """测试文件设置配置"""
        manager = LogManager()
        
        config = {
            'log_file': '/tmp/test.log',
            'max_file_size': 5 * 1024 * 1024,
            'backup_count': 3,
            'enable_file': True
        }
        
        manager.configure(config)
        
        assert manager._log_file == '/tmp/test.log'
        assert manager._max_file_size == 5 * 1024 * 1024
        assert manager._backup_count == 3
        assert manager._enable_file is True
    
    def test_configure_console_settings(self):
        """测试控制台设置配置"""
        manager = LogManager()
        
        config = {
            'enable_console': False,
            'console_format': '%(levelname)s - %(message)s'
        }
        
        manager.configure(config)
        
        assert manager._enable_console is False
        assert manager._console_format == '%(levelname)s - %(message)s'
    
    def test_get_logger_console_only(self):
        """测试获取仅控制台输出的日志记录器"""
        manager = LogManager()
        manager.configure({'log_level': 'DEBUG', 'enable_console': True})
        
        logger = manager.get_logger('test_logger')
        
        assert isinstance(logger, logging.Logger)
        assert logger.name == 'test_logger'
        assert logger.level == logging.DEBUG
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.StreamHandler)
    
    @patch('pathlib.Path.mkdir')
    def test_get_logger_with_file(self, mock_mkdir):
        """测试获取带文件输出的日志记录器"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = os.path.join(temp_dir, 'test.log')
            
            manager = LogManager()
            manager.configure({
                'log_level': 'INFO',
                'log_file': log_file,
                'enable_console': True,
                'enable_file': True
            })
            
            logger = manager.get_logger('test_file_logger')
            
            assert len(logger.handlers) == 2
            
            # 检查处理器类型
            handler_types = [type(handler).__name__ for handler in logger.handlers]
            assert 'StreamHandler' in handler_types
            assert 'RotatingFileHandler' in handler_types
    
    def test_logger_caching(self):
        """测试日志记录器缓存"""
        manager = LogManager()
        
        logger1 = manager.get_logger('cached_logger')
        logger2 = manager.get_logger('cached_logger')
        
        assert logger1 is logger2
        assert len(manager._loggers) == 1
    
    def test_set_level(self):
        """测试设置日志级别"""
        manager = LogManager()
        logger = manager.get_logger('level_test')
        
        # 初始级别
        assert logger.level == LogLevel.INFO.value
        
        # 更改级别
        manager.set_level(LogLevel.ERROR)
        assert manager._log_level == LogLevel.ERROR
        assert logger.level == LogLevel.ERROR.value
        
        # 检查处理器级别也被更新
        for handler in logger.handlers:
            assert handler.level == LogLevel.ERROR.value
    
    @patch('pathlib.Path.mkdir')
    def test_add_file_handler(self, mock_mkdir):
        """测试添加文件处理器"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = os.path.join(temp_dir, 'added.log')
            
            manager = LogManager()
            logger = manager.get_logger('file_handler_test')
            
            # 初始只有控制台处理器
            assert len(logger.handlers) == 1
            
            # 添加文件处理器
            manager.add_file_handler(log_file, max_size=1024, backup_count=2)
            
            assert len(logger.handlers) == 2
            assert manager._log_file == log_file
            assert manager._max_file_size == 1024
            assert manager._backup_count == 2
    
    def test_remove_file_handler(self):
        """测试移除文件处理器"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = os.path.join(temp_dir, 'remove.log')
            
            manager = LogManager()
            manager.configure({
                'log_file': log_file,
                'enable_file': True
            })
            
            logger = manager.get_logger('remove_test')
            initial_handler_count = len(logger.handlers)
            
            # 移除文件处理器
            manager.remove_file_handler()
            
            assert len(logger.handlers) < initial_handler_count
            assert manager._enable_file is False
    
    def test_get_log_stats(self):
        """测试获取日志统计信息"""
        manager = LogManager()
        manager.configure({
            'log_level': 'WARNING',
            'enable_console': True,
            'enable_file': False
        })
        
        # 创建一些日志记录器
        manager.get_logger('stats_test1')
        manager.get_logger('stats_test2')
        
        stats = manager.get_log_stats()
        
        assert stats['loggers_count'] == 2
        assert stats['log_level'] == 'WARNING'
        assert stats['console_logging_enabled'] is True
        assert stats['file_logging_enabled'] is False
        assert 'max_file_size' in stats
        assert 'backup_count' in stats
    
    @patch('os.path.getsize')
    @patch('os.path.exists')
    def test_get_log_stats_with_file(self, mock_exists, mock_getsize):
        """测试带文件的日志统计信息"""
        mock_exists.return_value = True
        mock_getsize.return_value = 1024
        
        manager = LogManager()
        manager.configure({
            'log_file': '/tmp/stats.log',
            'enable_file': True
        })
        
        stats = manager.get_log_stats()
        
        assert stats['current_log_size'] == 1024
        mock_exists.assert_called_once_with('/tmp/stats.log')
        mock_getsize.assert_called_once_with('/tmp/stats.log')
    
    def test_cleanup(self):
        """测试资源清理"""
        manager = LogManager()
        
        # 创建一些日志记录器
        logger1 = manager.get_logger('cleanup_test1')
        logger2 = manager.get_logger('cleanup_test2')
        
        assert len(manager._loggers) == 2
        
        # 模拟处理器的close方法
        for logger in [logger1, logger2]:
            for handler in logger.handlers:
                handler.close = MagicMock()
        
        # 执行清理
        manager.cleanup()
        
        assert len(manager._loggers) == 0
        
        # 验证处理器的close方法被调用
        for logger in [logger1, logger2]:
            for handler in logger.handlers:
                handler.close.assert_called_once()


class TestLogManagerConvenienceFunctions:
    """日志管理器便捷函数测试类"""
    
    def setup_method(self):
        """每个测试方法前的设置"""
        # 重置单例实例
        LogManager._instance = None
        LogManager._initialized = False
    
    def test_get_logger_function(self):
        """测试get_logger便捷函数"""
        logger = get_logger('convenience_test')
        
        assert isinstance(logger, logging.Logger)
        assert logger.name == 'convenience_test'
    
    def test_configure_logging_function(self):
        """测试configure_logging便捷函数"""
        config = {
            'log_level': 'DEBUG',
            'enable_console': True
        }
        
        configure_logging(config)
        
        # 验证配置是否生效
        logger = get_logger('config_test')
        assert logger.level == logging.DEBUG
    
    def test_global_log_manager_instance(self):
        """测试全局日志管理器实例"""
        from health_monitor.utils.log_manager import log_manager
        
        assert isinstance(log_manager, LogManager)
        
        # 由于单例模式，新创建的实例应该是同一个
        # 但由于我们在setup_method中重置了单例，这里需要特殊处理
        # 验证log_manager是LogManager的实例即可
        assert isinstance(log_manager, LogManager)


class TestLogManagerIntegration:
    """日志管理器集成测试类"""
    
    def setup_method(self):
        """每个测试方法前的设置"""
        LogManager._instance = None
        LogManager._initialized = False
    
    def test_logging_output(self):
        """测试实际的日志输出"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = os.path.join(temp_dir, 'integration.log')
            
            manager = LogManager()
            manager.configure({
                'log_level': 'INFO',
                'log_file': log_file,
                'enable_console': False,
                'enable_file': True
            })
            
            logger = manager.get_logger('integration_test')
            
            # 写入一些日志
            logger.info('这是一条信息日志')
            logger.warning('这是一条警告日志')
            logger.error('这是一条错误日志')
            
            # 强制刷新处理器
            for handler in logger.handlers:
                handler.flush()
            
            # 验证文件是否创建并包含内容
            assert os.path.exists(log_file)
            
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()
                assert '这是一条信息日志' in content
                assert '这是一条警告日志' in content
                assert '这是一条错误日志' in content
    
    def test_log_rotation(self):
        """测试日志轮转功能"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = os.path.join(temp_dir, 'rotation.log')
            
            manager = LogManager()
            manager.configure({
                'log_level': 'INFO',
                'log_file': log_file,
                'max_file_size': 100,  # 很小的文件大小以触发轮转
                'backup_count': 2,
                'enable_console': False,
                'enable_file': True
            })
            
            logger = manager.get_logger('rotation_test')
            
            # 写入大量日志以触发轮转
            for i in range(50):
                logger.info(f'这是第{i}条日志消息，用于测试日志轮转功能')
            
            # 强制刷新
            for handler in logger.handlers:
                handler.flush()
            
            # 检查是否创建了轮转文件
            log_files = list(Path(temp_dir).glob('rotation.log*'))
            assert len(log_files) > 1  # 应该有主文件和至少一个备份文件