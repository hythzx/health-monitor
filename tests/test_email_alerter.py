"""邮件告警器测试"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

from health_monitor.alerts.email_alerter import EmailAlerter
from health_monitor.models.health_check import AlertMessage
from health_monitor.utils.exceptions import AlertConfigError, AlertSendError


class TestEmailAlerter:
    """邮件告警器测试类"""

    def test_init_valid_config(self):
        """测试有效配置的初始化"""
        config = {
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'username': 'test@gmail.com',
            'password': 'test_password',
            'from_email': 'test@gmail.com',
            'to_emails': ['admin@company.com'],
            'use_tls': True
        }
        
        alerter = EmailAlerter('test-email', config)
        
        assert alerter.name == 'test-email'
        assert alerter.smtp_server == 'smtp.gmail.com'
        assert alerter.smtp_port == 587
        assert alerter.username == 'test@gmail.com'
        assert alerter.from_email == 'test@gmail.com'
        assert alerter.to_emails == ['admin@company.com']
        assert alerter.use_tls is True

    def test_init_invalid_config_missing_smtp_server(self):
        """测试缺少SMTP服务器配置"""
        config = {
            'username': 'test@gmail.com',
            'password': 'test_password',
            'from_email': 'test@gmail.com',
            'to_emails': ['admin@company.com']
        }
        
        with pytest.raises(AlertConfigError):
            EmailAlerter('test-email', config)

    def test_init_invalid_config_missing_username(self):
        """测试缺少用户名配置"""
        config = {
            'smtp_server': 'smtp.gmail.com',
            'password': 'test_password',
            'from_email': 'test@gmail.com',
            'to_emails': ['admin@company.com']
        }
        
        with pytest.raises(AlertConfigError):
            EmailAlerter('test-email', config)

    def test_init_invalid_config_missing_password(self):
        """测试缺少密码配置"""
        config = {
            'smtp_server': 'smtp.gmail.com',
            'username': 'test@gmail.com',
            'from_email': 'test@gmail.com',
            'to_emails': ['admin@company.com']
        }
        
        with pytest.raises(AlertConfigError):
            EmailAlerter('test-email', config)

    def test_init_invalid_config_missing_to_emails(self):
        """测试缺少收件人配置"""
        config = {
            'smtp_server': 'smtp.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password',
            'from_email': 'test@gmail.com'
        }
        
        with pytest.raises(AlertConfigError):
            EmailAlerter('test-email', config)

    def test_init_invalid_config_invalid_email(self):
        """测试无效邮箱格式"""
        config = {
            'smtp_server': 'smtp.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password',
            'from_email': 'invalid-email',
            'to_emails': ['admin@company.com']
        }
        
        with pytest.raises(AlertConfigError):
            EmailAlerter('test-email', config)

    def test_init_invalid_config_invalid_port(self):
        """测试无效端口配置"""
        config = {
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': -1,
            'username': 'test@gmail.com',
            'password': 'test_password',
            'from_email': 'test@gmail.com',
            'to_emails': ['admin@company.com']
        }
        
        with pytest.raises(AlertConfigError):
            EmailAlerter('test-email', config)

    def test_init_invalid_config_ssl_and_tls(self):
        """测试同时启用SSL和TLS"""
        config = {
            'smtp_server': 'smtp.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password',
            'from_email': 'test@gmail.com',
            'to_emails': ['admin@company.com'],
            'use_ssl': True,
            'use_tls': True
        }
        
        with pytest.raises(AlertConfigError):
            EmailAlerter('test-email', config)

    def test_validate_config_valid(self):
        """测试配置验证 - 有效配置"""
        config = {
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'username': 'test@gmail.com',
            'password': 'test_password',
            'from_email': 'test@gmail.com',
            'to_emails': ['admin@company.com', 'ops@company.com'],
            'cc_emails': ['manager@company.com'],
            'use_tls': True
        }
        
        alerter = EmailAlerter('test-email', config)
        assert alerter.validate_config() is True

    def test_is_valid_email(self):
        """测试邮箱格式验证"""
        config = {
            'smtp_server': 'smtp.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password',
            'from_email': 'test@gmail.com',
            'to_emails': ['admin@company.com']
        }
        
        alerter = EmailAlerter('test-email', config)
        
        # 有效邮箱
        assert alerter._is_valid_email('test@gmail.com') is True
        assert alerter._is_valid_email('user.name@company.co.uk') is True
        assert alerter._is_valid_email('test123+tag@example.org') is True
        
        # 无效邮箱
        assert alerter._is_valid_email('invalid-email') is False
        assert alerter._is_valid_email('@gmail.com') is False
        assert alerter._is_valid_email('test@') is False
        assert alerter._is_valid_email('test.gmail.com') is False

    @pytest.mark.asyncio
    async def test_send_alert_success(self):
        """测试成功发送告警邮件"""
        config = {
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'username': 'test@gmail.com',
            'password': 'test_password',
            'from_email': 'test@gmail.com',
            'to_emails': ['admin@company.com'],
            'use_tls': True
        }
        
        alerter = EmailAlerter('test-email', config)
        
        message = AlertMessage(
            service_name='test-service',
            service_type='redis',
            status='DOWN',
            timestamp=datetime.now(),
            error_message='Connection failed',
            response_time=5.0
        )
        
        # Mock aiosmtplib.send
        with patch('health_monitor.alerts.email_alerter.aiosmtplib.send', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = None
            
            result = await alerter.send_alert(message)
            
            assert result is True
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_alert_failure_with_retry(self):
        """测试发送失败后重试"""
        config = {
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'username': 'test@gmail.com',
            'password': 'test_password',
            'from_email': 'test@gmail.com',
            'to_emails': ['admin@company.com'],
            'use_tls': True,
            'max_retries': 2,
            'retry_delay': 0.1
        }
        
        alerter = EmailAlerter('test-email', config)
        
        message = AlertMessage(
            service_name='test-service',
            service_type='redis',
            status='DOWN',
            timestamp=datetime.now(),
            error_message='Connection failed'
        )
        
        # Mock aiosmtplib.send to fail first two times, then succeed
        with patch('health_monitor.alerts.email_alerter.aiosmtplib.send', new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = [
                Exception("SMTP error 1"),
                Exception("SMTP error 2"),
                None  # Success on third try
            ]
            
            result = await alerter.send_alert(message)
            
            assert result is True
            assert mock_send.call_count == 3

    @pytest.mark.asyncio
    async def test_send_alert_all_retries_failed(self):
        """测试所有重试都失败"""
        config = {
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'username': 'test@gmail.com',
            'password': 'test_password',
            'from_email': 'test@gmail.com',
            'to_emails': ['admin@company.com'],
            'use_tls': True,
            'max_retries': 1,
            'retry_delay': 0.1
        }
        
        alerter = EmailAlerter('test-email', config)
        
        message = AlertMessage(
            service_name='test-service',
            service_type='redis',
            status='DOWN',
            timestamp=datetime.now(),
            error_message='Connection failed'
        )
        
        # Mock aiosmtplib.send to always fail
        with patch('health_monitor.alerts.email_alerter.aiosmtplib.send', new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = Exception("SMTP error")
            
            with pytest.raises(AlertSendError):
                await alerter.send_alert(message)
            
            assert mock_send.call_count == 2  # Initial + 1 retry

    def test_render_template(self):
        """测试模板渲染"""
        config = {
            'smtp_server': 'smtp.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password',
            'from_email': 'test@gmail.com',
            'to_emails': ['admin@company.com']
        }
        
        alerter = EmailAlerter('test-email', config)
        
        message = AlertMessage(
            service_name='test-service',
            service_type='redis',
            status='DOWN',
            timestamp=datetime(2023, 1, 1, 12, 0, 0),
            error_message='Connection timeout',
            response_time=5.5,
            metadata={'host': 'localhost', 'port': 6379}
        )
        
        template = "服务 {{service_name}} 状态: {{status}}, 时间: {{timestamp}}, 错误: {{error_message}}, 响应时间: {{response_time}}ms, 主机: {{metadata_host}}"
        
        result = alerter._render_template(template, message)
        
        expected = "服务 test-service 状态: DOWN, 时间: 2023-01-01 12:00:00, 错误: Connection timeout, 响应时间: 5.50ms, 主机: localhost"
        assert result == expected

    def test_render_template_with_none_values(self):
        """测试模板渲染 - 包含None值"""
        config = {
            'smtp_server': 'smtp.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password',
            'from_email': 'test@gmail.com',
            'to_emails': ['admin@company.com']
        }
        
        alerter = EmailAlerter('test-email', config)
        
        message = AlertMessage(
            service_name='test-service',
            service_type='redis',
            status='UP',
            timestamp=datetime(2023, 1, 1, 12, 0, 0),
            error_message=None,
            response_time=None
        )
        
        template = "服务 {{service_name}} 状态: {{status}}, 错误: {{error_message}}, 响应时间: {{response_time}}ms"
        
        result = alerter._render_template(template, message)
        
        expected = "服务 test-service 状态: UP, 错误: 无, 响应时间: 未知ms"
        assert result == expected

    def test_create_email_message(self):
        """测试创建邮件消息"""
        config = {
            'smtp_server': 'smtp.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password',
            'from_email': 'test@gmail.com',
            'from_name': '监控系统',
            'to_emails': ['admin@company.com', 'ops@company.com'],
            'cc_emails': ['manager@company.com'],
            'subject_template': '告警: {{service_name}} - {{status}}',
            'body_template': '服务 {{service_name}} 状态变为 {{status}}'
        }
        
        alerter = EmailAlerter('test-email', config)
        
        message = AlertMessage(
            service_name='test-service',
            service_type='redis',
            status='DOWN',
            timestamp=datetime.now(),
            error_message='Connection failed'
        )
        
        email_msg = alerter._create_email_message(message)
        
        # 邮件头中的中文会被编码，所以检查是否包含邮箱地址
        assert 'test@gmail.com' in email_msg['From']
        assert email_msg['To'] == 'admin@company.com, ops@company.com'
        assert email_msg['Cc'] == 'manager@company.com'
        assert email_msg['Subject'] == '告警: test-service - DOWN'

    def test_get_config_summary(self):
        """测试获取配置摘要"""
        config = {
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'username': 'test@gmail.com',
            'password': 'test_password',
            'from_email': 'test@gmail.com',
            'to_emails': ['admin@company.com', 'ops@company.com'],
            'cc_emails': ['manager@company.com'],
            'use_tls': True,
            'timeout': 30,
            'max_retries': 3
        }
        
        alerter = EmailAlerter('test-email', config)
        summary = alerter.get_config_summary()
        
        expected = {
            'name': 'test-email',
            'type': 'email',
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'from_email': 'test@gmail.com',
            'to_emails_count': 2,
            'cc_emails_count': 1,
            'bcc_emails_count': 0,
            'use_tls': True,
            'use_ssl': False,
            'timeout': 30,
            'max_retries': 3
        }
        
        assert summary == expected

    def test_get_default_body_template(self):
        """测试获取默认邮件正文模板"""
        config = {
            'smtp_server': 'smtp.gmail.com',
            'username': 'test@gmail.com',
            'password': 'test_password',
            'from_email': 'test@gmail.com',
            'to_emails': ['admin@company.com']
        }
        
        alerter = EmailAlerter('test-email', config)
        template = alerter._get_default_body_template()
        
        assert '{{service_name}}' in template
        assert '{{service_type}}' in template
        assert '{{status}}' in template
        assert '{{timestamp}}' in template
        assert '{{error_message}}' in template
        assert '{{response_time}}' in template