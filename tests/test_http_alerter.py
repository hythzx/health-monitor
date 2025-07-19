"""HTTP告警器测试"""

import json
import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
from aiohttp import ClientError, ClientTimeout
from aiohttp.web import Response

from health_monitor.alerts.http_alerter import HTTPAlerter
from health_monitor.models.health_check import AlertMessage
from health_monitor.utils.exceptions import AlertConfigError, AlertSendError


class TestHTTPAlerter:
    """HTTP告警器测试类"""
    
    def setup_method(self):
        """测试前准备"""
        self.valid_config = {
            'url': 'https://api.example.com/webhook',
            'method': 'POST',
            'headers': {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer token123'
            },
            'timeout': 30,
            'max_retries': 2,
            'retry_delay': 1.0
        }
        
        self.alert_message = AlertMessage(
            service_name='test-service',
            service_type='redis',
            status='DOWN',
            timestamp=datetime(2023, 1, 1, 12, 0, 0),
            error_message='连接失败',
            response_time=1500.5,
            metadata={'old_state': True, 'new_state': False}
        )
    
    def test_init_valid_config(self):
        """测试有效配置的初始化"""
        alerter = HTTPAlerter('test-alerter', self.valid_config)
        
        assert alerter.name == 'test-alerter'
        assert alerter.url == 'https://api.example.com/webhook'
        assert alerter.method == 'POST'
        assert alerter.max_retries == 2
        assert alerter.retry_delay == 1.0
    
    def test_init_invalid_config(self):
        """测试无效配置的初始化"""
        invalid_config = {'method': 'POST'}  # 缺少URL
        
        with pytest.raises(AlertConfigError):
            HTTPAlerter('test-alerter', invalid_config)
    
    def test_validate_config_valid(self):
        """测试有效配置验证"""
        alerter = HTTPAlerter('test-alerter', self.valid_config)
        assert alerter.validate_config() is True
    
    def test_validate_config_missing_url(self):
        """测试缺少URL的配置验证"""
        config = self.valid_config.copy()
        del config['url']
        
        alerter = HTTPAlerter.__new__(HTTPAlerter)
        alerter.name = 'test'
        alerter.url = ''
        alerter.method = 'POST'
        alerter.max_retries = 3
        alerter.retry_delay = 1.0
        alerter.logger = Mock()
        
        assert alerter.validate_config() is False
    
    def test_validate_config_invalid_url(self):
        """测试无效URL的配置验证"""
        config = self.valid_config.copy()
        config['url'] = 'invalid-url'
        
        alerter = HTTPAlerter.__new__(HTTPAlerter)
        alerter.name = 'test'
        alerter.url = 'invalid-url'
        alerter.method = 'POST'
        alerter.max_retries = 3
        alerter.retry_delay = 1.0
        alerter.logger = Mock()
        
        assert alerter.validate_config() is False
    
    def test_validate_config_invalid_method(self):
        """测试无效HTTP方法的配置验证"""
        config = self.valid_config.copy()
        config['method'] = 'INVALID'
        
        alerter = HTTPAlerter.__new__(HTTPAlerter)
        alerter.name = 'test'
        alerter.url = 'https://api.example.com/webhook'
        alerter.method = 'INVALID'
        alerter.max_retries = 3
        alerter.retry_delay = 1.0
        alerter.logger = Mock()
        
        assert alerter.validate_config() is False
    
    def test_validate_config_invalid_retries(self):
        """测试无效重试次数的配置验证"""
        alerter = HTTPAlerter.__new__(HTTPAlerter)
        alerter.name = 'test'
        alerter.url = 'https://api.example.com/webhook'
        alerter.method = 'POST'
        alerter.max_retries = -1
        alerter.retry_delay = 1.0
        alerter.logger = Mock()
        
        assert alerter.validate_config() is False
    
    def test_validate_config_invalid_json_template(self):
        """测试无效JSON模板的配置验证"""
        alerter = HTTPAlerter.__new__(HTTPAlerter)
        alerter.name = 'test'
        alerter.url = 'https://api.example.com/webhook'
        alerter.method = 'POST'
        alerter.max_retries = 3
        alerter.retry_delay = 1.0
        alerter.template = '{"invalid": json}'
        alerter.logger = Mock()
        
        assert alerter.validate_config() is False
    
    def test_create_default_payload(self):
        """测试创建默认JSON负载"""
        alerter = HTTPAlerter('test-alerter', self.valid_config)
        payload = alerter._create_default_payload(self.alert_message)
        
        assert payload['service_name'] == 'test-service'
        assert payload['service_type'] == 'redis'
        assert payload['status'] == 'DOWN'
        assert payload['timestamp'] == '2023-01-01T12:00:00'
        assert payload['error_message'] == '连接失败'
        assert payload['response_time'] == 1500.5
        assert payload['metadata'] == {'old_state': True, 'new_state': False}
    
    def test_create_query_params(self):
        """测试创建查询参数"""
        alerter = HTTPAlerter('test-alerter', self.valid_config)
        params = alerter._create_query_params(self.alert_message)
        
        assert params['service_name'] == 'test-service'
        assert params['service_type'] == 'redis'
        assert params['status'] == 'DOWN'
        assert params['timestamp'] == '2023-01-01T12:00:00'
        assert params['error_message'] == '连接失败'
        assert params['response_time'] == '1500.5'
    
    def test_prepare_request_data_post_default(self):
        """测试准备POST请求数据（默认格式）"""
        alerter = HTTPAlerter('test-alerter', self.valid_config)
        request_data = alerter._prepare_request_data(self.alert_message)
        
        assert 'json' in request_data
        assert request_data['json']['service_name'] == 'test-service'
    
    def test_prepare_request_data_post_with_template(self):
        """测试准备POST请求数据（使用模板）"""
        config = self.valid_config.copy()
        config['template'] = '{"message": "服务 {{service_name}} 状态: {{status}}"}'
        
        alerter = HTTPAlerter('test-alerter', config)
        request_data = alerter._prepare_request_data(self.alert_message)
        
        assert 'json' in request_data
        assert request_data['json']['message'] == '服务 test-service 状态: DOWN'
    
    def test_prepare_request_data_post_with_text_template(self):
        """测试准备POST请求数据（文本模板）"""
        config = self.valid_config.copy()
        config['template'] = '服务 {{service_name}} 状态: {{status}}'
        
        alerter = HTTPAlerter('test-alerter', config)
        request_data = alerter._prepare_request_data(self.alert_message)
        
        assert 'data' in request_data
        assert request_data['data'] == '服务 test-service 状态: DOWN'
    
    def test_prepare_request_data_get(self):
        """测试准备GET请求数据"""
        config = self.valid_config.copy()
        config['method'] = 'GET'
        
        alerter = HTTPAlerter('test-alerter', config)
        request_data = alerter._prepare_request_data(self.alert_message)
        
        assert 'params' in request_data
        assert request_data['params']['service_name'] == 'test-service'
    
    @pytest.mark.asyncio
    async def test_send_request_success(self):
        """测试成功发送HTTP请求"""
        alerter = HTTPAlerter('test-alerter', self.valid_config)
        
        # 模拟成功的HTTP响应
        mock_response = Mock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='OK')
        
        # 创建异步上下文管理器
        mock_request_context = AsyncMock()
        mock_request_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_request_context.__aexit__ = AsyncMock(return_value=None)
        
        mock_session = Mock()
        mock_session.request = Mock(return_value=mock_request_context)
        
        with patch('aiohttp.ClientSession') as mock_client_session:
            mock_client_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_client_session.return_value.__aexit__ = AsyncMock(return_value=None)
            
            result = await alerter._send_request(self.alert_message)
            
            assert result is True
            mock_session.request.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_request_http_error(self):
        """测试HTTP错误响应"""
        alerter = HTTPAlerter('test-alerter', self.valid_config)
        
        # 模拟HTTP错误响应
        mock_response = Mock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value='Internal Server Error')
        
        # 创建异步上下文管理器
        mock_request_context = AsyncMock()
        mock_request_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_request_context.__aexit__ = AsyncMock(return_value=None)
        
        mock_session = Mock()
        mock_session.request = Mock(return_value=mock_request_context)
        
        with patch('aiohttp.ClientSession') as mock_client_session:
            mock_client_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_client_session.return_value.__aexit__ = AsyncMock(return_value=None)
            
            result = await alerter._send_request(self.alert_message)
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_send_request_network_error(self):
        """测试网络错误"""
        alerter = HTTPAlerter('test-alerter', self.valid_config)
        
        mock_session = Mock()
        mock_session.request = Mock(side_effect=ClientError("网络错误"))
        
        with patch('aiohttp.ClientSession') as mock_client_session:
            mock_client_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_client_session.return_value.__aexit__ = AsyncMock(return_value=None)
            
            with pytest.raises(AlertSendError):
                await alerter._send_request(self.alert_message)
    
    @pytest.mark.asyncio
    async def test_send_alert_success_first_try(self):
        """测试第一次尝试就成功发送告警"""
        alerter = HTTPAlerter('test-alerter', self.valid_config)
        
        with patch.object(alerter, '_send_request', return_value=True) as mock_send:
            result = await alerter.send_alert(self.alert_message)
            
            assert result is True
            mock_send.assert_called_once_with(self.alert_message)
    
    @pytest.mark.asyncio
    async def test_send_alert_success_after_retry(self):
        """测试重试后成功发送告警"""
        alerter = HTTPAlerter('test-alerter', self.valid_config)
        
        # 第一次抛出异常，第二次成功
        with patch.object(alerter, '_send_request', side_effect=[Exception("发送失败"), True]) as mock_send:
            with patch('asyncio.sleep') as mock_sleep:
                result = await alerter.send_alert(self.alert_message)
                
                assert result is True
                assert mock_send.call_count == 2
                mock_sleep.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_alert_all_retries_failed(self):
        """测试所有重试都失败"""
        config = self.valid_config.copy()
        config['max_retries'] = 1
        alerter = HTTPAlerter('test-alerter', config)
        
        # 所有尝试都抛出异常
        with patch.object(alerter, '_send_request', side_effect=Exception("发送失败")):
            with patch('asyncio.sleep'):
                with pytest.raises(AlertSendError):
                    await alerter.send_alert(self.alert_message)
    
    @pytest.mark.asyncio
    async def test_send_alert_exponential_backoff(self):
        """测试指数退避重试"""
        config = self.valid_config.copy()
        config['max_retries'] = 2
        config['retry_delay'] = 1.0
        config['retry_backoff'] = 2.0
        alerter = HTTPAlerter('test-alerter', config)
        
        with patch.object(alerter, '_send_request', side_effect=Exception("发送失败")):
            with patch('asyncio.sleep') as mock_sleep:
                with pytest.raises(AlertSendError):
                    await alerter.send_alert(self.alert_message)
                
                # 验证退避延迟：第一次1秒，第二次2秒
                expected_delays = [1.0, 2.0]
                actual_delays = [call[0][0] for call in mock_sleep.call_args_list]
                assert actual_delays == expected_delays
    
    def test_get_config_summary(self):
        """测试获取配置摘要"""
        alerter = HTTPAlerter('test-alerter', self.valid_config)
        summary = alerter.get_config_summary()
        
        assert summary['name'] == 'test-alerter'
        assert summary['type'] == 'http'
        assert summary['url'] == 'https://api.example.com/webhook'
        assert summary['method'] == 'POST'
        assert summary['timeout'] == 30
        assert summary['max_retries'] == 2
        assert summary['headers_count'] == 2
        assert summary['has_template'] is False
    
    def test_get_config_summary_with_template(self):
        """测试包含模板的配置摘要"""
        config = self.valid_config.copy()
        config['template'] = '{"message": "{{service_name}}"}'
        
        alerter = HTTPAlerter('test-alerter', config)
        summary = alerter.get_config_summary()
        
        assert summary['has_template'] is True