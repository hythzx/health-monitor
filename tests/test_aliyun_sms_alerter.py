"""阿里云短信告警器测试"""

import pytest
import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

from health_monitor.alerts.aliyun_sms_alerter import AliyunSMSAlerter
from health_monitor.models.health_check import AlertMessage
from health_monitor.utils.exceptions import AlertConfigError, AlertSendError


class TestAliyunSMSAlerter:
    """阿里云短信告警器测试类"""

    def test_init_valid_config(self):
        """测试有效配置的初始化"""
        config = {
            'access_key_id': 'test_key_id',
            'access_key_secret': 'test_key_secret',
            'region': 'cn-hangzhou',
            'sign_name': '测试签名',
            'template_code': 'SMS_123456789',
            'phone_numbers': ['13800138000', '13900139000'],
            'template_params': {
                'service': '{{service_name}}',
                'status': '{{status}}'
            }
        }
        
        with patch('health_monitor.alerts.aliyun_sms_alerter.DysmsapiClient'):
            alerter = AliyunSMSAlerter('test-sms', config)
            
            assert alerter.name == 'test-sms'
            assert alerter.access_key_id == 'test_key_id'
            assert alerter.access_key_secret == 'test_key_secret'
            assert alerter.region == 'cn-hangzhou'
            assert alerter.sign_name == '测试签名'
            assert alerter.template_code == 'SMS_123456789'
            assert alerter.phone_numbers == ['13800138000', '13900139000']

    def test_init_invalid_config_missing_access_key_id(self):
        """测试缺少access_key_id配置"""
        config = {
            'access_key_secret': 'test_key_secret',
            'sign_name': '测试签名',
            'template_code': 'SMS_123456789',
            'phone_numbers': ['13800138000']
        }
        
        with patch('health_monitor.alerts.aliyun_sms_alerter.DysmsapiClient'):
            with pytest.raises(AlertConfigError):
                AliyunSMSAlerter('test-sms', config)

    def test_init_invalid_config_missing_access_key_secret(self):
        """测试缺少access_key_secret配置"""
        config = {
            'access_key_id': 'test_key_id',
            'sign_name': '测试签名',
            'template_code': 'SMS_123456789',
            'phone_numbers': ['13800138000']
        }
        
        with patch('health_monitor.alerts.aliyun_sms_alerter.DysmsapiClient'):
            with pytest.raises(AlertConfigError):
                AliyunSMSAlerter('test-sms', config)

    def test_init_invalid_config_missing_sign_name(self):
        """测试缺少sign_name配置"""
        config = {
            'access_key_id': 'test_key_id',
            'access_key_secret': 'test_key_secret',
            'template_code': 'SMS_123456789',
            'phone_numbers': ['13800138000']
        }
        
        with patch('health_monitor.alerts.aliyun_sms_alerter.DysmsapiClient'):
            with pytest.raises(AlertConfigError):
                AliyunSMSAlerter('test-sms', config)

    def test_init_invalid_config_missing_template_code(self):
        """测试缺少template_code配置"""
        config = {
            'access_key_id': 'test_key_id',
            'access_key_secret': 'test_key_secret',
            'sign_name': '测试签名',
            'phone_numbers': ['13800138000']
        }
        
        with patch('health_monitor.alerts.aliyun_sms_alerter.DysmsapiClient'):
            with pytest.raises(AlertConfigError):
                AliyunSMSAlerter('test-sms', config)

    def test_init_invalid_config_missing_phone_numbers(self):
        """测试缺少phone_numbers配置"""
        config = {
            'access_key_id': 'test_key_id',
            'access_key_secret': 'test_key_secret',
            'sign_name': '测试签名',
            'template_code': 'SMS_123456789'
        }
        
        with patch('health_monitor.alerts.aliyun_sms_alerter.DysmsapiClient'):
            with pytest.raises(AlertConfigError):
                AliyunSMSAlerter('test-sms', config)

    def test_init_invalid_config_invalid_phone_number(self):
        """测试无效手机号格式"""
        config = {
            'access_key_id': 'test_key_id',
            'access_key_secret': 'test_key_secret',
            'sign_name': '测试签名',
            'template_code': 'SMS_123456789',
            'phone_numbers': ['invalid_phone']
        }
        
        with patch('health_monitor.alerts.aliyun_sms_alerter.DysmsapiClient'):
            with pytest.raises(AlertConfigError):
                AliyunSMSAlerter('test-sms', config)

    def test_init_invalid_config_invalid_batch_size(self):
        """测试无效批量大小"""
        config = {
            'access_key_id': 'test_key_id',
            'access_key_secret': 'test_key_secret',
            'sign_name': '测试签名',
            'template_code': 'SMS_123456789',
            'phone_numbers': ['13800138000'],
            'batch_size': 0
        }
        
        with patch('health_monitor.alerts.aliyun_sms_alerter.DysmsapiClient'):
            with pytest.raises(AlertConfigError):
                AliyunSMSAlerter('test-sms', config)

    def test_validate_config_valid(self):
        """测试配置验证 - 有效配置"""
        config = {
            'access_key_id': 'test_key_id',
            'access_key_secret': 'test_key_secret',
            'region': 'cn-hangzhou',
            'sign_name': '测试签名',
            'template_code': 'SMS_123456789',
            'phone_numbers': ['13800138000', '13900139000'],
            'batch_size': 100
        }
        
        with patch('health_monitor.alerts.aliyun_sms_alerter.DysmsapiClient'):
            alerter = AliyunSMSAlerter('test-sms', config)
            assert alerter.validate_config() is True

    def test_is_valid_phone(self):
        """测试手机号格式验证"""
        config = {
            'access_key_id': 'test_key_id',
            'access_key_secret': 'test_key_secret',
            'sign_name': '测试签名',
            'template_code': 'SMS_123456789',
            'phone_numbers': ['13800138000']
        }
        
        with patch('health_monitor.alerts.aliyun_sms_alerter.DysmsapiClient'):
            alerter = AliyunSMSAlerter('test-sms', config)
            
            # 有效手机号
            assert alerter._is_valid_phone('13800138000') is True
            assert alerter._is_valid_phone('15912345678') is True
            assert alerter._is_valid_phone('18888888888') is True
            
            # 无效手机号
            assert alerter._is_valid_phone('12345678901') is False  # 不是1开头的有效号段
            assert alerter._is_valid_phone('1380013800') is False   # 位数不够
            assert alerter._is_valid_phone('138001380000') is False # 位数过多
            assert alerter._is_valid_phone('invalid_phone') is False

    @pytest.mark.asyncio
    async def test_send_alert_success(self):
        """测试成功发送告警短信"""
        config = {
            'access_key_id': 'test_key_id',
            'access_key_secret': 'test_key_secret',
            'sign_name': '测试签名',
            'template_code': 'SMS_123456789',
            'phone_numbers': ['13800138000'],
            'template_params': {
                'service': '{{service_name}}',
                'status': '{{status}}'
            }
        }
        
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.body = MagicMock()
        mock_response.body.code = 'OK'
        mock_response.body.message = 'Success'
        
        # Mock client
        mock_client = MagicMock()
        mock_client.send_batch_sms_with_options.return_value = mock_response
        
        with patch('health_monitor.alerts.aliyun_sms_alerter.DysmsapiClient', return_value=mock_client):
            alerter = AliyunSMSAlerter('test-sms', config)
            
            message = AlertMessage(
                service_name='test-service',
                service_type='redis',
                status='DOWN',
                timestamp=datetime.now(),
                error_message='Connection failed',
                response_time=5.0
            )
            
            result = await alerter.send_alert(message)
            
            assert result is True
            mock_client.send_batch_sms_with_options.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_alert_failure_with_retry(self):
        """测试发送失败后重试"""
        config = {
            'access_key_id': 'test_key_id',
            'access_key_secret': 'test_key_secret',
            'sign_name': '测试签名',
            'template_code': 'SMS_123456789',
            'phone_numbers': ['13800138000'],
            'max_retries': 2,
            'retry_delay': 0.1,
            'template_params': {
                'service': '{{service_name}}',
                'status': '{{status}}'
            }
        }
        
        # Mock responses - fail first two times, then succeed
        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 200
        mock_response_fail.body = MagicMock()
        mock_response_fail.body.code = 'Error'
        mock_response_fail.body.message = 'Failed'
        
        mock_response_success = MagicMock()
        mock_response_success.status_code = 200
        mock_response_success.body = MagicMock()
        mock_response_success.body.code = 'OK'
        mock_response_success.body.message = 'Success'
        
        # Mock client
        mock_client = MagicMock()
        mock_client.send_batch_sms_with_options.side_effect = [
            mock_response_fail,
            mock_response_fail,
            mock_response_success
        ]
        
        with patch('health_monitor.alerts.aliyun_sms_alerter.DysmsapiClient', return_value=mock_client):
            alerter = AliyunSMSAlerter('test-sms', config)
            
            message = AlertMessage(
                service_name='test-service',
                service_type='redis',
                status='DOWN',
                timestamp=datetime.now(),
                error_message='Connection failed'
            )
            
            result = await alerter.send_alert(message)
            
            assert result is True
            assert mock_client.send_batch_sms_with_options.call_count == 3

    @pytest.mark.asyncio
    async def test_send_alert_all_retries_failed(self):
        """测试所有重试都失败"""
        config = {
            'access_key_id': 'test_key_id',
            'access_key_secret': 'test_key_secret',
            'sign_name': '测试签名',
            'template_code': 'SMS_123456789',
            'phone_numbers': ['13800138000'],
            'max_retries': 1,
            'retry_delay': 0.1,
            'template_params': {
                'service': '{{service_name}}',
                'status': '{{status}}'
            }
        }
        
        # Mock client to always fail
        mock_client = MagicMock()
        mock_client.send_batch_sms_with_options.side_effect = Exception("SMS API error")
        
        with patch('health_monitor.alerts.aliyun_sms_alerter.DysmsapiClient', return_value=mock_client):
            alerter = AliyunSMSAlerter('test-sms', config)
            
            message = AlertMessage(
                service_name='test-service',
                service_type='redis',
                status='DOWN',
                timestamp=datetime.now(),
                error_message='Connection failed'
            )
            
            with pytest.raises(AlertSendError):
                await alerter.send_alert(message)
            
            assert mock_client.send_batch_sms_with_options.call_count == 2  # Initial + 1 retry

    @pytest.mark.asyncio
    async def test_send_batch_sms_success(self):
        """测试批量发送短信成功"""
        config = {
            'access_key_id': 'test_key_id',
            'access_key_secret': 'test_key_secret',
            'sign_name': '测试签名',
            'template_code': 'SMS_123456789',
            'phone_numbers': ['13800138000', '13900139000']
        }
        
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.body = MagicMock()
        mock_response.body.code = 'OK'
        mock_response.body.message = 'Success'
        
        # Mock client
        mock_client = MagicMock()
        mock_client.send_batch_sms_with_options.return_value = mock_response
        
        with patch('health_monitor.alerts.aliyun_sms_alerter.DysmsapiClient', return_value=mock_client):
            alerter = AliyunSMSAlerter('test-sms', config)
            
            phone_numbers = ['13800138000', '13900139000']
            template_params = '{"service": "test-service", "status": "DOWN"}'
            
            result = await alerter._send_batch_sms(phone_numbers, template_params)
            
            assert result is True
            mock_client.send_batch_sms_with_options.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_batch_sms_api_error(self):
        """测试批量发送短信API错误"""
        config = {
            'access_key_id': 'test_key_id',
            'access_key_secret': 'test_key_secret',
            'sign_name': '测试签名',
            'template_code': 'SMS_123456789',
            'phone_numbers': ['13800138000']
        }
        
        # Mock response with error
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.body = MagicMock()
        mock_response.body.code = 'InvalidParameter'
        mock_response.body.message = 'Invalid template parameter'
        
        # Mock client
        mock_client = MagicMock()
        mock_client.send_batch_sms_with_options.return_value = mock_response
        
        with patch('health_monitor.alerts.aliyun_sms_alerter.DysmsapiClient', return_value=mock_client):
            alerter = AliyunSMSAlerter('test-sms', config)
            
            phone_numbers = ['13800138000']
            template_params = '{"service": "test-service"}'
            
            result = await alerter._send_batch_sms(phone_numbers, template_params)
            
            assert result is False

    def test_prepare_template_params(self):
        """测试准备模板参数"""
        config = {
            'access_key_id': 'test_key_id',
            'access_key_secret': 'test_key_secret',
            'sign_name': '测试签名',
            'template_code': 'SMS_123456789',
            'phone_numbers': ['13800138000'],
            'template_params': {
                'service': '{{service_name}}',
                'status': '{{status}}',
                'time': '{{timestamp}}',
                'error': '{{error_message}}',
                'fixed_value': 'constant'
            }
        }
        
        with patch('health_monitor.alerts.aliyun_sms_alerter.DysmsapiClient'):
            alerter = AliyunSMSAlerter('test-sms', config)
            
            message = AlertMessage(
                service_name='test-service',
                service_type='redis',
                status='DOWN',
                timestamp=datetime(2023, 1, 1, 12, 0, 0),
                error_message='Connection timeout',
                response_time=5.5,
                metadata={'host': 'localhost'}
            )
            
            result = alerter._prepare_template_params(message)
            params = json.loads(result)
            
            assert params['service'] == 'test-service'
            assert params['status'] == 'DOWN'
            assert params['time'] == '2023-01-01 12:00:00'
            assert params['error'] == 'Connection timeout'
            assert params['fixed_value'] == 'constant'

    def test_prepare_template_params_with_none_values(self):
        """测试准备模板参数 - 包含None值"""
        config = {
            'access_key_id': 'test_key_id',
            'access_key_secret': 'test_key_secret',
            'sign_name': '测试签名',
            'template_code': 'SMS_123456789',
            'phone_numbers': ['13800138000'],
            'template_params': {
                'service': '{{service_name}}',
                'error': '{{error_message}}',
                'response': '{{response_time}}'
            }
        }
        
        with patch('health_monitor.alerts.aliyun_sms_alerter.DysmsapiClient'):
            alerter = AliyunSMSAlerter('test-sms', config)
            
            message = AlertMessage(
                service_name='test-service',
                service_type='redis',
                status='UP',
                timestamp=datetime.now(),
                error_message=None,
                response_time=None
            )
            
            result = alerter._prepare_template_params(message)
            params = json.loads(result)
            
            assert params['service'] == 'test-service'
            assert params['error'] == '无'
            assert params['response'] == '未知'

    def test_get_config_summary(self):
        """测试获取配置摘要"""
        config = {
            'access_key_id': 'test_key_id',
            'access_key_secret': 'test_key_secret',
            'region': 'cn-hangzhou',
            'sign_name': '测试签名',
            'template_code': 'SMS_123456789',
            'phone_numbers': ['13800138000', '13900139000'],
            'batch_size': 50,
            'timeout': 30,
            'max_retries': 3
        }
        
        with patch('health_monitor.alerts.aliyun_sms_alerter.DysmsapiClient'):
            alerter = AliyunSMSAlerter('test-sms', config)
            summary = alerter.get_config_summary()
            
            expected = {
                'name': 'test-sms',
                'type': 'aliyun_sms',
                'region': 'cn-hangzhou',
                'endpoint': 'dysmsapi.cn-hangzhou.aliyuncs.com',
                'sign_name': '测试签名',
                'template_code': 'SMS_123456789',
                'phone_numbers_count': 2,
                'batch_size': 50,
                'timeout': 30,
                'max_retries': 3
            }
            
            assert summary == expected