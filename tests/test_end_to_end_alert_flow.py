"""端到端告警流程测试"""

import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from health_monitor.alerts.integrator import AlertIntegrator
from health_monitor.services.state_manager import StateManager
from health_monitor.models.health_check import HealthCheckResult


class TestEndToEndAlertFlow:
    """端到端告警流程测试类"""
    
    def setup_method(self):
        """测试前准备"""
        self.state_manager = StateManager()
        
        # 配置多个告警渠道
        self.alert_configs = [
            {
                'name': 'dingtalk-webhook',
                'type': 'http',
                'url': 'https://oapi.dingtalk.com/robot/send?access_token=test',
                'method': 'POST',
                'headers': {
                    'Content-Type': 'application/json'
                },
                'max_retries': 0,  # 禁用重试，简化测试
                'template': '''
                {
                    "msgtype": "text",
                    "text": {
                        "content": "🚨 服务告警\\n服务名称: {{service_name}}\\n服务类型: {{service_type}}\\n状态: {{status}}\\n时间: {{timestamp}}\\n错误信息: {{error_message}}"
                    }
                }
                '''.strip()
            },
            {
                'name': 'slack-webhook',
                'type': 'http',
                'url': 'https://hooks.slack.com/services/test/webhook',
                'method': 'POST',
                'headers': {
                    'Content-Type': 'application/json'
                },
                'max_retries': 0,  # 禁用重试，简化测试
                'template': '''
                {
                    "text": "Service Alert: $service_name is $status",
                    "attachments": [
                        {
                            "color": "danger",
                            "fields": [
                                {
                                    "title": "Service",
                                    "value": "$service_name",
                                    "short": true
                                },
                                {
                                    "title": "Status",
                                    "value": "$status",
                                    "short": true
                                },
                                {
                                    "title": "Error",
                                    "value": "$error_message",
                                    "short": false
                                }
                            ]
                        }
                    ]
                }
                '''.strip()
            }
        ]
        
        self.integrator = AlertIntegrator(self.state_manager, self.alert_configs)
    
    @pytest.mark.asyncio
    async def test_complete_alert_flow_service_down(self):
        """测试完整的服务DOWN告警流程"""
        # 模拟HTTP请求成功
        with patch('aiohttp.ClientSession') as mock_session_class:
            # 设置mock响应
            mock_response = Mock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"ok": True})
            mock_response.text = AsyncMock(return_value='{"ok": true}')
            
            # 创建异步上下文管理器Mock
            mock_request_context = AsyncMock()
            mock_request_context.__aenter__ = AsyncMock(return_value=mock_response)
            mock_request_context.__aexit__ = AsyncMock(return_value=None)
            
            # 创建session mock
            mock_session = Mock()
            mock_session.request = Mock(return_value=mock_request_context)
            
            # 创建session类的异步上下文管理器
            mock_session_context = AsyncMock()
            mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_context.__aexit__ = AsyncMock(return_value=None)
            
            mock_session_class.return_value = mock_session_context
            
            # 第一次健康检查 - 服务正常
            healthy_result = HealthCheckResult(
                service_name='redis-cache',
                service_type='redis',
                is_healthy=True,
                response_time=50.0,
                timestamp=datetime.now()
            )
            
            await self.integrator.process_health_check_result(healthy_result)
            
            # 验证没有告警发送（首次检查）
            assert mock_session.request.call_count == 0
            
            # 第二次健康检查 - 服务异常
            unhealthy_result = HealthCheckResult(
                service_name='redis-cache',
                service_type='redis',
                is_healthy=False,
                response_time=5000.0,
                error_message='连接超时',
                timestamp=datetime.now()
            )
            
            await self.integrator.process_health_check_result(unhealthy_result)
            
            # 验证告警被发送到两个渠道
            assert mock_session.request.call_count == 2
            
            # 验证请求参数
            calls = mock_session.request.call_args_list
            
            # 第一个请求（钉钉）
            dingtalk_call = calls[0]
            assert dingtalk_call[1]['url'] == 'https://oapi.dingtalk.com/robot/send?access_token=test'
            assert dingtalk_call[1]['method'] == 'POST'
            
            # 第二个请求（Slack）
            slack_call = calls[1]
            assert slack_call[1]['url'] == 'https://hooks.slack.com/services/test/webhook'
            assert slack_call[1]['method'] == 'POST'
    
    @pytest.mark.asyncio
    async def test_complete_alert_flow_service_recovery(self):
        """测试完整的服务恢复告警流程"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            # 设置mock
            mock_response = Mock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"ok": True})
            mock_response.text = AsyncMock(return_value='{"ok": true}')
            
            # 创建异步上下文管理器Mock
            mock_request_context = AsyncMock()
            mock_request_context.__aenter__ = AsyncMock(return_value=mock_response)
            mock_request_context.__aexit__ = AsyncMock(return_value=None)
            
            # 创建session mock
            mock_session = Mock()
            mock_session.request = Mock(return_value=mock_request_context)
            
            # 创建session类的异步上下文管理器
            mock_session_context = AsyncMock()
            mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_context.__aexit__ = AsyncMock(return_value=None)
            
            mock_session_class.return_value = mock_session_context
            
            # 建立初始状态：服务正常 -> 异常 -> 恢复
            results = [
                HealthCheckResult('mysql-db', 'mysql', True, 100.0),   # 正常
                HealthCheckResult('mysql-db', 'mysql', False, 0.0, '连接拒绝'),  # 异常
                HealthCheckResult('mysql-db', 'mysql', True, 120.0),   # 恢复
            ]
            
            for result in results:
                await self.integrator.process_health_check_result(result)
            
            # 应该发送两次告警：DOWN和UP
            assert mock_session.request.call_count == 4  # 2个告警器 × 2次状态变化
    
    @pytest.mark.asyncio
    async def test_alert_deduplication_in_flow(self):
        """测试告警流程中的去重功能"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            # 设置mock
            mock_response = Mock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"ok": True})
            mock_response.text = AsyncMock(return_value='{"ok": true}')
            
            # 创建异步上下文管理器Mock
            mock_request_context = AsyncMock()
            mock_request_context.__aenter__ = AsyncMock(return_value=mock_response)
            mock_request_context.__aexit__ = AsyncMock(return_value=None)
            
            # 创建session mock
            mock_session = Mock()
            mock_session.request = Mock(return_value=mock_request_context)
            
            # 创建session类的异步上下文管理器
            mock_session_context = AsyncMock()
            mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_context.__aexit__ = AsyncMock(return_value=None)
            
            mock_session_class.return_value = mock_session_context
            
            # 建立初始状态
            initial_result = HealthCheckResult('api-service', 'restful', True, 200.0)
            await self.integrator.process_health_check_result(initial_result)
            
            # 第一次DOWN
            down_result = HealthCheckResult('api-service', 'restful', False, 0.0, 'HTTP 500')
            await self.integrator.process_health_check_result(down_result)
            
            # 验证第一次告警发送
            first_call_count = mock_session.request.call_count
            assert first_call_count == 2  # 两个告警器
            
            # 再次DOWN（相同状态，应该被去重）
            down_result2 = HealthCheckResult('api-service', 'restful', False, 0.0, 'HTTP 500')
            await self.integrator.process_health_check_result(down_result2)
            
            # 验证没有新的告警发送（被去重）
            assert mock_session.request.call_count == first_call_count
    
    @pytest.mark.asyncio
    async def test_alert_flow_with_filters(self):
        """测试带过滤器的告警流程"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            # 设置mock
            mock_response = Mock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"ok": True})
            mock_response.text = AsyncMock(return_value='{"ok": true}')
            
            # 创建异步上下文管理器Mock
            mock_request_context = AsyncMock()
            mock_request_context.__aenter__ = AsyncMock(return_value=mock_response)
            mock_request_context.__aexit__ = AsyncMock(return_value=None)
            
            # 创建session mock
            mock_session = Mock()
            mock_session.request = Mock(return_value=mock_request_context)
            
            # 创建session类的异步上下文管理器
            mock_session_context = AsyncMock()
            mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_context.__aexit__ = AsyncMock(return_value=None)
            
            mock_session_class.return_value = mock_session_context
            
            # 添加服务过滤器，只允许critical服务告警
            critical_services = ['critical-db', 'critical-api']
            service_filter = self.integrator.create_service_filter(critical_services)
            self.integrator.add_alert_filter(service_filter)
            
            # 测试非关键服务（应该被过滤）
            non_critical_results = [
                HealthCheckResult('test-cache', 'redis', True, 50.0),
                HealthCheckResult('test-cache', 'redis', False, 0.0, '连接失败'),
            ]
            
            for result in non_critical_results:
                await self.integrator.process_health_check_result(result)
            
            # 验证没有告警发送
            assert mock_session.request.call_count == 0
            
            # 测试关键服务（应该发送告警）
            critical_results = [
                HealthCheckResult('critical-db', 'mysql', True, 100.0),
                HealthCheckResult('critical-db', 'mysql', False, 0.0, '数据库连接失败'),
            ]
            
            for result in critical_results:
                await self.integrator.process_health_check_result(result)
            
            # 验证关键服务的告警被发送
            assert mock_session.request.call_count == 2  # 两个告警器
    
    @pytest.mark.asyncio
    async def test_alert_flow_with_partial_failure(self):
        """测试部分告警器失败的流程"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            # 第一个告警器成功，第二个失败
            def create_mock_session(success):
                mock_response = Mock()
                mock_response.status = 200 if success else 500
                mock_response.json = AsyncMock(return_value={"ok": True} if success else {"error": "failed"})
                mock_response.text = AsyncMock(return_value='OK' if success else 'Error')
                
                # 创建异步上下文管理器Mock
                mock_request_context = AsyncMock()
                mock_request_context.__aenter__ = AsyncMock(return_value=mock_response)
                mock_request_context.__aexit__ = AsyncMock(return_value=None)
                
                # 创建session mock
                mock_session = Mock()
                mock_session.request = Mock(return_value=mock_request_context)
                
                # 创建session类的异步上下文管理器
                mock_session_context = AsyncMock()
                mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session_context.__aexit__ = AsyncMock(return_value=None)
                
                return mock_session_context, mock_session
            
            # 模拟两次调用，第一次成功，第二次失败
            success_context, success_session = create_mock_session(True)
            failure_context, failure_session = create_mock_session(False)
            
            mock_session_class.side_effect = [success_context, failure_context]
            
            # 触发告警
            results = [
                HealthCheckResult('service-x', 'redis', True, 50.0),
                HealthCheckResult('service-x', 'redis', False, 0.0, '连接超时'),
            ]
            
            for result in results:
                await self.integrator.process_health_check_result(result)
            
            # 验证两个告警器都被尝试调用
            assert success_session.request.call_count == 1
            assert failure_session.request.call_count == 1
    
    @pytest.mark.asyncio
    async def test_alert_flow_with_callbacks(self):
        """测试带回调的告警流程"""
        pre_alert_calls = []
        post_alert_calls = []
        
        def pre_alert_callback(state_change):
            pre_alert_calls.append(state_change.service_name)
        
        def post_alert_callback(state_change, success):
            post_alert_calls.append((state_change.service_name, success))
        
        self.integrator.add_pre_alert_callback(pre_alert_callback)
        self.integrator.add_post_alert_callback(post_alert_callback)
        
        with patch('aiohttp.ClientSession') as mock_session_class:
            # 设置mock
            mock_response = Mock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"ok": True})
            mock_response.text = AsyncMock(return_value='{"ok": true}')
            
            # 创建异步上下文管理器Mock
            mock_request_context = AsyncMock()
            mock_request_context.__aenter__ = AsyncMock(return_value=mock_response)
            mock_request_context.__aexit__ = AsyncMock(return_value=None)
            
            # 创建session mock
            mock_session = Mock()
            mock_session.request = Mock(return_value=mock_request_context)
            
            # 创建session类的异步上下文管理器
            mock_session_context = AsyncMock()
            mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_context.__aexit__ = AsyncMock(return_value=None)
            
            mock_session_class.return_value = mock_session_context
            
            # 触发告警
            results = [
                HealthCheckResult('callback-test', 'redis', True, 50.0),
                HealthCheckResult('callback-test', 'redis', False, 0.0, '测试错误'),
            ]
            
            for result in results:
                await self.integrator.process_health_check_result(result)
            
            # 验证回调被调用
            assert len(pre_alert_calls) == 1
            assert pre_alert_calls[0] == 'callback-test'
            
            assert len(post_alert_calls) == 1
            assert post_alert_calls[0][0] == 'callback-test'
            assert post_alert_calls[0][1] is True  # 成功