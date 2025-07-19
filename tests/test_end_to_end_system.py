"""端到端系统集成测试

测试完整的健康监控系统，包括所有服务类型的监控功能、告警系统的完整流程等
"""

import pytest
import asyncio
import tempfile
import os
import yaml
import time
from typing import Dict, Any, List
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path

from health_monitor.services.config_manager import ConfigManager
from health_monitor.services.monitor_scheduler import MonitorScheduler
from health_monitor.services.state_manager import StateManager
from health_monitor.alerts.integrator import AlertIntegrator
from health_monitor.models.health_check import HealthCheckResult
from health_monitor.utils.log_manager import log_manager


class TestEndToEndSystem:
    """端到端系统测试类"""
    
    @pytest.fixture
    def temp_config_file(self):
        """创建临时配置文件"""
        config_data = {
            'global': {
                'check_interval': 2,
                'log_level': 'INFO',
                'max_concurrent_checks': 5,
                'enable_performance_monitoring': True
            },
            'services': {
                'redis-cache': {
                    'type': 'redis',
                    'host': 'localhost',
                    'port': 6379,
                    'database': 0,
                    'timeout': 5,
                    'check_interval': 3,
                    'use_connection_pool': True
                },
                'user-database': {
                    'type': 'mysql',
                    'host': 'localhost',
                    'port': 3306,
                    'username': 'test_user',
                    'password': 'test_password',
                    'database': 'test_db',
                    'timeout': 10,
                    'check_interval': 5
                },
                'document-store': {
                    'type': 'mongodb',
                    'host': 'localhost',
                    'port': 27017,
                    'username': 'mongo_user',
                    'password': 'mongo_password',
                    'database': 'test_db',
                    'timeout': 8,
                    'check_interval': 4
                },
                'message-broker': {
                    'type': 'emqx',
                    'host': 'localhost',
                    'port': 1883,
                    'username': 'mqtt_user',
                    'password': 'mqtt_password',
                    'client_id': 'health_monitor_test',
                    'timeout': 10,
                    'check_interval': 6
                },
                'user-api': {
                    'type': 'restful',
                    'url': 'http://localhost:8080/health',
                    'method': 'GET',
                    'expected_status': 200,
                    'timeout': 5,
                    'check_interval': 3
                }
            },
            'alerts': [
                {
                    'name': 'webhook-alert',
                    'type': 'http',
                    'url': 'http://localhost:9999/webhook',
                    'method': 'POST',
                    'headers': {
                        'Content-Type': 'application/json'
                    },
                    'template': '''
                    {
                        "service": "{{service_name}}",
                        "status": "{{status}}",
                        "message": "{{error_message}}",
                        "timestamp": "{{timestamp}}"
                    }
                    '''
                }
            ]
        }
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f, default_flow_style=False)
            temp_file = f.name
        
        yield temp_file
        
        # 清理临时文件
        if os.path.exists(temp_file):
            os.unlink(temp_file)
    
    @pytest.fixture
    def temp_state_file(self):
        """创建临时状态文件"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_file = f.name
        
        yield temp_file
        
        # 清理临时文件
        if os.path.exists(temp_file):
            os.unlink(temp_file)
    
    @pytest.mark.asyncio
    async def test_complete_system_initialization(self, temp_config_file):
        """测试完整系统初始化"""
        # 配置日志系统
        log_manager.configure({
            'log_level': 'INFO',
            'enable_console': True,
            'enable_file': False
        })
        
        # 初始化配置管理器
        config_manager = ConfigManager(temp_config_file)
        config = config_manager.load_config()
        
        # 验证配置加载
        assert 'services' in config
        assert 'alerts' in config
        assert len(config['services']) == 5
        assert len(config['alerts']) == 1
        
        # 初始化状态管理器
        state_manager = StateManager()
        
        # 初始化监控调度器
        scheduler = MonitorScheduler(
            max_concurrent_checks=5,
            enable_performance_monitoring=True
        )
        
        # 配置服务
        services_config = config_manager.get_services_config()
        global_config = config_manager.get_global_config()
        scheduler.configure_services(services_config, global_config)
        
        # 验证服务配置
        assert len(scheduler.checkers) == 5
        assert 'redis-cache' in scheduler.checkers
        assert 'user-database' in scheduler.checkers
        assert 'document-store' in scheduler.checkers
        assert 'message-broker' in scheduler.checkers
        assert 'user-api' in scheduler.checkers
        
        # 初始化告警集成器
        alerts_config = config_manager.get_alerts_config()
        alert_integrator = AlertIntegrator(state_manager, alerts_config)
        
        # 验证告警配置
        assert len(alert_integrator.alert_manager.alerters) == 1
        
        print("✅ 完整系统初始化测试通过")
    
    @pytest.mark.asyncio
    async def test_all_service_types_monitoring(self, temp_config_file):
        """测试所有服务类型的监控功能"""
        # 模拟所有服务类型的健康检查
        mock_results = {
            'redis-cache': HealthCheckResult(
                service_name='redis-cache',
                service_type='redis',
                is_healthy=True,
                response_time=0.05,
                metadata={'ping_time': 0.02}
            ),
            'user-database': HealthCheckResult(
                service_name='user-database',
                service_type='mysql',
                is_healthy=True,
                response_time=0.08,
                metadata={'query_time': 0.06}
            ),
            'document-store': HealthCheckResult(
                service_name='document-store',
                service_type='mongodb',
                is_healthy=False,
                response_time=2.0,
                error_message='连接超时',
                metadata={'connection_error': True}
            ),
            'message-broker': HealthCheckResult(
                service_name='message-broker',
                service_type='emqx',
                is_healthy=True,
                response_time=0.12,
                metadata={'mqtt_connected': True}
            ),
            'user-api': HealthCheckResult(
                service_name='user-api',
                service_type='restful',
                is_healthy=True,
                response_time=0.15,
                metadata={'status_code': 200}
            )
        }
        
        # 初始化系统组件
        config_manager = ConfigManager(temp_config_file)
        config = config_manager.load_config()
        
        state_manager = StateManager()
        scheduler = MonitorScheduler(max_concurrent_checks=5)
        
        services_config = config_manager.get_services_config()
        global_config = config_manager.get_global_config()
        scheduler.configure_services(services_config, global_config)
        
        # 模拟健康检查结果
        collected_results = []
        
        async def mock_check_result_callback(result: HealthCheckResult):
            collected_results.append(result)
        
        scheduler.set_check_result_callback(mock_check_result_callback)
        
        # 模拟每个检查器的check_health方法
        for service_name, checker in scheduler.checkers.items():
            expected_result = mock_results[service_name]
            checker.check_health = AsyncMock(return_value=expected_result)
        
        # 执行一次完整的健康检查
        results = await scheduler.check_all_services_now()
        
        # 验证结果
        assert len(results) == 5
        
        # 验证每种服务类型都被检查了
        service_types = {result.service_type for result in results.values() if result}
        expected_types = {'redis', 'mysql', 'mongodb', 'emqx', 'restful'}
        assert service_types == expected_types
        
        # 验证健康和不健康的服务
        healthy_services = [name for name, result in results.items() 
                          if result and result.is_healthy]
        unhealthy_services = [name for name, result in results.items() 
                            if result and not result.is_healthy]
        
        assert len(healthy_services) == 4
        assert len(unhealthy_services) == 1
        assert 'document-store' in unhealthy_services
        
        print(f"✅ 所有服务类型监控测试通过")
        print(f"   健康服务: {healthy_services}")
        print(f"   不健康服务: {unhealthy_services}")
    
    @pytest.mark.asyncio
    async def test_complete_alert_flow(self, temp_config_file):
        """测试完整的告警流程"""
        # 初始化系统组件
        config_manager = ConfigManager(temp_config_file)
        config = config_manager.load_config()
        
        state_manager = StateManager()
        scheduler = MonitorScheduler(max_concurrent_checks=5)
        
        services_config = config_manager.get_services_config()
        global_config = config_manager.get_global_config()
        scheduler.configure_services(services_config, global_config)
        
        alerts_config = config_manager.get_alerts_config()
        alert_integrator = AlertIntegrator(state_manager, alerts_config)
        
        # 连接调度器和告警系统
        scheduler.set_check_result_callback(
            alert_integrator.process_health_check_result
        )
        
        # 模拟HTTP告警器
        sent_alerts = []
        
        async def mock_send_alert(alert_message):
            sent_alerts.append(alert_message)
            return True
        
        # 替换告警器的发送方法
        for alerter in alert_integrator.alert_manager.alerters:
            alerter.send_alert = mock_send_alert
        
        # 模拟服务状态变化场景
        test_scenarios = [
            # 场景1: 服务从健康变为不健康
            HealthCheckResult(
                service_name='redis-cache',
                service_type='redis',
                is_healthy=False,
                response_time=5.0,
                error_message='连接超时'
            ),
            # 场景2: 服务从不健康恢复为健康
            HealthCheckResult(
                service_name='redis-cache',
                service_type='redis',
                is_healthy=True,
                response_time=0.05
            ),
            # 场景3: 另一个服务出现问题
            HealthCheckResult(
                service_name='user-api',
                service_type='restful',
                is_healthy=False,
                response_time=10.0,
                error_message='HTTP 500 错误'
            )
        ]
        
        # 执行测试场景
        for i, result in enumerate(test_scenarios):
            await alert_integrator.process_health_check_result(result)
            
            # 等待告警处理
            await asyncio.sleep(0.1)
            
            print(f"场景 {i+1}: {result.service_name} -> {'健康' if result.is_healthy else '不健康'}")
        
        # 验证告警发送
        assert len(sent_alerts) >= 2  # 至少应该有2个告警（故障和恢复）
        
        # 验证告警内容
        alert_services = {alert.service_name for alert in sent_alerts}
        assert 'redis-cache' in alert_services
        assert 'user-api' in alert_services
        
        # 验证告警类型
        alert_statuses = {alert.status for alert in sent_alerts}
        assert 'DOWN' in alert_statuses  # 应该有故障告警
        assert 'UP' in alert_statuses    # 应该有恢复告警
        
        print(f"✅ 完整告警流程测试通过")
        print(f"   发送告警数量: {len(sent_alerts)}")
        print(f"   告警服务: {list(alert_services)}")
        print(f"   告警状态: {list(alert_statuses)}")
    
    @pytest.mark.asyncio
    async def test_concurrent_monitoring_performance(self, temp_config_file):
        """测试并发监控性能"""
        # 初始化系统
        config_manager = ConfigManager(temp_config_file)
        config = config_manager.load_config()
        
        scheduler = MonitorScheduler(
            max_concurrent_checks=3,  # 限制并发数
            enable_performance_monitoring=True
        )
        
        services_config = config_manager.get_services_config()
        global_config = config_manager.get_global_config()
        scheduler.configure_services(services_config, global_config)
        
        # 模拟检查器延迟
        for checker in scheduler.checkers.values():
            async def mock_check_with_delay():
                await asyncio.sleep(0.2)  # 200ms延迟
                return HealthCheckResult(
                    service_name=checker.name,
                    service_type=checker.config.get('type', 'unknown'),
                    is_healthy=True,
                    response_time=0.2
                )
            checker.check_health = mock_check_with_delay
        
        # 收集性能数据
        start_time = time.time()
        results = await scheduler.check_all_services_now()
        end_time = time.time()
        
        total_time = end_time - start_time
        
        # 验证并发效果
        # 如果是串行执行，5个服务 * 0.2秒 = 1秒
        # 如果是并发执行（限制3个），应该约为 0.4秒（2批次）
        assert total_time < 0.8  # 应该明显少于串行时间
        assert len(results) == 5
        
        # 获取性能指标
        if scheduler.performance_monitor:
            current_metrics = scheduler.performance_monitor.get_current_metrics()
            if current_metrics:
                print(f"当前CPU使用率: {current_metrics.cpu_percent:.1f}%")
                print(f"当前内存使用率: {current_metrics.memory_percent:.1f}%")
                print(f"活跃线程数: {current_metrics.active_threads}")
                print(f"活跃任务数: {current_metrics.active_tasks}")
        
        print(f"✅ 并发监控性能测试通过")
        print(f"   总执行时间: {total_time:.3f}秒")
        print(f"   检查服务数量: {len(results)}")
        print(f"   平均每服务时间: {total_time/len(results):.3f}秒")
    
    @pytest.mark.asyncio
    async def test_error_resilience(self, temp_config_file):
        """测试错误恢复能力"""
        # 初始化系统
        config_manager = ConfigManager(temp_config_file)
        config = config_manager.load_config()
        
        scheduler = MonitorScheduler(max_concurrent_checks=5)
        
        services_config = config_manager.get_services_config()
        global_config = config_manager.get_global_config()
        scheduler.configure_services(services_config, global_config)
        
        # 模拟部分服务检查失败
        success_count = 0
        error_count = 0
        
        for i, (service_name, checker) in enumerate(scheduler.checkers.items()):
            if i % 2 == 0:  # 偶数索引的服务正常
                async def mock_success_check():
                    nonlocal success_count
                    success_count += 1
                    return HealthCheckResult(
                        service_name=service_name,
                        service_type=checker.config.get('type', 'unknown'),
                        is_healthy=True,
                        response_time=0.1
                    )
                checker.check_health = mock_success_check
            else:  # 奇数索引的服务失败
                async def mock_error_check():
                    nonlocal error_count
                    error_count += 1
                    raise Exception(f"模拟 {service_name} 检查失败")
                checker.check_health = mock_error_check
        
        # 收集错误
        errors = []
        
        async def error_callback(service_name: str, error: Exception):
            errors.append((service_name, str(error)))
        
        scheduler.set_check_error_callback(error_callback)
        
        # 执行检查
        results = await scheduler.check_all_services_now()
        
        # 等待错误回调处理
        await asyncio.sleep(0.1)
        
        # 验证错误处理
        successful_results = [r for r in results.values() if r is not None]
        failed_results = [r for r in results.values() if r is None]
        
        assert len(successful_results) > 0  # 应该有成功的检查
        assert len(failed_results) > 0     # 应该有失败的检查
        assert len(errors) > 0             # 应该捕获到错误
        
        # 验证系统继续运行
        assert success_count > 0
        assert error_count > 0
        
        print(f"✅ 错误恢复能力测试通过")
        print(f"   成功检查: {len(successful_results)}")
        print(f"   失败检查: {len(failed_results)}")
        print(f"   捕获错误: {len(errors)}")
    
    @pytest.mark.asyncio
    async def test_configuration_reload(self, temp_config_file):
        """测试配置重新加载"""
        # 初始化系统
        config_manager = ConfigManager(temp_config_file)
        initial_config = config_manager.load_config()
        
        scheduler = MonitorScheduler(max_concurrent_checks=5)
        
        services_config = config_manager.get_services_config()
        global_config = config_manager.get_global_config()
        scheduler.configure_services(services_config, global_config)
        
        # 验证初始配置
        initial_service_count = len(scheduler.checkers)
        assert initial_service_count == 5
        
        # 修改配置文件（添加新服务）
        modified_config = initial_config.copy()
        modified_config['services']['new-service'] = {
            'type': 'restful',
            'url': 'http://localhost:8081/health',
            'method': 'GET',
            'expected_status': 200,
            'timeout': 5,
            'check_interval': 10
        }
        
        # 写入修改后的配置
        with open(temp_config_file, 'w') as f:
            yaml.dump(modified_config, f, default_flow_style=False)
        
        # 重新加载配置
        new_config = config_manager.load_config()
        new_services_config = config_manager.get_services_config()
        new_global_config = config_manager.get_global_config()
        
        # 重新配置调度器
        scheduler.configure_services(new_services_config, new_global_config)
        
        # 验证配置重新加载
        new_service_count = len(scheduler.checkers)
        assert new_service_count == 6  # 应该增加了一个服务
        assert 'new-service' in scheduler.checkers
        
        # 验证新服务的配置
        new_service_checker = scheduler.checkers['new-service']
        assert new_service_checker.config['type'] == 'restful'
        assert new_service_checker.config['url'] == 'http://localhost:8081/health'
        
        print(f"✅ 配置重新加载测试通过")
        print(f"   初始服务数量: {initial_service_count}")
        print(f"   重新加载后服务数量: {new_service_count}")
        print(f"   新增服务: new-service")
    
    @pytest.mark.asyncio
    async def test_long_running_stability(self, temp_config_file):
        """测试长时间运行稳定性"""
        # 初始化系统
        config_manager = ConfigManager(temp_config_file)
        config = config_manager.load_config()
        
        scheduler = MonitorScheduler(
            max_concurrent_checks=3,
            enable_performance_monitoring=True
        )
        
        services_config = config_manager.get_services_config()
        global_config = config_manager.get_global_config()
        scheduler.configure_services(services_config, global_config)
        
        # 模拟检查器
        check_counts = {name: 0 for name in scheduler.checkers.keys()}
        
        for service_name, checker in scheduler.checkers.items():
            def create_mock_check(svc_name, chk):
                async def mock_check():
                    nonlocal check_counts
                    check_counts[svc_name] += 1
                    await asyncio.sleep(0.1)  # 模拟检查时间
                    return HealthCheckResult(
                        service_name=svc_name,
                        service_type=chk.config.get('type', 'unknown'),
                        is_healthy=True,
                        response_time=0.1,
                        metadata={'check_count': check_counts[svc_name]}
                    )
                return mock_check
            checker.check_health = create_mock_check(service_name, checker)
        
        # 收集结果
        results = []
        
        async def collect_result(result: HealthCheckResult):
            results.append(result)
        
        scheduler.set_check_result_callback(collect_result)
        
        # 运行较短时间（模拟长时间运行）
        start_time = time.time()
        scheduler_task = asyncio.create_task(scheduler.start())
        
        # 运行10秒
        await asyncio.sleep(10)
        await scheduler.stop()
        scheduler_task.cancel()
        
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # 验证稳定性
        total_checks = len(results)
        assert total_checks > 10  # 应该执行了多次检查
        
        # 验证每个服务都被检查了
        service_check_counts = {}
        for result in results:
            service_name = result.service_name
            service_check_counts[service_name] = service_check_counts.get(service_name, 0) + 1
        
        assert len(service_check_counts) == 5  # 所有服务都应该被检查
        
        # 验证检查频率合理
        avg_checks_per_service = total_checks / len(service_check_counts)
        expected_min_checks = 2  # 至少每个服务检查2次
        
        for service_name, count in service_check_counts.items():
            assert count >= expected_min_checks, f"服务 {service_name} 检查次数过少: {count}"
        
        # 获取性能指标
        performance_stats = scheduler.get_scheduler_stats()
        
        print(f"✅ 长时间运行稳定性测试通过")
        print(f"   运行时间: {total_time:.2f}秒")
        print(f"   总检查次数: {total_checks}")
        print(f"   平均检查频率: {total_checks/total_time:.2f} 次/秒")
        print(f"   每服务平均检查次数: {avg_checks_per_service:.1f}")
        
        if 'current_performance' in performance_stats:
            perf = performance_stats['current_performance']
            print(f"   最终CPU使用率: {perf.get('cpu_percent', 0):.1f}%")
            print(f"   最终内存使用率: {perf.get('memory_percent', 0):.1f}%")
    
    @pytest.mark.asyncio
    async def test_state_persistence(self, temp_config_file, temp_state_file):
        """测试状态持久化"""
        # 第一阶段：创建状态并保存
        state_manager1 = StateManager(temp_state_file)
        
        # 模拟一些状态变化
        test_results = [
            HealthCheckResult(
                service_name='redis-cache',
                service_type='redis',
                is_healthy=True,
                response_time=0.05
            ),
            HealthCheckResult(
                service_name='user-database',
                service_type='mysql',
                is_healthy=False,
                response_time=5.0,
                error_message='连接超时'
            )
        ]
        
        for result in test_results:
            state_manager1.update_state(result)
        
        # 状态会自动保存，无需手动调用
        
        # 获取当前状态
        states1 = state_manager1.get_all_states()
        
        # 第二阶段：创建新的状态管理器（会自动加载状态）
        state_manager2 = StateManager(temp_state_file)
        
        # 获取加载的状态
        states2 = state_manager2.get_all_states()
        
        # 验证状态持久化
        assert len(states1) == len(states2)
        
        for service_name in states1:
            assert service_name in states2
            assert states1[service_name] == states2[service_name]
        
        print(f"✅ 状态持久化测试通过")
        print(f"   保存状态数量: {len(states1)}")
        print(f"   加载状态数量: {len(states2)}")
        print(f"   状态文件: {temp_state_file}")


if __name__ == "__main__":
    # 运行端到端测试
    pytest.main([__file__, "-v", "-s"])