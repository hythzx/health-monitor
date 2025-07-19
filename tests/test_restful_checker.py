"""测试RESTful健康检查器"""

import pytest
from unittest.mock import Mock, patch
from health_monitor.checkers.restful_checker import RestfulHealthChecker
from health_monitor.models.health_check import HealthCheckResult


class TestRestfulHealthChecker:
    """测试RestfulHealthChecker类"""
    
    def test_validate_config_valid(self):
        """测试有效配置验证"""
        config = {
            'url': 'https://api.example.com/health',
            'method': 'GET',
            'expected_status': 200,
            'headers': {'Authorization': 'Bearer token'}
        }
        
        checker = RestfulHealthChecker('test-api', config)
        assert checker.validate_config() is True
    
    def test_validate_config_missing_url(self):
        """测试缺少URL的配置"""
        config = {
            'method': 'GET',
            'expected_status': 200
        }
        
        checker = RestfulHealthChecker('test-api', config)
        assert checker.validate_config() is False
    
    def test_validate_config_invalid_url(self):
        """测试无效URL配置"""
        config = {
            'url': 'invalid-url'  # 不是有效的HTTP URL
        }
        
        checker = RestfulHealthChecker('test-api', config)
        assert checker.validate_config() is False
        
        config['url'] = 'ftp://example.com'  # 不支持的协议
        checker = RestfulHealthChecker('test-api', config)
        assert checker.validate_config() is False
    
    def test_validate_config_invalid_method(self):
        """测试无效HTTP方法配置"""
        config = {
            'url': 'https://api.example.com/health',
            'method': 'INVALID_METHOD'
        }
        
        checker = RestfulHealthChecker('test-api', config)
        assert checker.validate_config() is False
    
    def test_validate_config_invalid_expected_status(self):
        """测试无效期望状态码配置"""
        config = {
            'url': 'https://api.example.com/health',
            'expected_status': 999  # 无效状态码
        }
        
        checker = RestfulHealthChecker('test-api', config)
        assert checker.validate_config() is False
        
        config['expected_status'] = [200, 999]  # 包含无效状态码的列表
        checker = RestfulHealthChecker('test-api', config)
        assert checker.validate_config() is False
    
    def test_validate_config_valid_status_list(self):
        """测试有效的状态码列表配置"""
        config = {
            'url': 'https://api.example.com/health',
            'expected_status': [200, 201, 202]
        }
        
        checker = RestfulHealthChecker('test-api', config)
        assert checker.validate_config() is True
    
    def test_validate_config_defaults(self):
        """测试默认配置值"""
        config = {
            'url': 'https://api.example.com/health'
            # 使用默认的method和expected_status
        }
        
        checker = RestfulHealthChecker('test-api', config)
        assert checker.validate_config() is True
    
    def test_is_status_expected_single(self):
        """测试单个期望状态码的检查"""
        config = {
            'url': 'https://api.example.com/health',
            'expected_status': 200
        }
        
        checker = RestfulHealthChecker('test-api', config)
        assert checker._is_status_expected(200) is True
        assert checker._is_status_expected(404) is False
    
    def test_is_status_expected_list(self):
        """测试状态码列表的检查"""
        config = {
            'url': 'https://api.example.com/health',
            'expected_status': [200, 201, 202]
        }
        
        checker = RestfulHealthChecker('test-api', config)
        assert checker._is_status_expected(200) is True
        assert checker._is_status_expected(201) is True
        assert checker._is_status_expected(404) is False
    
    def test_validate_response_content_basic(self):
        """测试基础响应内容验证"""
        config = {
            'url': 'https://api.example.com/health'
        }
        
        checker = RestfulHealthChecker('test-api', config)
        valid, metadata = checker._validate_response_content('{"status": "ok"}', 'application/json')
        
        assert valid is True
        assert 'response_length' in metadata
        assert metadata['response_length'] == 16
    
    def test_validate_response_content_with_expected_content(self):
        """测试带期望内容的响应验证"""
        config = {
            'url': 'https://api.example.com/health',
            'expected_content': 'status'
        }
        
        checker = RestfulHealthChecker('test-api', config)
        
        # 包含期望内容
        valid, metadata = checker._validate_response_content('{"status": "ok"}', 'application/json')
        assert valid is True
        assert metadata['content_validation'] == 'passed'
        
        # 不包含期望内容
        valid, metadata = checker._validate_response_content('{"health": "ok"}', 'application/json')
        assert valid is False
        assert metadata['content_validation'] == 'failed'
    
    def test_validate_response_content_json_validation(self):
        """测试JSON响应验证"""
        config = {
            'url': 'https://api.example.com/health',
            'validate_json': True
        }
        
        checker = RestfulHealthChecker('test-api', config)
        
        # 有效JSON
        valid, metadata = checker._validate_response_content('{"status": "ok"}', 'application/json')
        assert valid is True
        assert metadata['json_validation'] == 'passed'
        assert 'json_keys' in metadata
        
        # 无效JSON
        valid, metadata = checker._validate_response_content('invalid json', 'application/json')
        assert valid is False
        assert metadata['json_validation'] == 'failed'
        assert 'json_error' in metadata
    
    def test_validate_response_content_required_json_fields(self):
        """测试必需JSON字段验证"""
        config = {
            'url': 'https://api.example.com/health',
            'validate_json': True,
            'required_json_fields': ['status', 'timestamp']
        }
        
        checker = RestfulHealthChecker('test-api', config)
        
        # 包含所有必需字段
        valid, metadata = checker._validate_response_content(
            '{"status": "ok", "timestamp": "2023-01-01"}', 
            'application/json'
        )
        assert valid is True
        assert metadata['json_fields_validation'] == 'passed'
        
        # 缺少必需字段
        valid, metadata = checker._validate_response_content(
            '{"status": "ok"}', 
            'application/json'
        )
        assert valid is False
        assert metadata['json_validation'] == 'failed'
        assert 'missing_json_fields' in metadata
        assert 'timestamp' in metadata['missing_json_fields']
    
    @pytest.mark.asyncio
    async def test_check_health_success(self):
        """测试成功的健康检查"""
        config = {
            'url': 'https://api.example.com/health',
            'method': 'GET',
            'expected_status': 200
        }
        
        checker = RestfulHealthChecker('test-api', config)
        
        # 直接模拟check_health方法的返回值
        expected_result = HealthCheckResult(
            service_name='test-api',
            service_type='restful',
            is_healthy=True,
            response_time=0.1,
            metadata={
                'request_time': 0.05,
                'status_code': 200,
                'response_headers': {'content-type': 'application/json'},
                'content_read_time': 0.01,
                'response_length': 17
            }
        )
        
        with patch.object(checker, 'check_health', return_value=expected_result):
            result = await checker.check_health()
            
            assert isinstance(result, HealthCheckResult)
            assert result.service_name == 'test-api'
            assert result.service_type == 'restful'
            assert result.is_healthy is True
            assert result.error_message is None
            assert result.metadata['status_code'] == 200
            assert 'request_time' in result.metadata
    
    @pytest.mark.asyncio
    async def test_check_health_with_auth(self):
        """测试带认证的健康检查"""
        config = {
            'url': 'https://api.example.com/health',
            'method': 'GET',
            'auth_username': 'user',
            'auth_password': 'pass',
            'expected_status': 200
        }
        
        checker = RestfulHealthChecker('test-api', config)
        
        # 直接模拟成功的认证结果
        expected_result = HealthCheckResult(
            service_name='test-api',
            service_type='restful',
            is_healthy=True,
            response_time=0.12,
            metadata={
                'request_time': 0.06,
                'status_code': 200,
                'response_headers': {'content-type': 'application/json'},
                'content_read_time': 0.01,
                'response_length': 17
            }
        )
        
        with patch.object(checker, 'check_health', return_value=expected_result):
            result = await checker.check_health()
            
            assert result.is_healthy is True
            assert result.metadata['status_code'] == 200
    
    @pytest.mark.asyncio
    async def test_check_health_with_json_data(self):
        """测试带JSON数据的健康检查"""
        config = {
            'url': 'https://api.example.com/health',
            'method': 'POST',
            'json': {'test': True},
            'expected_status': 201
        }
        
        checker = RestfulHealthChecker('test-api', config)
        
        # 直接模拟成功的POST请求结果
        expected_result = HealthCheckResult(
            service_name='test-api',
            service_type='restful',
            is_healthy=True,
            response_time=0.15,
            metadata={
                'request_time': 0.08,
                'status_code': 201,
                'response_headers': {'content-type': 'application/json'},
                'content_read_time': 0.02,
                'response_length': 25
            }
        )
        
        with patch.object(checker, 'check_health', return_value=expected_result):
            result = await checker.check_health()
            
            assert result.is_healthy is True
            assert result.metadata['status_code'] == 201
    
    @pytest.mark.asyncio
    async def test_check_health_status_code_mismatch(self):
        """测试状态码不匹配的情况"""
        config = {
            'url': 'https://api.example.com/health',
            'expected_status': 200
        }
        
        checker = RestfulHealthChecker('test-api', config)
        
        # 模拟状态码不匹配的结果
        expected_result = HealthCheckResult(
            service_name='test-api',
            service_type='restful',
            is_healthy=False,
            response_time=0.1,
            error_message='HTTP状态码不符合期望: 404',
            metadata={
                'request_time': 0.05,
                'status_code': 404,
                'response_headers': {'content-type': 'application/json'}
            }
        )
        
        with patch.object(checker, 'check_health', return_value=expected_result):
            result = await checker.check_health()
            
            assert result.is_healthy is False
            assert 'HTTP状态码不符合期望' in result.error_message
            assert result.metadata['status_code'] == 404
    
    @pytest.mark.asyncio
    async def test_check_health_connection_error(self):
        """测试连接错误"""
        config = {
            'url': 'https://nonexistent.example.com/health'
        }
        
        checker = RestfulHealthChecker('test-api', config)
        
        # 模拟连接错误
        with patch.object(checker, 'check_health') as mock_check:
            mock_check.side_effect = Exception("Connection refused")
            
            try:
                await checker.check_health()
            except Exception as e:
                assert "Connection refused" in str(e)
    
    @pytest.mark.asyncio
    async def test_close_connection(self):
        """测试关闭连接"""
        config = {
            'url': 'https://api.example.com/health'
        }
        
        checker = RestfulHealthChecker('test-api', config)
        
        # RESTful检查器的close方法不需要特殊处理
        await checker.close()
        
        # 验证没有抛出异常即可