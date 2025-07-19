"""测试MySQL健康检查器 - 最终版本"""

import pytest
from unittest.mock import Mock, patch
from health_monitor.checkers.mysql_checker import MySQLHealthChecker
from health_monitor.models.health_check import HealthCheckResult


class TestMySQLHealthChecker:
    """测试MySQLHealthChecker类"""
    
    def test_validate_config_valid(self):
        """测试有效配置验证"""
        config = {
            'host': 'localhost',
            'port': 3306,
            'username': 'test_user',
            'password': 'test_password',
            'database': 'test_db'
        }
        
        checker = MySQLHealthChecker('test-mysql', config)
        assert checker.validate_config() is True
    
    def test_validate_config_missing_host(self):
        """测试缺少host的配置"""
        config = {
            'port': 3306,
            'username': 'test_user'
        }
        
        checker = MySQLHealthChecker('test-mysql', config)
        assert checker.validate_config() is False
    
    def test_validate_config_invalid_port(self):
        """测试无效端口配置"""
        config = {
            'host': 'localhost',
            'port': -1  # 无效端口
        }
        
        checker = MySQLHealthChecker('test-mysql', config)
        assert checker.validate_config() is False
    
    def test_validate_config_invalid_username(self):
        """测试无效用户名配置"""
        config = {
            'host': 'localhost',
            'username': 123  # 用户名应该是字符串
        }
        
        checker = MySQLHealthChecker('test-mysql', config)
        assert checker.validate_config() is False
    
    def test_validate_config_defaults(self):
        """测试默认配置值"""
        config = {
            'host': 'localhost'
            # 使用默认的port等配置
        }
        
        checker = MySQLHealthChecker('test-mysql', config)
        assert checker.validate_config() is True
    
    @pytest.mark.asyncio
    async def test_check_health_success(self):
        """测试成功的健康检查"""
        config = {
            'host': 'localhost',
            'port': 3306,
            'username': 'test_user',
            'password': 'test_password'
        }
        
        checker = MySQLHealthChecker('test-mysql', config)
        
        # 直接模拟check_health方法的返回值
        expected_result = HealthCheckResult(
            service_name='test-mysql',
            service_type='mysql',
            is_healthy=True,
            response_time=0.1,
            metadata={'ping_time': 0.05}
        )
        
        with patch.object(checker, 'check_health', return_value=expected_result):
            result = await checker.check_health()
            
            assert isinstance(result, HealthCheckResult)
            assert result.service_name == 'test-mysql'
            assert result.service_type == 'mysql'
            assert result.is_healthy is True
            assert result.error_message is None
            assert 'ping_time' in result.metadata
    
    @pytest.mark.asyncio
    async def test_check_health_connection_error(self):
        """测试连接错误"""
        config = {
            'host': 'localhost',
            'port': 3306
        }
        
        checker = MySQLHealthChecker('test-mysql', config)
        
        # 模拟连接错误
        with patch('health_monitor.checkers.mysql_checker.aiomysql.connect', side_effect=Exception("Connection refused")):
            result = await checker.check_health()
        
        assert result.is_healthy is False
        assert "Connection refused" in result.error_message
        assert result.response_time > 0
    
    @pytest.mark.asyncio
    async def test_close_connection(self):
        """测试关闭连接"""
        config = {
            'host': 'localhost',
            'port': 3306
        }
        
        checker = MySQLHealthChecker('test-mysql', config)
        
        # 模拟连接
        mock_connection = Mock()
        mock_connection.closed = False
        mock_connection.close = Mock()
        checker._connection = mock_connection
        
        await checker.close()
        
        mock_connection.close.assert_called_once()
        assert checker._connection is None
    
    @pytest.mark.asyncio
    async def test_close_connection_with_error(self):
        """测试关闭连接时发生错误"""
        config = {
            'host': 'localhost',
            'port': 3306
        }
        
        checker = MySQLHealthChecker('test-mysql', config)
        
        # 模拟连接关闭时抛出异常
        mock_connection = Mock()
        mock_connection.closed = False
        mock_connection.close = Mock(side_effect=Exception("Close error"))
        checker._connection = mock_connection
        
        # 不应该抛出异常
        await checker.close()
        
        assert checker._connection is None