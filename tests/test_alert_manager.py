"""告警管理器测试"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from health_monitor.alerts.manager import AlertManager
from health_monitor.alerts.base import BaseAlerter
from health_monitor.models.health_check import StateChange, AlertMessage
from health_monitor.utils.exceptions import AlertConfigError


class MockAlerter(BaseAlerter):
    """模拟告警器用于测试"""
    
    def __init__(self, name: str, config: dict, should_succeed: bool = True):
        super().__init__(name, config)
        self.should_succeed = should_succeed
        self.sent_messages = []
    
    async def send_alert(self, message: AlertMessage) -> bool:
        self.sent_messages.append(message)
        if not self.should_succeed:
            raise Exception("模拟发送失败")
        return True
    
    def validate_config(self) -> bool:
        return True


class TestAlertManager:
    """告警管理器测试类"""
    
    def setup_method(self):
        """测试前准备"""
        self.alert_configs = [
            {
                'name': 'test-alerter',
                'type': 'mock',
                'config': {}
            }
        ]
        self.manager = AlertManager(self.alert_configs)
    
    def test_init(self):
        """测试初始化"""
        assert self.manager.alert_configs == self.alert_configs
        assert len(self.manager.alerters) == 0
        assert self.manager.get_alerter_count() == 0
    
    def test_add_alerter(self):
        """测试添加告警器"""
        alerter = MockAlerter('test', {})
        self.manager.add_alerter(alerter)
        
        assert self.manager.get_alerter_count() == 1
        assert 'test' in self.manager.get_alerter_names()
    
    def test_add_invalid_alerter(self):
        """测试添加无效告警器"""
        with pytest.raises(AlertConfigError):
            self.manager.add_alerter("not an alerter")
    
    def test_remove_alerter(self):
        """测试移除告警器"""
        alerter = MockAlerter('test', {})
        self.manager.add_alerter(alerter)
        
        assert self.manager.remove_alerter('test') is True
        assert self.manager.get_alerter_count() == 0
        
        # 移除不存在的告警器
        assert self.manager.remove_alerter('nonexistent') is False
    
    @pytest.mark.asyncio
    async def test_send_alert_no_alerters(self):
        """测试没有告警器时发送告警"""
        state_change = StateChange(
            service_name='test-service',
            service_type='redis',
            old_state=True,
            new_state=False,
            error_message='连接失败'
        )
        
        # 应该不会抛出异常
        await self.manager.send_alert(state_change)
    
    @pytest.mark.asyncio
    async def test_send_alert_success(self):
        """测试成功发送告警"""
        alerter = MockAlerter('test', {})
        self.manager.add_alerter(alerter)
        
        state_change = StateChange(
            service_name='test-service',
            service_type='redis',
            old_state=True,
            new_state=False,
            error_message='连接失败'
        )
        
        await self.manager.send_alert(state_change)
        
        assert len(alerter.sent_messages) == 1
        message = alerter.sent_messages[0]
        assert message.service_name == 'test-service'
        assert message.status == 'DOWN'
        assert message.error_message == '连接失败'
    
    @pytest.mark.asyncio
    async def test_send_alert_multiple_alerters(self):
        """测试向多个告警器发送告警"""
        alerter1 = MockAlerter('test1', {})
        alerter2 = MockAlerter('test2', {})
        
        self.manager.add_alerter(alerter1)
        self.manager.add_alerter(alerter2)
        
        state_change = StateChange(
            service_name='test-service',
            service_type='redis',
            old_state=True,
            new_state=False
        )
        
        await self.manager.send_alert(state_change)
        
        assert len(alerter1.sent_messages) == 1
        assert len(alerter2.sent_messages) == 1
    
    @pytest.mark.asyncio
    async def test_send_alert_with_failure(self):
        """测试部分告警器发送失败"""
        alerter1 = MockAlerter('success', {}, should_succeed=True)
        alerter2 = MockAlerter('failure', {}, should_succeed=False)
        
        self.manager.add_alerter(alerter1)
        self.manager.add_alerter(alerter2)
        
        state_change = StateChange(
            service_name='test-service',
            service_type='redis',
            old_state=True,
            new_state=False
        )
        
        # 应该不会抛出异常，即使部分失败
        await self.manager.send_alert(state_change)
        
        assert len(alerter1.sent_messages) == 1
        assert len(alerter2.sent_messages) == 1  # 仍然会尝试发送
    
    def test_create_alert_message_down(self):
        """测试创建DOWN状态告警消息"""
        state_change = StateChange(
            service_name='test-service',
            service_type='redis',
            old_state=True,
            new_state=False,
            error_message='连接失败',
            response_time=100.5
        )
        
        message = self.manager._create_alert_message(state_change)
        
        assert message.service_name == 'test-service'
        assert message.service_type == 'redis'
        assert message.status == 'DOWN'
        assert message.error_message == '连接失败'
        assert message.response_time == 100.5
        assert message.metadata['old_state'] is True
        assert message.metadata['new_state'] is False
    
    def test_create_alert_message_up(self):
        """测试创建UP状态告警消息"""
        state_change = StateChange(
            service_name='test-service',
            service_type='redis',
            old_state=False,
            new_state=True
        )
        
        message = self.manager._create_alert_message(state_change)
        
        assert message.status == 'UP'
        assert message.metadata['old_state'] is False
        assert message.metadata['new_state'] is True
    
    def test_alert_deduplication(self):
        """测试告警去重功能"""
        message1 = AlertMessage(
            service_name='test-service',
            service_type='redis',
            status='DOWN',
            timestamp=datetime.now()
        )
        
        # 第一次不应该去重
        assert not self.manager._should_deduplicate(message1)
        self.manager._record_alert(message1)
        
        # 短时间内相同告警应该去重
        message2 = AlertMessage(
            service_name='test-service',
            service_type='redis',
            status='DOWN',
            timestamp=datetime.now()
        )
        assert self.manager._should_deduplicate(message2)
        
        # 不同状态不应该去重
        message3 = AlertMessage(
            service_name='test-service',
            service_type='redis',
            status='UP',
            timestamp=datetime.now()
        )
        assert not self.manager._should_deduplicate(message3)
        
        # 不同服务不应该去重
        message4 = AlertMessage(
            service_name='other-service',
            service_type='redis',
            status='DOWN',
            timestamp=datetime.now()
        )
        assert not self.manager._should_deduplicate(message4)
    
    def test_alert_deduplication_timeout(self):
        """测试告警去重超时"""
        # 模拟过期的告警
        old_time = datetime.now() - timedelta(minutes=10)
        message1 = AlertMessage(
            service_name='test-service',
            service_type='redis',
            status='DOWN',
            timestamp=old_time
        )
        
        self.manager._record_alert(message1)
        
        # 新的相同告警不应该被去重（因为时间已过期）
        message2 = AlertMessage(
            service_name='test-service',
            service_type='redis',
            status='DOWN',
            timestamp=datetime.now()
        )
        assert not self.manager._should_deduplicate(message2)
    
    def test_render_template_basic(self):
        """测试基本模板渲染"""
        template_str = "服务 $service_name 状态: $status"
        message = AlertMessage(
            service_name='test-service',
            service_type='redis',
            status='DOWN'
        )
        
        result = self.manager.render_template(template_str, message)
        assert result == "服务 test-service 状态: DOWN"
    
    def test_render_template_all_variables(self):
        """测试所有变量的模板渲染"""
        template_str = (
            "服务: $service_name\n"
            "类型: $service_type\n"
            "状态: $status\n"
            "时间: $timestamp\n"
            "错误: $error_message\n"
            "响应时间: $response_time"
        )
        
        message = AlertMessage(
            service_name='test-service',
            service_type='redis',
            status='DOWN',
            timestamp=datetime(2023, 1, 1, 12, 0, 0),
            error_message='连接超时',
            response_time=1500.5
        )
        
        result = self.manager.render_template(template_str, message)
        
        assert 'test-service' in result
        assert 'redis' in result
        assert 'DOWN' in result
        assert '2023-01-01 12:00:00' in result
        assert '连接超时' in result
        assert '1500.50ms' in result
    
    def test_render_template_with_metadata(self):
        """测试包含元数据的模板渲染"""
        template_str = "服务 $service_name 从 $metadata_old_state 变为 $metadata_new_state"
        message = AlertMessage(
            service_name='test-service',
            service_type='redis',
            status='DOWN',
            metadata={'old_state': True, 'new_state': False}
        )
        
        result = self.manager.render_template(template_str, message)
        assert result == "服务 test-service 从 True 变为 False"
    
    def test_render_template_missing_variable(self):
        """测试模板变量缺失"""
        template_str = "服务 $service_name 状态: $nonexistent_variable"
        message = AlertMessage(
            service_name='test-service',
            service_type='redis',
            status='DOWN'
        )
        
        with pytest.raises(AlertConfigError):
            self.manager.render_template(template_str, message)
    
    def test_template_caching(self):
        """测试模板缓存"""
        template_str = "服务 $service_name 状态: $status"
        message = AlertMessage(
            service_name='test-service',
            service_type='redis',
            status='DOWN'
        )
        
        # 第一次渲染
        result1 = self.manager.render_template(template_str, message)
        
        # 第二次渲染应该使用缓存
        result2 = self.manager.render_template(template_str, message)
        
        assert result1 == result2
        assert template_str in self.manager._template_cache
    
    def test_clear_alert_history(self):
        """测试清空告警历史"""
        message = AlertMessage(
            service_name='test-service',
            service_type='redis',
            status='DOWN'
        )
        
        self.manager._record_alert(message)
        assert len(self.manager._alert_history) > 0
        
        self.manager.clear_alert_history()
        assert len(self.manager._alert_history) == 0
    
    @pytest.mark.asyncio
    async def test_send_alert_deduplication_integration(self):
        """测试发送告警时的去重集成"""
        alerter = MockAlerter('test', {})
        self.manager.add_alerter(alerter)
        
        state_change = StateChange(
            service_name='test-service',
            service_type='redis',
            old_state=True,
            new_state=False
        )
        
        # 第一次发送
        await self.manager.send_alert(state_change)
        assert len(alerter.sent_messages) == 1
        
        # 第二次发送应该被去重
        await self.manager.send_alert(state_change)
        assert len(alerter.sent_messages) == 1  # 没有增加