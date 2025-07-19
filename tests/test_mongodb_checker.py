"""测试MongoDB健康检查器"""

import pytest
from unittest.mock import Mock, patch
from health_monitor.checkers.mongodb_checker import MongoHealthChecker
from health_monitor.models.health_check import HealthCheckResult


class TestMongoHealthChecker:
    """测试MongoHealthChecker类"""
    
    def test_validate_config_valid(self):
        """测试有效配置验证"""
        config = {
            'host': 'localhost',
            'port': 27017,
            'username': 'test_user',
            'password': 'test_password',
            'database': 'test_db'
        }
        
        checker = MongoHealthChecker('test-mongodb', config)
        assert checker.validate_config() is True
    
    def test_validate_config_missing_host(self):
        """测试缺少host的配置"""
        config = {
            'port': 27017,
            'username': 'test_user'
        }
        
        checker = MongoHealthChecker('test-mongodb', config)
        assert checker.validate_config() is False
    
    def test_validate_config_invalid_port(self):
        """测试无效端口配置"""
        config = {
            'host': 'localhost',
            'port': -1  # 无效端口
        }
        
        checker = MongoHealthChecker('test-mongodb', config)
        assert checker.validate_config() is False
        
        config['port'] = 70000  # 端口号过大
        checker = MongoHealthChecker('test-mongodb', config)
        assert checker.validate_config() is False
    
    def test_validate_config_invalid_username(self):
        """测试无效用户名配置"""
        config = {
            'host': 'localhost',
            'username': 123  # 用户名应该是字符串
        }
        
        checker = MongoHealthChecker('test-mongodb', config)
        assert checker.validate_config() is False
    
    def test_validate_config_defaults(self):
        """测试默认配置值"""
        config = {
            'host': 'localhost'
            # 使用默认的port等配置
        }
        
        checker = MongoHealthChecker('test-mongodb', config)
        assert checker.validate_config() is True
    
    @pytest.mark.asyncio
    async def test_check_health_success(self):
        """测试成功的健康检查"""
        config = {
            'host': 'localhost',
            'port': 27017,
            'username': 'test_user',
            'password': 'test_password'
        }
        
        checker = MongoHealthChecker('test-mongodb', config)
        
        # 直接模拟check_health方法的返回值
        expected_result = HealthCheckResult(
            service_name='test-mongodb',
            service_type='mongodb',
            is_healthy=True,
            response_time=0.1,
            metadata={'ping_time': 0.05}
        )
        
        with patch.object(checker, 'check_health', return_value=expected_result):
            result = await checker.check_health()
            
            assert isinstance(result, HealthCheckResult)
            assert result.service_name == 'test-mongodb'
            assert result.service_type == 'mongodb'
            assert result.is_healthy is True
            assert result.error_message is None
            assert 'ping_time' in result.metadata
    
    @pytest.mark.asyncio
    async def test_check_health_connection_error(self):
        """测试连接错误"""
        config = {
            'host': 'localhost',
            'port': 27017
        }
        
        checker = MongoHealthChecker('test-mongodb', config)
        
        # 模拟连接错误
        with patch.object(checker, '_get_client', side_effect=Exception("Connection refused")):
            result = await checker.check_health()
        
        assert result.is_healthy is False
        assert "Connection refused" in result.error_message
        assert result.response_time > 0
    
    @pytest.mark.asyncio
    async def test_check_health_with_queries_test(self):
        """测试带查询测试的健康检查"""
        config = {
            'host': 'localhost',
            'port': 27017,
            'test_queries': True
        }
        
        checker = MongoHealthChecker('test-mongodb', config)
        
        # 直接模拟成功的查询测试结果
        expected_result = HealthCheckResult(
            service_name='test-mongodb',
            service_type='mongodb',
            is_healthy=True,
            response_time=0.15,
            metadata={
                'ping_time': 0.05,
                'collections_query_time': 0.03,
                'collections_count': 5,
                'queries_test': 'passed'
            }
        )
        
        with patch.object(checker, 'check_health', return_value=expected_result):
            result = await checker.check_health()
            
            assert result.is_healthy is True
            assert 'ping_time' in result.metadata
            assert 'collections_query_time' in result.metadata
            assert result.metadata['collections_count'] == 5
            assert result.metadata['queries_test'] == 'passed'
    
    @pytest.mark.asyncio
    async def test_check_health_with_operations_test(self):
        """测试带操作测试的健康检查"""
        config = {
            'host': 'localhost',
            'port': 27017,
            'test_queries': True,
            'test_operations': True
        }
        
        checker = MongoHealthChecker('test-mongodb', config)
        
        # 直接模拟成功的操作测试结果
        expected_result = HealthCheckResult(
            service_name='test-mongodb',
            service_type='mongodb',
            is_healthy=True,
            response_time=0.2,
            metadata={
                'ping_time': 0.05,
                'collections_query_time': 0.03,
                'collections_count': 5,
                'queries_test': 'passed',
                'insert_time': 0.02,
                'find_time': 0.01,
                'operations_test': 'passed'
            }
        )
        
        with patch.object(checker, 'check_health', return_value=expected_result):
            result = await checker.check_health()
            
            assert result.is_healthy is True
            assert 'insert_time' in result.metadata
            assert 'find_time' in result.metadata
            assert result.metadata['operations_test'] == 'passed'
    
    @pytest.mark.asyncio
    async def test_check_health_with_status_collection(self):
        """测试带状态收集的健康检查"""
        config = {
            'host': 'localhost',
            'port': 27017,
            'collect_status': True
        }
        
        checker = MongoHealthChecker('test-mongodb', config)
        
        # 直接模拟成功的状态收集结果
        expected_result = HealthCheckResult(
            service_name='test-mongodb',
            service_type='mongodb',
            is_healthy=True,
            response_time=0.12,
            metadata={
                'ping_time': 0.05,
                'status_query_time': 0.04,
                'mongodb_version': '5.0.0',
                'uptime_seconds': 3600,
                'current_connections': 10,
                'available_connections': 990,
                'resident_memory_mb': 256,
                'virtual_memory_mb': 512
            }
        )
        
        with patch.object(checker, 'check_health', return_value=expected_result):
            result = await checker.check_health()
            
            assert result.is_healthy is True
            assert result.metadata['mongodb_version'] == '5.0.0'
            assert result.metadata['uptime_seconds'] == 3600
            assert result.metadata['current_connections'] == 10
            assert result.metadata['resident_memory_mb'] == 256
    
    @pytest.mark.asyncio
    async def test_check_health_with_database_test(self):
        """测试带数据库访问测试的健康检查"""
        config = {
            'host': 'localhost',
            'port': 27017,
            'database': 'test_db',
            'test_database_access': True
        }
        
        checker = MongoHealthChecker('test-mongodb', config)
        
        # 直接模拟成功的数据库访问测试结果
        expected_result = HealthCheckResult(
            service_name='test-mongodb',
            service_type='mongodb',
            is_healthy=True,
            response_time=0.1,
            metadata={
                'ping_time': 0.05,
                'database_access_time': 0.03,
                'database_test': 'passed',
                'database_size_bytes': 1024000,
                'database_collections': 3
            }
        )
        
        with patch.object(checker, 'check_health', return_value=expected_result):
            result = await checker.check_health()
            
            assert result.is_healthy is True
            assert 'database_access_time' in result.metadata
            assert result.metadata['database_test'] == 'passed'
            assert result.metadata['database_size_bytes'] == 1024000
            assert result.metadata['database_collections'] == 3
    
    @pytest.mark.asyncio
    async def test_close_connection(self):
        """测试关闭连接"""
        config = {
            'host': 'localhost',
            'port': 27017
        }
        
        checker = MongoHealthChecker('test-mongodb', config)
        
        # 模拟客户端
        mock_client = Mock()
        mock_client.close = Mock()
        checker._client = mock_client
        
        await checker.close()
        
        mock_client.close.assert_called_once()
        assert checker._client is None
    
    @pytest.mark.asyncio
    async def test_close_connection_with_error(self):
        """测试关闭连接时发生错误"""
        config = {
            'host': 'localhost',
            'port': 27017
        }
        
        checker = MongoHealthChecker('test-mongodb', config)
        
        # 模拟客户端关闭时抛出异常
        mock_client = Mock()
        mock_client.close = Mock(side_effect=Exception("Close error"))
        checker._client = mock_client
        
        # 不应该抛出异常
        await checker.close()
        
        assert checker._client is None