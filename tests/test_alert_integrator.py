"""告警集成器测试"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

from health_monitor.alerts.integrator import AlertIntegrator
from health_monitor.services.state_manager import StateManager
from health_monitor.models.health_check import HealthCheckResult, StateChange


class TestAlertIntegrator:
    """告警集成器测试类"""

    def test_init_with_http_alerter(self):
        """测试初始化HTTP告警器"""
        state_manager = StateManager()
        alert_configs = [
            {
                'name': 'test-http',
                'type': 'http',
                'url': 'https://example.com/webhook',
                'method': 'POST'
            }
        ]
        
        integrator = AlertIntegrator(state_manager, alert_configs)
        
        assert integrator.alert_manager.get_alerter_count() == 1
        assert 'test-http' in integrator.alert_manager.get_alerter_names()

    def test_init_with_email_alerter(self):
        """测试初始化邮件告警器"""
        state_manager = StateManager()
        alert_configs = [
            {
                'name': 'test-email',
                'type': 'email',
                'smtp_server': 'smtp.gmail.com',
                'username': 'test@gmail.com',
                'password': 'test_password',
                'from_email': 'test@gmail.com',
                'to_emails': ['admin@company.com']
            }
        ]
        
        integrator = AlertIntegrator(state_manager, alert_configs)
        
        assert integrator.alert_manager.get_alerter_count() == 1
        assert 'test-email' in integrator.alert_manager.get_alerter_names()

    def test_init_with_aliyun_sms_alerter(self):
        """测试初始化阿里云短信告警器"""
        state_manager = StateManager()
        alert_configs = [
            {
                'name': 'test-sms',
                'type': 'aliyun_sms',
                'access_key_id': 'test_key_id',
                'access_key_secret': 'test_key_secret',
                'sign_name': '测试签名',
                'template_code': 'SMS_123456789',
                'phone_numbers': ['13800138000']
            }
        ]
        
        with patch('health_monitor.alerts.aliyun_sms_alerter.DysmsapiClient'):
            integrator = AlertIntegrator(state_manager, alert_configs)
            
            assert integrator.alert_manager.get_alerter_count() == 1
            assert 'test-sms' in integrator.alert_manager.get_alerter_names()

    def test_init_with_multiple_alerters(self):
        """测试初始化多个告警器"""
        state_manager = StateManager()
        alert_configs = [
            {
                'name': 'test-http',
                'type': 'http',
                'url': 'https://example.com/webhook',
                'method': 'POST'
            },
            {
                'name': 'test-email',
                'type': 'email',
                'smtp_server': 'smtp.gmail.com',
                'username': 'test@gmail.com',
                'password': 'test_password',
                'from_email': 'test@gmail.com',
                'to_emails': ['admin@company.com']
            },
            {
                'name': 'test-sms',
                'type': 'aliyun_sms',
                'access_key_id': 'test_key_id',
                'access_key_secret': 'test_key_secret',
                'sign_name': '测试签名',
                'template_code': 'SMS_123456789',
                'phone_numbers': ['13800138000']
            }
        ]
        
        with patch('health_monitor.alerts.aliyun_sms_alerter.DysmsapiClient'):
            integrator = AlertIntegrator(state_manager, alert_configs)
            
            assert integrator.alert_manager.get_alerter_count() == 3
            alerter_names = integrator.alert_manager.get_alerter_names()
            assert 'test-http' in alerter_names
            assert 'test-email' in alerter_names
            assert 'test-sms' in alerter_names

    def test_init_with_unsupported_alerter_type(self):
        """测试不支持的告警器类型"""
        state_manager = StateManager()
        alert_configs = [
            {
                'name': 'test-unsupported',
                'type': 'unsupported_type',
                'some_config': 'value'
            }
        ]
        
        integrator = AlertIntegrator(state_manager, alert_configs)
        
        # 不支持的类型应该被忽略
        assert integrator.alert_manager.get_alerter_count() == 0

    @pytest.mark.asyncio
    async def test_process_health_check_result_with_state_change(self):
        """测试处理健康检查结果并触发告警"""
        state_manager = StateManager()
        alert_configs = [
            {
                'name': 'test-http',
                'type': 'http',
                'url': 'https://example.com/webhook',
                'method': 'POST'
            }
        ]
        
        integrator = AlertIntegrator(state_manager, alert_configs)
        
        # Mock alert manager send_alert method
        integrator.alert_manager.send_alert = AsyncMock()
        
        # 创建第一个健康检查结果（建立初始状态）
        result1 = HealthCheckResult(
            service_name='test-service',
            service_type='redis',
            is_healthy=True,
            response_time=1.0,
            timestamp=datetime.now()
        )
        
        # 处理第一个结果（初始状态，不会触发告警）
        await integrator.process_health_check_result(result1)
        
        # 验证初始状态不触发告警
        integrator.alert_manager.send_alert.assert_not_called()
        
        # 创建第二个健康检查结果（状态变化）
        result2 = HealthCheckResult(
            service_name='test-service',
            service_type='redis',
            is_healthy=False,
            response_time=5.0,
            error_message='Connection failed',
            timestamp=datetime.now()
        )
        
        # 处理第二个结果（状态变化，应该触发告警）
        await integrator.process_health_check_result(result2)
        
        # 验证告警被触发
        integrator.alert_manager.send_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_health_check_result_no_state_change(self):
        """测试处理健康检查结果但没有状态变化"""
        state_manager = StateManager()
        alert_configs = [
            {
                'name': 'test-http',
                'type': 'http',
                'url': 'https://example.com/webhook',
                'method': 'POST'
            }
        ]
        
        integrator = AlertIntegrator(state_manager, alert_configs)
        
        # Mock alert manager send_alert method
        integrator.alert_manager.send_alert = AsyncMock()
        
        # 创建健康检查结果 - 第一次
        result1 = HealthCheckResult(
            service_name='test-service',
            service_type='redis',
            is_healthy=True,
            response_time=1.0,
            timestamp=datetime.now()
        )
        
        # 第一次处理 - 应该触发告警（初始状态变化）
        await integrator.process_health_check_result(result1)
        
        # 重置mock
        integrator.alert_manager.send_alert.reset_mock()
        
        # 创建相同状态的健康检查结果 - 第二次
        result2 = HealthCheckResult(
            service_name='test-service',
            service_type='redis',
            is_healthy=True,
            response_time=1.2,
            timestamp=datetime.now()
        )
        
        # 第二次处理 - 不应该触发告警（状态没有变化）
        await integrator.process_health_check_result(result2)
        
        # 验证告警没有被触发
        integrator.alert_manager.send_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_trigger_alert_with_filter(self):
        """测试带过滤器的告警触发"""
        state_manager = StateManager()
        alert_configs = [
            {
                'name': 'test-http',
                'type': 'http',
                'url': 'https://example.com/webhook',
                'method': 'POST'
            }
        ]
        
        integrator = AlertIntegrator(state_manager, alert_configs)
        
        # 添加过滤器 - 只允许特定服务的告警
        def service_filter(state_change):
            return state_change.service_name == 'allowed-service'
        
        integrator.add_alert_filter(service_filter)
        
        # Mock alert manager send_alert method
        integrator.alert_manager.send_alert = AsyncMock()
        
        # 创建不被允许的服务状态变化
        state_change_blocked = StateChange(
            service_name='blocked-service',
            service_type='redis',
            old_state=True,
            new_state=False,
            timestamp=datetime.now()
        )
        
        # 触发告警 - 应该被过滤器阻止
        await integrator.trigger_alert(state_change_blocked)
        
        # 验证告警没有被发送
        integrator.alert_manager.send_alert.assert_not_called()
        
        # 创建被允许的服务状态变化
        state_change_allowed = StateChange(
            service_name='allowed-service',
            service_type='redis',
            old_state=True,
            new_state=False,
            timestamp=datetime.now()
        )
        
        # 触发告警 - 应该通过过滤器
        await integrator.trigger_alert(state_change_allowed)
        
        # 验证告警被发送
        integrator.alert_manager.send_alert.assert_called_once_with(state_change_allowed)

    def test_reload_alert_config(self):
        """测试重新加载告警配置"""
        state_manager = StateManager()
        initial_configs = [
            {
                'name': 'test-http',
                'type': 'http',
                'url': 'https://example.com/webhook',
                'method': 'POST'
            }
        ]
        
        integrator = AlertIntegrator(state_manager, initial_configs)
        assert integrator.alert_manager.get_alerter_count() == 1
        
        # 重新加载配置
        new_configs = [
            {
                'name': 'test-email',
                'type': 'email',
                'smtp_server': 'smtp.gmail.com',
                'username': 'test@gmail.com',
                'password': 'test_password',
                'from_email': 'test@gmail.com',
                'to_emails': ['admin@company.com']
            },
            {
                'name': 'test-sms',
                'type': 'aliyun_sms',
                'access_key_id': 'test_key_id',
                'access_key_secret': 'test_key_secret',
                'sign_name': '测试签名',
                'template_code': 'SMS_123456789',
                'phone_numbers': ['13800138000']
            }
        ]
        
        with patch('health_monitor.alerts.aliyun_sms_alerter.DysmsapiClient'):
            integrator.reload_alert_config(new_configs)
            
            assert integrator.alert_manager.get_alerter_count() == 2
            alerter_names = integrator.alert_manager.get_alerter_names()
            assert 'test-email' in alerter_names
            assert 'test-sms' in alerter_names
            assert 'test-http' not in alerter_names  # 旧的配置应该被清除

    def test_get_alert_stats(self):
        """测试获取告警统计信息"""
        state_manager = StateManager()
        alert_configs = [
            {
                'name': 'test-http',
                'type': 'http',
                'url': 'https://example.com/webhook',
                'method': 'POST'
            },
            {
                'name': 'test-email',
                'type': 'email',
                'smtp_server': 'smtp.gmail.com',
                'username': 'test@gmail.com',
                'password': 'test_password',
                'from_email': 'test@gmail.com',
                'to_emails': ['admin@company.com']
            }
        ]
        
        integrator = AlertIntegrator(state_manager, alert_configs)
        
        # 添加一些过滤器和回调
        integrator.add_alert_filter(lambda x: True)
        integrator.add_pre_alert_callback(lambda x: None)
        integrator.add_post_alert_callback(lambda x, y: None)
        
        stats = integrator.get_alert_stats()
        
        assert stats['alerter_count'] == 2
        assert len(stats['alerter_names']) == 2
        assert stats['filter_count'] == 1
        assert stats['pre_callback_count'] == 1
        assert stats['post_callback_count'] == 1

    @pytest.mark.asyncio
    async def test_test_alert_system(self):
        """测试告警系统测试功能"""
        state_manager = StateManager()
        alert_configs = [
            {
                'name': 'test-http',
                'type': 'http',
                'url': 'https://example.com/webhook',
                'method': 'POST'
            }
        ]
        
        integrator = AlertIntegrator(state_manager, alert_configs)
        
        # Mock trigger_alert method
        integrator.trigger_alert = AsyncMock()
        
        # 测试告警系统
        result = await integrator.test_alert_system('test-service')
        
        assert result is True
        integrator.trigger_alert.assert_called_once()
        
        # 验证传递的参数
        call_args = integrator.trigger_alert.call_args[0][0]
        assert call_args.service_name == 'test-service'
        assert call_args.service_type == 'test'
        assert call_args.old_state is True
        assert call_args.new_state is False
        assert call_args.error_message == '告警系统测试'