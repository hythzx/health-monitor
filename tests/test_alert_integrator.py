"""告警集成器测试"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from health_monitor.alerts.integrator import AlertIntegrator
from health_monitor.alerts.http_alerter import HTTPAlerter
from health_monitor.services.state_manager import StateManager
from health_monitor.models.health_check import HealthCheckResult, StateChange


class TestAlertIntegrator:
    """告警集成器测试类"""
    
    def setup_method(self):
        """测试前准备"""
        self.state_manager = StateManager()
        
        self.alert_configs = [
            {
                'name': 'test-webhook',
                'type': 'http',
                'url': 'https://api.example.com/webhook',
                'method': 'POST'
            }
        ]
        
        self.integrator = AlertIntegrator(self.state_manager, self.alert_configs)
    
    def test_init(self):
        """测试初始化"""
        assert self.integrator.state_manager == self.state_manager
        assert self.integrator.alert_manager.get_alerter_count() == 1
        assert len(self.integrator.alert_filters) == 0
    
    def test_initialize_alerters_http(self):
        """测试初始化HTTP告警器"""
        configs = [
            {
                'name': 'webhook1',
                'type': 'http',
                'url': 'https://api1.example.com/webhook',
                'method': 'POST'
            },
            {
                'name': 'webhook2',
                'type': 'http',
                'url': 'https://api2.example.com/webhook',
                'method': 'POST'
            }
        ]
        
        integrator = AlertIntegrator(StateManager(), configs)
        assert integrator.alert_manager.get_alerter_count() == 2
        assert 'webhook1' in integrator.alert_manager.get_alerter_names()
        assert 'webhook2' in integrator.alert_manager.get_alerter_names()
    
    def test_initialize_alerters_unsupported_type(self):
        """测试初始化不支持的告警器类型"""
        configs = [
            {
                'name': 'unsupported',
                'type': 'email',  # 不支持的类型
                'config': {}
            }
        ]
        
        integrator = AlertIntegrator(StateManager(), configs)
        assert integrator.alert_manager.get_alerter_count() == 0
    
    @pytest.mark.asyncio
    async def test_process_health_check_result_no_state_change(self):
        """测试处理健康检查结果（无状态变化）"""
        result = HealthCheckResult(
            service_name='test-service',
            service_type='redis',
            is_healthy=True,
            response_time=100.0
        )
        
        with patch.object(self.integrator, 'trigger_alert') as mock_trigger:
            await self.integrator.process_health_check_result(result)
            
            # 首次检查不应该触发告警
            mock_trigger.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_process_health_check_result_with_state_change(self):
        """测试处理健康检查结果（有状态变化）"""
        # 先添加一个健康状态
        first_result = HealthCheckResult(
            service_name='test-service',
            service_type='redis',
            is_healthy=True,
            response_time=100.0
        )
        await self.integrator.process_health_check_result(first_result)
        
        # 再添加一个不健康状态
        second_result = HealthCheckResult(
            service_name='test-service',
            service_type='redis',
            is_healthy=False,
            response_time=5000.0,
            error_message='连接超时'
        )
        
        with patch.object(self.integrator, 'trigger_alert') as mock_trigger:
            await self.integrator.process_health_check_result(second_result)
            
            # 状态变化应该触发告警
            mock_trigger.assert_called_once()
            
            # 验证传递的StateChange参数
            call_args = mock_trigger.call_args[0][0]
            assert call_args.service_name == 'test-service'
            assert call_args.old_state is True
            assert call_args.new_state is False
    
    @pytest.mark.asyncio
    async def test_trigger_alert_success(self):
        """测试成功触发告警"""
        state_change = StateChange(
            service_name='test-service',
            service_type='redis',
            old_state=True,
            new_state=False
        )
        
        with patch.object(self.integrator.alert_manager, 'send_alert') as mock_send:
            await self.integrator.trigger_alert(state_change)
            
            mock_send.assert_called_once_with(state_change)
    
    @pytest.mark.asyncio
    async def test_trigger_alert_with_filter(self):
        """测试带过滤器的告警触发"""
        state_change = StateChange(
            service_name='test-service',
            service_type='redis',
            old_state=True,
            new_state=False
        )
        
        # 添加一个阻止告警的过滤器
        def block_filter(change):
            return False
        
        self.integrator.add_alert_filter(block_filter)
        
        with patch.object(self.integrator.alert_manager, 'send_alert') as mock_send:
            await self.integrator.trigger_alert(state_change)
            
            # 告警应该被过滤器阻止
            mock_send.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_trigger_alert_with_callbacks(self):
        """测试带回调的告警触发"""
        state_change = StateChange(
            service_name='test-service',
            service_type='redis',
            old_state=True,
            new_state=False
        )
        
        pre_callback = Mock()
        post_callback = Mock()
        
        self.integrator.add_pre_alert_callback(pre_callback)
        self.integrator.add_post_alert_callback(post_callback)
        
        with patch.object(self.integrator.alert_manager, 'send_alert'):
            await self.integrator.trigger_alert(state_change)
            
            # 验证回调被调用
            pre_callback.assert_called_once_with(state_change)
            post_callback.assert_called_once_with(state_change, True)
    
    @pytest.mark.asyncio
    async def test_trigger_alert_failure_callback(self):
        """测试告警失败时的回调"""
        state_change = StateChange(
            service_name='test-service',
            service_type='redis',
            old_state=True,
            new_state=False
        )
        
        post_callback = Mock()
        self.integrator.add_post_alert_callback(post_callback)
        
        # 模拟告警发送失败
        with patch.object(self.integrator.alert_manager, 'send_alert', side_effect=Exception("发送失败")):
            await self.integrator.trigger_alert(state_change)
            
            # 验证失败回调被调用
            post_callback.assert_called_once_with(state_change, False)
    
    def test_add_and_remove_alert_filter(self):
        """测试添加和移除告警过滤器"""
        def test_filter(change):
            return True
        
        # 添加过滤器
        self.integrator.add_alert_filter(test_filter)
        assert len(self.integrator.alert_filters) == 1
        
        # 移除过滤器
        assert self.integrator.remove_alert_filter(test_filter) is True
        assert len(self.integrator.alert_filters) == 0
        
        # 移除不存在的过滤器
        assert self.integrator.remove_alert_filter(test_filter) is False
    
    def test_create_service_filter(self):
        """测试创建服务过滤器"""
        allowed_services = ['service1', 'service2']
        filter_func = self.integrator.create_service_filter(allowed_services)
        
        # 允许的服务
        change1 = StateChange('service1', 'redis', True, False)
        assert filter_func(change1) is True
        
        # 不允许的服务
        change2 = StateChange('service3', 'redis', True, False)
        assert filter_func(change2) is False
    
    def test_create_status_filter(self):
        """测试创建状态过滤器"""
        # 只允许DOWN告警
        filter_func = self.integrator.create_status_filter(alert_on_down=True, alert_on_up=False)
        
        # DOWN状态变化
        down_change = StateChange('service1', 'redis', True, False)
        assert filter_func(down_change) is True
        
        # UP状态变化
        up_change = StateChange('service1', 'redis', False, True)
        assert filter_func(up_change) is False
    
    def test_create_time_filter(self):
        """测试创建时间过滤器"""
        # 静默时间：22:00-06:00
        quiet_hours = [(22, 6)]
        filter_func = self.integrator.create_time_filter(quiet_hours)
        
        # 创建不同时间的状态变化
        # 23:00 - 应该被过滤
        night_change = StateChange('service1', 'redis', True, False, 
                                 timestamp=datetime(2023, 1, 1, 23, 0, 0))
        assert filter_func(night_change) is False
        
        # 10:00 - 不应该被过滤
        day_change = StateChange('service1', 'redis', True, False,
                               timestamp=datetime(2023, 1, 1, 10, 0, 0))
        assert filter_func(day_change) is True
    
    def test_get_alert_stats(self):
        """测试获取告警统计信息"""
        # 添加一些过滤器和回调
        self.integrator.add_alert_filter(lambda x: True)
        self.integrator.add_pre_alert_callback(lambda x: None)
        self.integrator.add_post_alert_callback(lambda x, y: None)
        
        stats = self.integrator.get_alert_stats()
        
        assert stats['alerter_count'] == 1
        assert stats['filter_count'] == 1
        assert stats['pre_callback_count'] == 1
        assert stats['post_callback_count'] == 1
        assert 'state_changes_count' in stats
    
    @pytest.mark.asyncio
    async def test_test_alert_system(self):
        """测试告警系统测试功能"""
        with patch.object(self.integrator, 'trigger_alert') as mock_trigger:
            result = await self.integrator.test_alert_system('test-service')
            
            assert result is True
            mock_trigger.assert_called_once()
            
            # 验证测试状态变化
            call_args = mock_trigger.call_args[0][0]
            assert call_args.service_name == 'test-service'
            assert call_args.service_type == 'test'
            assert call_args.old_state is True
            assert call_args.new_state is False
    
    @pytest.mark.asyncio
    async def test_test_alert_system_failure(self):
        """测试告警系统测试失败"""
        with patch.object(self.integrator, 'trigger_alert', side_effect=Exception("测试失败")):
            result = await self.integrator.test_alert_system()
            
            assert result is False
    
    def test_reload_alert_config(self):
        """测试重新加载告警配置"""
        # 初始状态
        assert self.integrator.alert_manager.get_alerter_count() == 1
        
        # 新配置
        new_configs = [
            {
                'name': 'new-webhook1',
                'type': 'http',
                'url': 'https://new1.example.com/webhook',
                'method': 'POST'
            },
            {
                'name': 'new-webhook2',
                'type': 'http',
                'url': 'https://new2.example.com/webhook',
                'method': 'POST'
            }
        ]
        
        self.integrator.reload_alert_config(new_configs)
        
        # 验证配置已更新
        assert self.integrator.alert_manager.get_alerter_count() == 2
        assert 'new-webhook1' in self.integrator.alert_manager.get_alerter_names()
        assert 'new-webhook2' in self.integrator.alert_manager.get_alerter_names()
    
    def test_get_recent_alerts(self):
        """测试获取最近的告警记录"""
        # 添加一些状态变化
        now = datetime.now()
        
        # 2小时前的变化
        old_change = StateChange(
            'service1', 'redis', True, False,
            timestamp=now - timedelta(hours=2)
        )
        self.state_manager.state_changes.append(old_change)
        
        # 1小时前的变化
        recent_change = StateChange(
            'service2', 'redis', True, False,
            timestamp=now - timedelta(hours=1)
        )
        self.state_manager.state_changes.append(recent_change)
        
        # 获取最近1.5小时的记录
        recent_alerts = self.integrator.get_recent_alerts(hours=1.5)
        
        assert len(recent_alerts) == 1
        assert recent_alerts[0].service_name == 'service2'