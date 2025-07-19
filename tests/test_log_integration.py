"""
日志集成测试模块

测试各个组件的日志记录功能
"""

import tempfile
import os
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
import pytest

from health_monitor.utils.log_manager import LogManager, configure_logging
from health_monitor.checkers.redis_checker import RedisHealthChecker
from health_monitor.checkers.mongodb_checker import MongoHealthChecker
from health_monitor.alerts.http_alerter import HTTPAlerter
from health_monitor.services.config_manager import ConfigManager
from health_monitor.models.health_check import AlertMessage
from datetime import datetime


class TestLogIntegration:
    """日志集成测试类"""
    
    def setup_method(self):
        """每个测试方法前的设置"""
        # 重置日志管理器
        LogManager._instance = None
        LogManager._initialized = False
        
        # 配置日志到临时文件
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.temp_dir, 'test.log')
        
        configure_logging({
            'log_level': 'DEBUG',
            'log_file': self.log_file,
            'enable_console': False,
            'enable_file': True
        })
    
    def teardown_method(self):
        """每个测试方法后的清理"""
        # 清理临时文件
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_redis_checker_logging(self):
        """测试Redis检查器的日志记录"""
        config = {
            'host': 'localhost',
            'port': 6379,
            'timeout': 5
        }
        
        checker = RedisHealthChecker('test-redis', config)
        
        # 验证日志记录器已创建
        assert checker.logger is not None
        assert 'checker.redis.test-redis' in checker.logger.name
    
    @patch('health_monitor.checkers.redis_checker.redis.Redis')
    @pytest.mark.asyncio
    async def test_redis_checker_health_check_logging(self, mock_redis_class):
        """测试Redis健康检查的日志记录"""
        # 模拟Redis客户端
        mock_client = AsyncMock()
        mock_client.ping.return_value = True
        mock_client.aclose = AsyncMock()
        mock_redis_class.return_value = mock_client
        
        config = {
            'host': 'localhost',
            'port': 6379,
            'timeout': 5
        }
        
        checker = RedisHealthChecker('test-redis', config)
        
        # 执行健康检查
        result = await checker.check_health()
        
        # 验证结果
        assert result.is_healthy is True
        assert result.service_name == 'test-redis'
        
        # 强制刷新日志处理器
        for handler in checker.logger.handlers:
            handler.flush()
        
        # 验证日志文件内容
        if os.path.exists(self.log_file):
            with open(self.log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()
                assert '开始执行Redis健康检查: test-redis' in log_content
                assert 'Redis服务 test-redis PING测试成功' in log_content
                assert '健康检查成功' in log_content
    
    def test_mongodb_checker_logging(self):
        """测试MongoDB检查器的日志记录"""
        config = {
            'host': 'localhost',
            'port': 27017,
            'timeout': 5
        }
        
        checker = MongoHealthChecker('test-mongo', config)
        
        # 验证日志记录器已创建
        assert checker.logger is not None
        assert 'checker.mongo.test-mongo' in checker.logger.name
    
    def test_http_alerter_logging(self):
        """测试HTTP告警器的日志记录"""
        config = {
            'url': 'https://example.com/webhook',
            'method': 'POST',
            'timeout': 10
        }
        
        alerter = HTTPAlerter('test-alerter', config)
        
        # 验证日志记录器已创建
        assert alerter.logger is not None
        assert 'alerter.http.test-alerter' in alerter.logger.name
    
    @patch('aiohttp.ClientSession.request')
    @pytest.mark.asyncio
    async def test_http_alerter_send_logging(self, mock_request):
        """测试HTTP告警器发送的日志记录"""
        # 模拟HTTP响应
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.__aenter__.return_value = mock_response
        mock_response.__aexit__.return_value = None
        mock_request.return_value = mock_response
        
        config = {
            'url': 'https://example.com/webhook',
            'method': 'POST',
            'timeout': 10
        }
        
        alerter = HTTPAlerter('test-alerter', config)
        
        # 创建测试告警消息
        message = AlertMessage(
            service_name='test-service',
            service_type='redis',
            status='DOWN',
            timestamp=datetime.now(),
            error_message='Connection failed'
        )
        
        # 发送告警
        result = await alerter.send_alert(message)
        
        # 验证结果
        assert result is True
        
        # 强制刷新日志处理器
        for handler in alerter.logger.handlers:
            handler.flush()
        
        # 验证日志文件内容
        if os.path.exists(self.log_file):
            with open(self.log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()
                assert '开始发送告警消息' in log_content
                assert 'test-service' in log_content
                assert 'DOWN' in log_content
                assert '发送成功' in log_content
    
    def test_config_manager_logging(self):
        """测试配置管理器的日志记录"""
        # 创建临时配置文件
        config_file = os.path.join(self.temp_dir, 'test_config.yaml')
        config_content = """
global:
  log_level: INFO
  check_interval: 30

services:
  test-redis:
    type: redis
    host: localhost
    port: 6379

alerts:
  - name: test-alert
    type: http
    url: https://example.com/webhook
"""
        
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write(config_content)
        
        # 创建配置管理器
        config_manager = ConfigManager(config_file)
        
        # 验证日志记录器已创建
        assert config_manager.logger is not None
        assert 'config_manager' in config_manager.logger.name
        
        # 加载配置
        config = config_manager.load_config()
        
        # 验证配置加载成功
        assert 'services' in config
        assert 'test-redis' in config['services']
        
        # 验证日志文件内容
        with open(self.log_file, 'r', encoding='utf-8') as f:
            log_content = f.read()
            assert '开始加载配置文件' in log_content
            assert '配置验证成功' in log_content
            assert '包含 1 个服务和 1 个告警配置' in log_content
    
    def test_config_manager_reload_logging(self):
        """测试配置管理器重新加载的日志记录"""
        # 创建临时配置文件
        config_file = os.path.join(self.temp_dir, 'test_config.yaml')
        config_content = """
global:
  log_level: INFO

services:
  test-redis:
    type: redis
    host: localhost
    port: 6379
"""
        
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write(config_content)
        
        config_manager = ConfigManager(config_file)
        
        # 首次加载
        config_manager.load_config()
        
        # 修改配置文件
        updated_config = """
global:
  log_level: DEBUG

services:
  test-redis:
    type: redis
    host: localhost
    port: 6379
  test-mongo:
    type: mongodb
    host: localhost
    port: 27017
"""
        
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write(updated_config)
        
        # 重新加载配置
        config_manager.reload_config()
        
        # 强制刷新日志处理器
        for handler in config_manager.logger.handlers:
            handler.flush()
        
        # 验证日志文件内容
        if os.path.exists(self.log_file):
            with open(self.log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()
                assert '重新加载配置文件' in log_content
                assert '新增服务: test-mongo' in log_content
                assert '全局配置已修改' in log_content
    
    def test_multiple_components_logging(self):
        """测试多个组件同时使用日志系统"""
        # 创建多个组件
        redis_checker = RedisHealthChecker('redis-1', {
            'host': 'localhost',
            'port': 6379
        })
        
        mongo_checker = MongoHealthChecker('mongo-1', {
            'host': 'localhost',
            'port': 27017
        })
        
        http_alerter = HTTPAlerter('alerter-1', {
            'url': 'https://example.com/webhook',
            'method': 'POST'
        })
        
        # 验证每个组件都有独立的日志记录器
        assert redis_checker.logger.name != mongo_checker.logger.name
        assert mongo_checker.logger.name != http_alerter.logger.name
        assert redis_checker.logger.name != http_alerter.logger.name
        
        # 记录一些日志
        redis_checker.logger.info("Redis检查器测试日志")
        mongo_checker.logger.info("MongoDB检查器测试日志")
        http_alerter.logger.info("HTTP告警器测试日志")
        
        # 验证日志文件内容
        with open(self.log_file, 'r', encoding='utf-8') as f:
            log_content = f.read()
            assert 'Redis检查器测试日志' in log_content
            assert 'MongoDB检查器测试日志' in log_content
            assert 'HTTP告警器测试日志' in log_content
            assert 'checker.redis.redis-1' in log_content
            assert 'checker.mongo.mongo-1' in log_content
            assert 'alerter.http.alerter-1' in log_content