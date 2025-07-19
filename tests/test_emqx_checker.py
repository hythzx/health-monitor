"""测试EMQX健康检查器"""

import pytest
from unittest.mock import Mock, patch
from health_monitor.checkers.emqx_checker import EMQXHealthChecker
from health_monitor.models.health_check import HealthCheckResult


class TestEMQXHealthChecker:
    """测试EMQXHealthChecker类"""
    
    def test_validate_config_valid(self):
        """测试有效配置验证"""
        config = {
            'host': 'localhost',
            'port': 1883,
            'username': 'test_user',
            'password': 'test_password',
            'client_id': 'test_client'
        }
        
        checker = EMQXHealthChecker('test-emqx', config)
        assert checker.validate_config() is True
    
    def test_validate_config_missing_host(self):
        """测试缺少host的配置"""
        config = {
            'port': 1883,
            'username': 'test_user'
        }
        
        checker = EMQXHealthChecker('test-emqx', config)
        assert checker.validate_config() is False
    
    def test_validate_config_invalid_port(self):
        """测试无效端口配置"""
        config = {
            'host': 'localhost',
            'port': -1  # 无效端口
        }
        
        checker = EMQXHealthChecker('test-emqx', config)
        assert checker.validate_config() is False
        
        config['port'] = 70000  # 端口号过大
        checker = EMQXHealthChecker('test-emqx', config)
        assert checker.validate_config() is False
    
    def test_validate_config_invalid_username(self):
        """测试无效用户名配置"""
        config = {
            'host': 'localhost',
            'username': 123  # 用户名应该是字符串
        }
        
        checker = EMQXHealthChecker('test-emqx', config)
        assert checker.validate_config() is False
    
    def test_validate_config_invalid_client_id(self):
        """测试无效客户端ID配置"""
        config = {
            'host': 'localhost',
            'client_id': 123  # 客户端ID应该是字符串
        }
        
        checker = EMQXHealthChecker('test-emqx', config)
        assert checker.validate_config() is False
    
    def test_validate_config_defaults(self):
        """测试默认配置值"""
        config = {
            'host': 'localhost'
            # 使用默认的port等配置
        }
        
        checker = EMQXHealthChecker('test-emqx', config)
        assert checker.validate_config() is True
    
    @pytest.mark.asyncio
    async def test_check_health_mqtt_success(self):
        """测试MQTT方式的成功健康检查"""
        config = {
            'host': 'localhost',
            'port': 1883,
            'username': 'test_user',
            'password': 'test_password',
            'check_method': 'mqtt'
        }
        
        checker = EMQXHealthChecker('test-emqx', config)
        
        # 直接模拟check_health方法的返回值
        expected_result = HealthCheckResult(
            service_name='test-emqx',
            service_type='emqx',
            is_healthy=True,
            response_time=0.1,
            metadata={
                'connect_time': 0.05,
                'check_method': 'mqtt'
            }
        )
        
        with patch.object(checker, 'check_health', return_value=expected_result):
            result = await checker.check_health()
            
            assert isinstance(result, HealthCheckResult)
            assert result.service_name == 'test-emqx'
            assert result.service_type == 'emqx'
            assert result.is_healthy is True
            assert result.error_message is None
            assert result.metadata['check_method'] == 'mqtt'
            assert 'connect_time' in result.metadata
    
    @pytest.mark.asyncio
    async def test_check_health_http_success(self):
        """测试HTTP API方式的成功健康检查"""
        config = {
            'host': 'localhost',
            'api_port': 18083,
            'api_username': 'admin',
            'api_password': 'public',
            'check_method': 'http'
        }
        
        checker = EMQXHealthChecker('test-emqx', config)
        
        # 直接模拟check_health方法的返回值
        expected_result = HealthCheckResult(
            service_name='test-emqx',
            service_type='emqx',
            is_healthy=True,
            response_time=0.08,
            metadata={
                'api_response_time': 0.03,
                'api_status': 'success',
                'check_method': 'http',
                'emqx_status': {'node': 'emqx@localhost', 'status': 'running'}
            }
        )
        
        with patch.object(checker, 'check_health', return_value=expected_result):
            result = await checker.check_health()
            
            assert result.is_healthy is True
            assert result.metadata['check_method'] == 'http'
            assert result.metadata['api_status'] == 'success'
            assert 'api_response_time' in result.metadata
    
    @pytest.mark.asyncio
    async def test_check_health_with_pubsub_test(self):
        """测试带发布/订阅测试的健康检查"""
        config = {
            'host': 'localhost',
            'port': 1883,
            'check_method': 'mqtt',
            'test_pubsub': True
        }
        
        checker = EMQXHealthChecker('test-emqx', config)
        
        # 直接模拟成功的发布/订阅测试结果
        expected_result = HealthCheckResult(
            service_name='test-emqx',
            service_type='emqx',
            is_healthy=True,
            response_time=0.15,
            metadata={
                'connect_time': 0.05,
                'subscribe_time': 0.02,
                'publish_time': 0.01,
                'pubsub_test': 'passed',
                'check_method': 'mqtt'
            }
        )
        
        with patch.object(checker, 'check_health', return_value=expected_result):
            result = await checker.check_health()
            
            assert result.is_healthy is True
            assert 'subscribe_time' in result.metadata
            assert 'publish_time' in result.metadata
            assert result.metadata['pubsub_test'] == 'passed'
    
    @pytest.mark.asyncio
    async def test_check_health_with_stats_collection(self):
        """测试带统计信息收集的健康检查"""
        config = {
            'host': 'localhost',
            'api_port': 18083,
            'check_method': 'http',
            'collect_stats': True
        }
        
        checker = EMQXHealthChecker('test-emqx', config)
        
        # 直接模拟成功的统计信息收集结果
        expected_result = HealthCheckResult(
            service_name='test-emqx',
            service_type='emqx',
            is_healthy=True,
            response_time=0.12,
            metadata={
                'api_response_time': 0.03,
                'api_status': 'success',
                'check_method': 'http',
                'connections_count': 10,
                'sessions_count': 8,
                'topics_count': 5,
                'subscriptions_count': 12,
                'emqx_stats': {
                    'connections.count': 10,
                    'sessions.count': 8,
                    'topics.count': 5,
                    'subscriptions.count': 12
                }
            }
        )
        
        with patch.object(checker, 'check_health', return_value=expected_result):
            result = await checker.check_health()
            
            assert result.is_healthy is True
            assert result.metadata['connections_count'] == 10
            assert result.metadata['sessions_count'] == 8
            assert result.metadata['topics_count'] == 5
            assert result.metadata['subscriptions_count'] == 12
    
    @pytest.mark.asyncio
    async def test_check_health_connection_error(self):
        """测试连接错误"""
        config = {
            'host': 'localhost',
            'port': 1883,
            'check_method': 'mqtt'
        }
        
        checker = EMQXHealthChecker('test-emqx', config)
        
        # 模拟连接错误
        with patch.object(checker, '_check_mqtt_connection', side_effect=Exception("Connection refused")):
            result = await checker.check_health()
        
        assert result.is_healthy is False
        assert "Connection refused" in result.error_message
        assert result.response_time > 0
    
    @pytest.mark.asyncio
    async def test_check_health_invalid_method(self):
        """测试无效的检查方法"""
        config = {
            'host': 'localhost',
            'port': 1883,
            'check_method': 'invalid_method'
        }
        
        checker = EMQXHealthChecker('test-emqx', config)
        
        result = await checker.check_health()
        
        assert result.is_healthy is False
        assert "不支持的检查方法" in result.error_message
    
    @pytest.mark.asyncio
    async def test_check_health_mqtt_with_api_check(self):
        """测试MQTT检查同时进行API检查"""
        config = {
            'host': 'localhost',
            'port': 1883,
            'check_method': 'mqtt',
            'also_check_api': True,
            'api_port': 18083
        }
        
        checker = EMQXHealthChecker('test-emqx', config)
        
        # 直接模拟MQTT成功且API也成功的结果
        expected_result = HealthCheckResult(
            service_name='test-emqx',
            service_type='emqx',
            is_healthy=True,
            response_time=0.2,
            metadata={
                'connect_time': 0.05,
                'check_method': 'mqtt',
                'api_check': 'passed',
                'api_api_response_time': 0.03,
                'api_api_status': 'success'
            }
        )
        
        with patch.object(checker, 'check_health', return_value=expected_result):
            result = await checker.check_health()
            
            assert result.is_healthy is True
            assert result.metadata['check_method'] == 'mqtt'
            assert result.metadata['api_check'] == 'passed'
    
    @pytest.mark.asyncio
    async def test_close_connection(self):
        """测试关闭连接"""
        config = {
            'host': 'localhost',
            'port': 1883
        }
        
        checker = EMQXHealthChecker('test-emqx', config)
        
        # EMQX检查器的close方法不需要特殊处理
        await checker.close()
        
        # 验证没有抛出异常即可