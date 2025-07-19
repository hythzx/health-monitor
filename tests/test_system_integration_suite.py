"""系统集成测试套件

运行完整的系统集成测试，验证所有功能模块的协同工作
"""

import pytest
import asyncio
import tempfile
import os
import yaml
import time
from typing import Dict, Any, List
from unittest.mock import Mock, patch, AsyncMock

from health_monitor.services.config_manager import ConfigManager
from health_monitor.services.monitor_scheduler import MonitorScheduler
from health_monitor.services.state_manager import StateManager
from health_monitor.alerts.integrator import AlertIntegrator
from health_monitor.models.health_check import HealthCheckResult
from health_monitor.utils.log_manager import log_manager
from health_monitor.utils.performance_monitor import PerformanceMonitor


class SystemIntegrationTestSuite:
    """系统集成测试套件"""
    
    def __init__(self):
        self.test_results = {}
        self.temp_files = []
    
    def create_test_config(self) -> str:
        """创建测试配置文件"""
        config_data = {
            'global': {
                'check_interval': 1,
                'log_level': 'INFO',
                'max_concurrent_checks': 10,
                'enable_performance_monitoring': True
            },
            'services': {
                'redis-primary': {
                    'type': 'redis',
                    'host': 'localhost',
                    'port': 6379,
                    'database': 0,
                    'timeout': 5,
                    'check_interval': 2,
                    'use_connection_pool': True,
                    'test_operations': True
                },
                'mysql-main': {
                    'type': 'mysql',
                    'host': 'localhost',
                    'port': 3306,
                    'username': 'test_user',
                    'password': 'test_password',
                    'database': 'test_db',
                    'timeout': 10,
                    'check_interval': 3
                },
                'mongodb-docs': {
                    'type': 'mongodb',
                    'host': 'localhost',
                    'port': 27017,
                    'username': 'mongo_user',
                    'password': 'mongo_password',
                    'database': 'test_db',
                    'timeout': 8,
                    'check_interval': 2
                },
                'emqx-broker': {
                    'type': 'emqx',
                    'host': 'localhost',
                    'port': 1883,
                    'username': 'mqtt_user',
                    'password': 'mqtt_password',
                    'client_id': 'health_monitor_integration_test',
                    'timeout': 10,
                    'check_interval': 4
                },
                'api-gateway': {
                    'type': 'restful',
                    'url': 'http://localhost:8080/health',
                    'method': 'GET',
                    'expected_status': 200,
                    'timeout': 5,
                    'check_interval': 2,
                    'headers': {
                        'User-Agent': 'HealthMonitor/1.0'
                    }
                },
                'user-service': {
                    'type': 'restful',
                    'url': 'http://localhost:8081/api/health',
                    'method': 'GET',
                    'expected_status': 200,
                    'timeout': 3,
                    'check_interval': 3
                }
            },
            'alerts': [
                {
                    'name': 'primary-webhook',
                    'type': 'http',
                    'url': 'http://localhost:9999/webhook/primary',
                    'method': 'POST',
                    'headers': {
                        'Content-Type': 'application/json',
                        'X-Alert-Source': 'health-monitor'
                    },
                    'template': '''
                    {
                        "service": "{{service_name}}",
                        "status": "{{status}}",
                        "message": "{{error_message}}",
                        "timestamp": "{{timestamp}}",
                        "response_time": "{{response_time}}"
                    }
                    '''
                },
                {
                    'name': 'backup-webhook',
                    'type': 'http',
                    'url': 'http://localhost:9998/webhook/backup',
                    'method': 'POST',
                    'headers': {
                        'Content-Type': 'application/json'
                    },
                    'template': '''
                    {
                        "alert": "{{service_name}} is {{status}}",
                        "details": "{{error_message}}",
                        "time": "{{timestamp}}"
                    }
                    '''
                }
            ]
        }
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f, default_flow_style=False)
            temp_file = f.name
        
        self.temp_files.append(temp_file)
        return temp_file
    
    async def test_complete_system_workflow(self) -> Dict[str, Any]:
        """测试完整的系统工作流程"""
        print("🚀 开始完整系统工作流程测试...")
        
        config_file = self.create_test_config()
        test_result = {
            'test_name': 'complete_system_workflow',
            'success': False,
            'details': {},
            'errors': []
        }
        
        try:
            # 1. 系统初始化
            print("   📋 初始化系统组件...")
            config_manager = ConfigManager(config_file)
            config = config_manager.load_config()
            
            state_manager = StateManager()
            scheduler = MonitorScheduler(
                max_concurrent_checks=5,
                enable_performance_monitoring=True
            )
            
            services_config = config_manager.get_services_config()
            global_config = config_manager.get_global_config()
            scheduler.configure_services(services_config, global_config)
            
            alerts_config = config_manager.get_alerts_config()
            alert_integrator = AlertIntegrator(state_manager, alerts_config)
            
            # 连接组件
            scheduler.set_check_result_callback(
                alert_integrator.process_health_check_result
            )
            
            test_result['details']['initialization'] = {
                'services_count': len(scheduler.checkers),
                'alerters_count': len(alert_integrator.alert_manager.alerters),
                'performance_monitoring': scheduler.enable_performance_monitoring
            }
            
            # 2. 模拟服务健康检查
            print("   🔍 模拟服务健康检查...")
            mock_results = self._create_mock_health_results()
            
            for service_name, checker in scheduler.checkers.items():
                expected_result = mock_results.get(service_name)
                if expected_result:
                    checker.check_health = AsyncMock(return_value=expected_result)
            
            # 3. 执行健康检查
            print("   ⚡ 执行健康检查...")
            start_time = time.time()
            results = await scheduler.check_all_services_now()
            check_time = time.time() - start_time
            
            test_result['details']['health_checks'] = {
                'total_services': len(results),
                'successful_checks': len([r for r in results.values() if r and r.is_healthy]),
                'failed_checks': len([r for r in results.values() if r and not r.is_healthy]),
                'check_time': check_time
            }
            
            # 4. 验证告警系统
            print("   🚨 测试告警系统...")
            sent_alerts = []
            
            async def mock_send_alert(alert_message):
                sent_alerts.append(alert_message)
                return True
            
            for alerter in alert_integrator.alert_manager.alerters:
                alerter.send_alert = mock_send_alert
            
            # 触发一些状态变化
            await self._trigger_state_changes(alert_integrator)
            
            test_result['details']['alerts'] = {
                'alerts_sent': len(sent_alerts),
                'alert_services': list({alert.service_name for alert in sent_alerts})
            }
            
            # 5. 性能监控验证
            print("   📊 验证性能监控...")
            if scheduler.performance_monitor:
                current_metrics = scheduler.performance_monitor.get_current_metrics()
                test_result['details']['performance'] = {
                    'monitoring_enabled': True,
                    'current_cpu': current_metrics.cpu_percent if current_metrics else 0,
                    'current_memory': current_metrics.memory_percent if current_metrics else 0
                }
            else:
                test_result['details']['performance'] = {'monitoring_enabled': False}
            
            # 6. 并发性能测试
            print("   🏃 并发性能测试...")
            concurrent_start = time.time()
            concurrent_results = await asyncio.gather(*[
                scheduler.check_service_now(service_name)
                for service_name in list(scheduler.checkers.keys())[:3]  # 测试前3个服务
            ])
            concurrent_time = time.time() - concurrent_start
            
            test_result['details']['concurrent_performance'] = {
                'concurrent_checks': len(concurrent_results),
                'concurrent_time': concurrent_time,
                'avg_time_per_check': concurrent_time / len(concurrent_results) if concurrent_results else 0
            }
            
            test_result['success'] = True
            print("   ✅ 完整系统工作流程测试成功!")
            
        except Exception as e:
            test_result['errors'].append(str(e))
            print(f"   ❌ 完整系统工作流程测试失败: {e}")
        
        return test_result
    
    def _create_mock_health_results(self) -> Dict[str, HealthCheckResult]:
        """创建模拟健康检查结果"""
        return {
            'redis-primary': HealthCheckResult(
                service_name='redis-primary',
                service_type='redis',
                is_healthy=True,
                response_time=0.05,
                metadata={'ping_time': 0.02, 'operations_test': 'passed'}
            ),
            'mysql-main': HealthCheckResult(
                service_name='mysql-main',
                service_type='mysql',
                is_healthy=True,
                response_time=0.12,
                metadata={'query_time': 0.08}
            ),
            'mongodb-docs': HealthCheckResult(
                service_name='mongodb-docs',
                service_type='mongodb',
                is_healthy=False,
                response_time=5.0,
                error_message='连接超时',
                metadata={'connection_error': True}
            ),
            'emqx-broker': HealthCheckResult(
                service_name='emqx-broker',
                service_type='emqx',
                is_healthy=True,
                response_time=0.18,
                metadata={'mqtt_connected': True, 'client_id': 'health_monitor_integration_test'}
            ),
            'api-gateway': HealthCheckResult(
                service_name='api-gateway',
                service_type='restful',
                is_healthy=True,
                response_time=0.25,
                metadata={'status_code': 200, 'content_length': 156}
            ),
            'user-service': HealthCheckResult(
                service_name='user-service',
                service_type='restful',
                is_healthy=False,
                response_time=10.0,
                error_message='HTTP 503 Service Unavailable',
                metadata={'status_code': 503}
            )
        }
    
    async def _trigger_state_changes(self, alert_integrator: AlertIntegrator):
        """触发状态变化以测试告警系统"""
        # 模拟服务故障
        failure_result = HealthCheckResult(
            service_name='redis-primary',
            service_type='redis',
            is_healthy=False,
            response_time=5.0,
            error_message='连接被拒绝'
        )
        await alert_integrator.process_health_check_result(failure_result)
        
        # 等待一下
        await asyncio.sleep(0.1)
        
        # 模拟服务恢复
        recovery_result = HealthCheckResult(
            service_name='redis-primary',
            service_type='redis',
            is_healthy=True,
            response_time=0.05
        )
        await alert_integrator.process_health_check_result(recovery_result)
    
    async def test_stress_performance(self) -> Dict[str, Any]:
        """压力性能测试"""
        print("🔥 开始压力性能测试...")
        
        config_file = self.create_test_config()
        test_result = {
            'test_name': 'stress_performance',
            'success': False,
            'details': {},
            'errors': []
        }
        
        try:
            # 创建大量服务配置
            config_manager = ConfigManager(config_file)
            config = config_manager.load_config()
            
            # 添加更多服务进行压力测试
            additional_services = {}
            for i in range(20):  # 添加20个额外的服务
                additional_services[f'stress-service-{i}'] = {
                    'type': 'restful',
                    'url': f'http://localhost:808{i % 10}/health',
                    'method': 'GET',
                    'expected_status': 200,
                    'timeout': 2,
                    'check_interval': 1
                }
            
            config['services'].update(additional_services)
            
            # 初始化调度器
            scheduler = MonitorScheduler(
                max_concurrent_checks=10,
                enable_performance_monitoring=True
            )
            
            services_config = config.get('services', {})
            global_config = config.get('global', {})
            scheduler.configure_services(services_config, global_config)
            
            # 模拟所有服务的检查器
            for service_name, checker in scheduler.checkers.items():
                async def mock_stress_check():
                    await asyncio.sleep(0.1)  # 模拟检查延迟
                    return HealthCheckResult(
                        service_name=service_name,
                        service_type=checker.config.get('type', 'unknown'),
                        is_healthy=True,
                        response_time=0.1
                    )
                checker.check_health = mock_stress_check
            
            # 执行压力测试
            print(f"   📈 测试 {len(scheduler.checkers)} 个服务的并发检查...")
            
            start_time = time.time()
            results = await scheduler.check_all_services_now()
            end_time = time.time()
            
            total_time = end_time - start_time
            successful_checks = len([r for r in results.values() if r and r.is_healthy])
            
            # 获取性能指标
            performance_stats = {}
            if scheduler.performance_monitor:
                current_metrics = scheduler.performance_monitor.get_current_metrics()
                if current_metrics:
                    performance_stats = {
                        'cpu_percent': current_metrics.cpu_percent,
                        'memory_percent': current_metrics.memory_percent,
                        'active_threads': current_metrics.active_threads,
                        'active_tasks': current_metrics.active_tasks
                    }
            
            test_result['details'] = {
                'total_services': len(scheduler.checkers),
                'successful_checks': successful_checks,
                'total_time': total_time,
                'throughput': len(results) / total_time if total_time > 0 else 0,
                'avg_response_time': total_time / len(results) if results else 0,
                'performance_stats': performance_stats
            }
            
            # 验证性能要求
            if total_time < 5.0 and successful_checks == len(scheduler.checkers):
                test_result['success'] = True
                print(f"   ✅ 压力性能测试成功! 处理 {len(results)} 个服务用时 {total_time:.2f}秒")
            else:
                test_result['errors'].append(f"性能不达标: 时间={total_time:.2f}s, 成功率={successful_checks}/{len(scheduler.checkers)}")
                print(f"   ❌ 压力性能测试失败")
            
        except Exception as e:
            test_result['errors'].append(str(e))
            print(f"   ❌ 压力性能测试异常: {e}")
        
        return test_result
    
    async def test_fault_tolerance(self) -> Dict[str, Any]:
        """容错能力测试"""
        print("🛡️ 开始容错能力测试...")
        
        config_file = self.create_test_config()
        test_result = {
            'test_name': 'fault_tolerance',
            'success': False,
            'details': {},
            'errors': []
        }
        
        try:
            config_manager = ConfigManager(config_file)
            config = config_manager.load_config()
            
            scheduler = MonitorScheduler(max_concurrent_checks=5)
            
            services_config = config_manager.get_services_config()
            global_config = config_manager.get_global_config()
            scheduler.configure_services(services_config, global_config)
            
            # 模拟各种故障场景
            failure_scenarios = {
                'redis-primary': Exception("连接被拒绝"),
                'mysql-main': Exception("数据库锁定"),
                'mongodb-docs': Exception("认证失败"),
                'emqx-broker': HealthCheckResult(
                    service_name='emqx-broker',
                    service_type='emqx',
                    is_healthy=True,
                    response_time=0.1
                ),
                'api-gateway': Exception("网络超时"),
                'user-service': HealthCheckResult(
                    service_name='user-service',
                    service_type='restful',
                    is_healthy=True,
                    response_time=0.2
                )
            }
            
            # 设置模拟检查器
            for service_name, checker in scheduler.checkers.items():
                scenario = failure_scenarios.get(service_name)
                if isinstance(scenario, Exception):
                    async def mock_failing_check():
                        raise scenario
                    checker.check_health = mock_failing_check
                else:
                    checker.check_health = AsyncMock(return_value=scenario)
            
            # 收集错误
            errors_caught = []
            
            async def error_callback(service_name: str, error: Exception):
                errors_caught.append((service_name, str(error)))
            
            scheduler.set_check_error_callback(error_callback)
            
            # 执行检查
            results = await scheduler.check_all_services_now()
            
            # 等待错误处理
            await asyncio.sleep(0.2)
            
            # 分析结果
            successful_results = [r for r in results.values() if r is not None]
            failed_results = [r for r in results.values() if r is None]
            
            test_result['details'] = {
                'total_services': len(scheduler.checkers),
                'successful_checks': len(successful_results),
                'failed_checks': len(failed_results),
                'errors_caught': len(errors_caught),
                'error_services': [error[0] for error in errors_caught]
            }
            
            # 验证容错能力
            if len(successful_results) > 0 and len(errors_caught) > 0:
                test_result['success'] = True
                print(f"   ✅ 容错能力测试成功! 成功处理 {len(successful_results)} 个服务，捕获 {len(errors_caught)} 个错误")
            else:
                test_result['errors'].append("容错能力不足")
                print("   ❌ 容错能力测试失败")
            
        except Exception as e:
            test_result['errors'].append(str(e))
            print(f"   ❌ 容错能力测试异常: {e}")
        
        return test_result
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """运行所有集成测试"""
        print("🎯 开始运行系统集成测试套件...")
        print("=" * 60)
        
        # 配置日志
        log_manager.configure({
            'log_level': 'INFO',
            'enable_console': True,
            'enable_file': False
        })
        
        all_results = {
            'suite_name': 'SystemIntegrationTestSuite',
            'start_time': time.time(),
            'tests': [],
            'summary': {}
        }
        
        # 运行各项测试
        tests = [
            self.test_complete_system_workflow,
            self.test_stress_performance,
            self.test_fault_tolerance
        ]
        
        for test_func in tests:
            try:
                result = await test_func()
                all_results['tests'].append(result)
            except Exception as e:
                error_result = {
                    'test_name': test_func.__name__,
                    'success': False,
                    'details': {},
                    'errors': [str(e)]
                }
                all_results['tests'].append(error_result)
        
        # 生成总结
        all_results['end_time'] = time.time()
        all_results['total_time'] = all_results['end_time'] - all_results['start_time']
        
        successful_tests = [t for t in all_results['tests'] if t['success']]
        failed_tests = [t for t in all_results['tests'] if not t['success']]
        
        all_results['summary'] = {
            'total_tests': len(all_results['tests']),
            'successful_tests': len(successful_tests),
            'failed_tests': len(failed_tests),
            'success_rate': len(successful_tests) / len(all_results['tests']) * 100 if all_results['tests'] else 0
        }
        
        # 清理临时文件
        self.cleanup()
        
        return all_results
    
    def cleanup(self):
        """清理临时文件"""
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except Exception:
                pass
        self.temp_files.clear()
    
    def print_results(self, results: Dict[str, Any]):
        """打印测试结果"""
        print("\n" + "=" * 60)
        print("📊 系统集成测试结果报告")
        print("=" * 60)
        
        summary = results['summary']
        print(f"总测试数量: {summary['total_tests']}")
        print(f"成功测试: {summary['successful_tests']}")
        print(f"失败测试: {summary['failed_tests']}")
        print(f"成功率: {summary['success_rate']:.1f}%")
        print(f"总耗时: {results['total_time']:.2f}秒")
        
        print("\n📋 详细测试结果:")
        for test in results['tests']:
            status = "✅ 通过" if test['success'] else "❌ 失败"
            print(f"  {test['test_name']}: {status}")
            
            if test['details']:
                for key, value in test['details'].items():
                    if isinstance(value, dict):
                        print(f"    {key}:")
                        for sub_key, sub_value in value.items():
                            print(f"      {sub_key}: {sub_value}")
                    else:
                        print(f"    {key}: {value}")
            
            if test['errors']:
                print(f"    错误信息:")
                for error in test['errors']:
                    print(f"      - {error}")
            print()
        
        # 总体评估
        if summary['success_rate'] >= 80:
            print("🎉 系统集成测试总体评估: 优秀")
        elif summary['success_rate'] >= 60:
            print("⚠️  系统集成测试总体评估: 良好")
        else:
            print("🚨 系统集成测试总体评估: 需要改进")


async def main():
    """主函数"""
    suite = SystemIntegrationTestSuite()
    
    try:
        results = await suite.run_all_tests()
        suite.print_results(results)
        
        # 返回适当的退出码
        if results['summary']['success_rate'] >= 80:
            return 0
        else:
            return 1
            
    except Exception as e:
        print(f"❌ 测试套件执行失败: {e}")
        return 1
    finally:
        suite.cleanup()


if __name__ == "__main__":
    import sys
    exit_code = asyncio.run(main())
    sys.exit(exit_code)