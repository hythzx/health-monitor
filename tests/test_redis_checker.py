"""测试Redis健康检查器"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from health_monitor.checkers.redis_checker import RedisHealthChecker
from health_monitor.models.health_check import HealthCheckResult


class TestRedisHealthChecker:
    """测试RedisHealthChecker类"""
    
    def test_validate_config_valid(self):
        """测试有效配置验证"""
        config = {
            'host': 'localhost',
            'port': 6379,
            'database': 0,
            'password': 'test_password'
        }
        
        checker = RedisHealthChecker('test-redis', config)
        assert checker.validate_config() is True
    
    def test_validate_config_missing_host(self):
        """测试缺少host的配置"""
        config = {
            'port': 6379,
            'database': 0
        }
        
        checker = RedisHealthChecker('test-redis', config)
        assert checker.validate_config() is False
    
    def test_validate_config_invalid_port(self):
        """测试无效端口配置"""
        config = {
            'host': 'localhost',
            'port': -1  # 无效端口
        }
        
        checker = RedisHealthChecker('test-redis', config)
        assert checker.validate_config() is False
        
        config['port'] = 70000  # 端口号过大
        checker = RedisHealthChecker('test-redis', config)
        assert checker.validate_config() is False
    
    def test_validate_config_invalid_database(self):
        """测试无效数据库配置"""
        config = {
            'host': 'localhost',
            'database': -1  # 无效数据库编号
        }
        
        checker = RedisHealthChecker('test-redis', config)
        assert checker.validate_config() is False
    
    def test_validate_config_defaults(self):
        """测试默认配置值"""
        config = {
            'host': 'localhost'
            # 使用默认的port和database
        }
        
        checker = RedisHealthChecker('test-redis', config)
        assert checker.validate_config() is True
    
    @pytest.mark.asyncio
    async def test_check_health_success(self):
        """测试成功的健康检查"""
        config = {
            'host': 'localhost',
            'port': 6379,
            'database': 0,
            'use_connection_pool': False  # 禁用连接池，这样会调用aclose
        }
        
        checker = RedisHealthChecker('test-redis', config)
        
        # 模拟Redis客户端
        mock_client = AsyncMock()
        mock_client.ping.return_value = True
        mock_client.aclose = AsyncMock()
        
        with patch('health_monitor.checkers.redis_checker.redis.Redis', return_value=mock_client):
            result = await checker.check_health()
        
        assert isinstance(result, HealthCheckResult)
        assert result.service_name == 'test-redis'
        assert result.service_type == 'redis'
        assert result.is_healthy is True
        assert result.error_message is None
        assert result.response_time > 0
        assert 'ping_time' in result.metadata
        
        # 验证客户端方法被调用
        mock_client.ping.assert_called_once()
        mock_client.aclose.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_check_health_with_operations_test(self):
        """测试带操作测试的健康检查"""
        config = {
            'host': 'localhost',
            'port': 6379,
            'test_operations': True
        }
        
        checker = RedisHealthChecker('test-redis', config)
        
        # 模拟Redis客户端
        mock_client = AsyncMock()
        mock_client.ping.return_value = True
        mock_client.set = AsyncMock()
        mock_client.get.return_value = "health_check_value"
        mock_client.delete = AsyncMock()
        mock_client.aclose = AsyncMock()
        
        with patch('health_monitor.checkers.redis_checker.redis.Redis', return_value=mock_client):
            result = await checker.check_health()
        
        assert result.is_healthy is True
        assert 'ping_time' in result.metadata
        assert 'set_time' in result.metadata
        assert 'get_time' in result.metadata
        assert result.metadata['operations_test'] == 'passed'
        
        # 验证操作被调用
        mock_client.ping.assert_called_once()
        mock_client.set.assert_called_once()
        mock_client.get.assert_called_once()
        mock_client.delete.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_check_health_operations_test_failed(self):
        """测试操作测试失败的情况"""
        config = {
            'host': 'localhost',
            'port': 6379,
            'test_operations': True
        }
        
        checker = RedisHealthChecker('test-redis', config)
        
        # 模拟Redis客户端
        mock_client = AsyncMock()
        mock_client.ping.return_value = True
        mock_client.set = AsyncMock()
        mock_client.get.return_value = "wrong_value"  # 返回错误的值
        mock_client.delete = AsyncMock()
        mock_client.aclose = AsyncMock()
        
        with patch('health_monitor.checkers.redis_checker.redis.Redis', return_value=mock_client):
            result = await checker.check_health()
        
        assert result.is_healthy is False
        assert result.error_message == "SET/GET操作测试失败"
        assert result.metadata['operations_test'] == 'failed'
    
    @pytest.mark.asyncio
    async def test_check_health_with_info_collection(self):
        """测试带信息收集的健康检查"""
        config = {
            'host': 'localhost',
            'port': 6379,
            'collect_info': True
        }
        
        checker = RedisHealthChecker('test-redis', config)
        
        # 模拟Redis客户端和INFO响应
        mock_info = {
            'redis_version': '6.2.0',
            'connected_clients': 5,
            'used_memory': 1024000,
            'uptime_in_seconds': 3600
        }
        
        mock_client = AsyncMock()
        mock_client.ping.return_value = True
        mock_client.info.return_value = mock_info
        mock_client.aclose = AsyncMock()
        
        with patch('health_monitor.checkers.redis_checker.redis.Redis', return_value=mock_client):
            result = await checker.check_health()
        
        assert result.is_healthy is True
        assert result.metadata['redis_version'] == '6.2.0'
        assert result.metadata['connected_clients'] == 5
        assert result.metadata['used_memory'] == 1024000
        assert result.metadata['uptime_in_seconds'] == 3600
        
        mock_client.info.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_check_health_connection_error(self):
        """测试连接错误"""
        config = {
            'host': 'localhost',
            'port': 6379
        }
        
        checker = RedisHealthChecker('test-redis', config)
        
        # 模拟连接错误
        mock_client = AsyncMock()
        mock_client.ping.side_effect = Exception("Connection refused")
        mock_client.aclose = AsyncMock()
        
        with patch('health_monitor.checkers.redis_checker.redis.Redis', return_value=mock_client):
            result = await checker.check_health()
        
        assert result.is_healthy is False
        assert "Connection refused" in result.error_message
        assert result.response_time > 0
    
    @pytest.mark.asyncio
    async def test_check_health_ping_false(self):
        """测试PING返回False的情况"""
        config = {
            'host': 'localhost',
            'port': 6379
        }
        
        checker = RedisHealthChecker('test-redis', config)
        
        # 模拟PING返回False
        mock_client = AsyncMock()
        mock_client.ping.return_value = False
        mock_client.aclose = AsyncMock()
        
        with patch('health_monitor.checkers.redis_checker.redis.Redis', return_value=mock_client):
            result = await checker.check_health()
        
        assert result.is_healthy is False
        assert result.error_message == "PING命令返回False"
    
    @pytest.mark.asyncio
    async def test_close_connection(self):
        """测试关闭连接"""
        config = {
            'host': 'localhost',
            'port': 6379
        }
        
        checker = RedisHealthChecker('test-redis', config)
        
        # 模拟客户端
        mock_client = AsyncMock()
        checker._client = mock_client
        
        await checker.close()
        
        mock_client.aclose.assert_called_once()
        assert checker._client is None
    
    @pytest.mark.asyncio
    async def test_close_connection_with_error(self):
        """测试关闭连接时发生错误"""
        config = {
            'host': 'localhost',
            'port': 6379
        }
        
        checker = RedisHealthChecker('test-redis', config)
        
        # 模拟客户端关闭时抛出异常
        mock_client = AsyncMock()
        mock_client.aclose.side_effect = Exception("Close error")
        checker._client = mock_client
        
        # 不应该抛出异常
        await checker.close()
        
        assert checker._client is None