"""HTTP告警器集成测试"""

import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from health_monitor.alerts.manager import AlertManager
from health_monitor.alerts.http_alerter import HTTPAlerter
from health_monitor.models.health_check import StateChange


class TestHTTPAlerterIntegration:
    """HTTP告警器集成测试类"""
    
    def setup_method(self):
        """测试前准备"""
        self.alert_configs = [
            {
                'name': 'webhook-alert',
                'type': 'http',
                'url': 'https://hooks.slack.com/webhook',
                'method': 'POST',
                'headers': {
                    'Content-Type': 'application/json'
                },
                'template': '{"text": "🚨 服务告警\\n服务: $service_name\\n状态: $status\\n时间: $timestamp"}'
            }
        ]
        
        self.manager = AlertManager(self.alert_configs)
        
        self.state_change = StateChange(
            service_name='redis-cache',
            service_type='redis',
            old_state=True,
            new_state=False,
            error_message='连接超时'
        )
    
    @pytest.mark.asyncio
    async def test_manager_with_http_alerter_success(self):
        """测试告警管理器与HTTP告警器的成功集成"""
        # 创建HTTP告警器
        http_config = {
            'url': 'https://api.example.com/webhook',
            'method': 'POST',
            'headers': {'Content-Type': 'application/json'},
            'template': '{"message": "服务 $service_name 状态变为 $status"}'
        }
        
        alerter = HTTPAlerter('test-webhook', http_config)
        
        # 模拟成功的HTTP请求
        with patch.object(alerter, '_send_request', return_value=True) as mock_send:
            self.manager.add_alerter(alerter)
            
            await self.manager.send_alert(self.state_change)
            
            # 验证HTTP请求被调用
            mock_send.assert_called_once()
            
            # 验证传递的消息内容
            call_args = mock_send.call_args[0][0]  # 获取AlertMessage参数
            assert call_args.service_name == 'redis-cache'
            assert call_args.status == 'DOWN'
    
    @pytest.mark.asyncio
    async def test_manager_with_multiple_http_alerters(self):
        """测试告警管理器与多个HTTP告警器的集成"""
        # 创建两个HTTP告警器
        alerter1 = HTTPAlerter('webhook1', {
            'url': 'https://api1.example.com/webhook',
            'method': 'POST'
        })
        
        alerter2 = HTTPAlerter('webhook2', {
            'url': 'https://api2.example.com/webhook',
            'method': 'POST'
        })
        
        # 模拟HTTP请求
        with patch.object(alerter1, '_send_request', return_value=True) as mock_send1:
            with patch.object(alerter2, '_send_request', return_value=True) as mock_send2:
                self.manager.add_alerter(alerter1)
                self.manager.add_alerter(alerter2)
                
                await self.manager.send_alert(self.state_change)
                
                # 验证两个告警器都被调用
                mock_send1.assert_called_once()
                mock_send2.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_manager_with_http_alerter_partial_failure(self):
        """测试部分HTTP告警器失败的情况"""
        # 创建两个HTTP告警器
        alerter1 = HTTPAlerter('webhook1', {
            'url': 'https://api1.example.com/webhook',
            'method': 'POST'
        })
        
        alerter2 = HTTPAlerter('webhook2', {
            'url': 'https://api2.example.com/webhook',
            'method': 'POST'
        })
        
        # 第一个成功，第二个失败
        with patch.object(alerter1, '_send_request', return_value=True):
            with patch.object(alerter2, '_send_request', side_effect=Exception("发送失败")):
                self.manager.add_alerter(alerter1)
                self.manager.add_alerter(alerter2)
                
                # 应该不会抛出异常，即使部分失败
                await self.manager.send_alert(self.state_change)
    
    @pytest.mark.asyncio
    async def test_template_rendering_integration(self):
        """测试模板渲染的集成"""
        # 创建带有复杂模板的HTTP告警器
        template = '''
        {
            "service": "$service_name",
            "type": "$service_type", 
            "status": "$status",
            "time": "$timestamp",
            "error": "$error_message",
            "response_time": "$response_time",
            "old_state": "$metadata_old_state",
            "new_state": "$metadata_new_state"
        }
        '''
        
        alerter = HTTPAlerter('complex-webhook', {
            'url': 'https://api.example.com/webhook',
            'method': 'POST',
            'template': template.strip()
        })
        
        # 模拟HTTP请求并捕获请求数据
        captured_data = {}
        
        async def mock_send_request(message):
            request_data = alerter._prepare_request_data(message)
            captured_data.update(request_data)
            return True
        
        with patch.object(alerter, '_send_request', side_effect=mock_send_request):
            self.manager.add_alerter(alerter)
            
            await self.manager.send_alert(self.state_change)
            
            # 验证模板被正确渲染
            assert 'json' in captured_data
            json_data = captured_data['json']
            assert json_data['service'] == 'redis-cache'
            assert json_data['status'] == 'DOWN'
            assert json_data['old_state'] == 'True'
            assert json_data['new_state'] == 'False'
    
    def test_http_alerter_config_validation_in_manager(self):
        """测试告警管理器中HTTP告警器的配置验证"""
        # 尝试添加配置无效的HTTP告警器
        with pytest.raises(Exception):  # 应该在初始化时就失败
            invalid_alerter = HTTPAlerter('invalid', {
                'method': 'POST'  # 缺少URL
            })
    
    @pytest.mark.asyncio
    async def test_deduplication_with_http_alerter(self):
        """测试HTTP告警器的去重功能"""
        alerter = HTTPAlerter('test-webhook', {
            'url': 'https://api.example.com/webhook',
            'method': 'POST'
        })
        
        with patch.object(alerter, '_send_request', return_value=True) as mock_send:
            self.manager.add_alerter(alerter)
            
            # 发送第一个告警
            await self.manager.send_alert(self.state_change)
            assert mock_send.call_count == 1
            
            # 发送相同的告警（应该被去重）
            await self.manager.send_alert(self.state_change)
            assert mock_send.call_count == 1  # 没有增加
            
            # 发送不同状态的告警（不应该被去重）
            recovery_change = StateChange(
                service_name='redis-cache',
                service_type='redis',
                old_state=False,
                new_state=True
            )
            
            await self.manager.send_alert(recovery_change)
            assert mock_send.call_count == 2  # 增加了一次