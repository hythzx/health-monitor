"""性能基准测试

测试系统在不同负载下的性能表现
"""

import pytest
import asyncio
import time
import statistics
from typing import List, Dict, Any
from unittest.mock import Mock, patch

from health_monitor.services.monitor_scheduler import MonitorScheduler
from health_monitor.checkers.base import BaseHealthChecker
from health_monitor.models.health_check import HealthCheckResult
from health_monitor.utils.performance_monitor import PerformanceMonitor


class MockHealthChecker(BaseHealthChecker):
    """模拟健康检查器，用于基准测试"""
    
    def __init__(self, name: str, config: Dict[str, Any], delay: float = 0.1):
        super().__init__(name, config)
        self.delay = delay  # 模拟检查延迟
        self.check_count = 0
    
    def validate_config(self) -> bool:
        return True
    
    async def check_health(self) -> HealthCheckResult:
        """模拟健康检查"""
        self.check_count += 1
        start_time = time.time()
        
        # 模拟检查延迟
        await asyncio.sleep(self.delay)
        
        response_time = time.time() - start_time
        
        return HealthCheckResult(
            service_name=self.name,
            service_type='mock',
            is_healthy=True,
            response_time=response_time,
            metadata={'check_count': self.check_count}
        )


class TestPerformanceBenchmark:
    """性能基准测试类"""
    
    @pytest.mark.asyncio
    async def test_single_service_performance(self):
        """测试单个服务的性能"""
        scheduler = MonitorScheduler(max_concurrent_checks=1)
        
        # 创建模拟检查器
        checker = MockHealthChecker('test_service', {'type': 'mock'}, delay=0.05)
        scheduler.checkers['test_service'] = checker
        scheduler.check_intervals['test_service'] = 1  # 1秒间隔
        
        # 收集性能数据
        results = []
        
        def collect_result(result: HealthCheckResult):
            results.append(result)
        
        scheduler.set_check_result_callback(collect_result)
        
        # 运行5秒
        start_time = time.time()
        scheduler_task = asyncio.create_task(scheduler.start())
        
        await asyncio.sleep(5)
        await scheduler.stop()
        scheduler_task.cancel()
        
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        
        # 分析结果
        total_time = time.time() - start_time
        total_checks = len(results)
        
        if total_checks > 0:
            response_times = [r.response_time for r in results]
            avg_response_time = statistics.mean(response_times)
            max_response_time = max(response_times)
            min_response_time = min(response_times)
            
            print(f"\n单服务性能测试结果:")
            print(f"总运行时间: {total_time:.2f}秒")
            print(f"总检查次数: {total_checks}")
            print(f"检查频率: {total_checks/total_time:.2f} 次/秒")
            print(f"平均响应时间: {avg_response_time:.3f}秒")
            print(f"最大响应时间: {max_response_time:.3f}秒")
            print(f"最小响应时间: {min_response_time:.3f}秒")
            
            # 断言性能要求
            assert avg_response_time < 0.1  # 平均响应时间小于100ms
            assert max_response_time < 0.2  # 最大响应时间小于200ms
            assert total_checks >= 4  # 至少执行4次检查
    
    @pytest.mark.asyncio
    async def test_multiple_services_performance(self):
        """测试多个服务的并发性能"""
        scheduler = MonitorScheduler(max_concurrent_checks=5)
        
        # 创建多个模拟检查器
        service_count = 10
        for i in range(service_count):
            service_name = f'service_{i}'
            checker = MockHealthChecker(service_name, {'type': 'mock'}, delay=0.1)
            scheduler.checkers[service_name] = checker
            scheduler.check_intervals[service_name] = 2  # 2秒间隔
        
        # 收集性能数据
        results = []
        
        def collect_result(result: HealthCheckResult):
            results.append(result)
        
        scheduler.set_check_result_callback(collect_result)
        
        # 运行10秒
        start_time = time.time()
        scheduler_task = asyncio.create_task(scheduler.start())
        
        await asyncio.sleep(10)
        await scheduler.stop()
        scheduler_task.cancel()
        
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        
        # 分析结果
        total_time = time.time() - start_time
        total_checks = len(results)
        
        if total_checks > 0:
            # 按服务分组统计
            service_stats = {}
            for result in results:
                service_name = result.service_name
                if service_name not in service_stats:
                    service_stats[service_name] = []
                service_stats[service_name].append(result.response_time)
            
            print(f"\n多服务并发性能测试结果:")
            print(f"服务数量: {service_count}")
            print(f"总运行时间: {total_time:.2f}秒")
            print(f"总检查次数: {total_checks}")
            print(f"平均检查频率: {total_checks/total_time:.2f} 次/秒")
            print(f"每服务平均检查次数: {total_checks/service_count:.1f}")
            
            # 计算整体响应时间统计
            all_response_times = [r.response_time for r in results]
            avg_response_time = statistics.mean(all_response_times)
            max_response_time = max(all_response_times)
            
            print(f"平均响应时间: {avg_response_time:.3f}秒")
            print(f"最大响应时间: {max_response_time:.3f}秒")
            
            # 验证每个服务都被检查了
            assert len(service_stats) == service_count
            
            # 断言性能要求
            assert avg_response_time < 0.15  # 平均响应时间小于150ms
            assert max_response_time < 0.3   # 最大响应时间小于300ms
            assert total_checks >= service_count * 3  # 每个服务至少检查3次
    
    @pytest.mark.asyncio
    async def test_concurrent_limit_performance(self):
        """测试并发限制的性能影响"""
        # 测试不同并发限制下的性能
        concurrent_limits = [1, 3, 5, 10]
        results_by_limit = {}
        
        for limit in concurrent_limits:
            scheduler = MonitorScheduler(max_concurrent_checks=limit)
            
            # 创建20个服务
            service_count = 20
            for i in range(service_count):
                service_name = f'service_{i}'
                checker = MockHealthChecker(service_name, {'type': 'mock'}, delay=0.1)
                scheduler.checkers[service_name] = checker
                scheduler.check_intervals[service_name] = 1  # 1秒间隔
            
            # 收集结果
            results = []
            
            def collect_result(result: HealthCheckResult):
                results.append(result)
            
            scheduler.set_check_result_callback(collect_result)
            
            # 运行5秒
            start_time = time.time()
            scheduler_task = asyncio.create_task(scheduler.start())
            
            await asyncio.sleep(5)
            await scheduler.stop()
            scheduler_task.cancel()
            
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass
            
            # 统计结果
            total_time = time.time() - start_time
            total_checks = len(results)
            throughput = total_checks / total_time if total_time > 0 else 0
            
            results_by_limit[limit] = {
                'total_checks': total_checks,
                'total_time': total_time,
                'throughput': throughput,
                'avg_response_time': statistics.mean([r.response_time for r in results]) if results else 0
            }
        
        # 分析不同并发限制的性能
        print(f"\n并发限制性能对比:")
        print(f"{'并发限制':<8} {'总检查数':<8} {'吞吐量(次/秒)':<12} {'平均响应时间(秒)':<15}")
        print("-" * 50)
        
        for limit in concurrent_limits:
            stats = results_by_limit[limit]
            print(f"{limit:<8} {stats['total_checks']:<8} {stats['throughput']:<12.2f} {stats['avg_response_time']:<15.3f}")
        
        # 验证并发限制的效果
        # 更高的并发限制应该带来更高的吞吐量（在一定范围内）
        assert results_by_limit[5]['throughput'] > results_by_limit[1]['throughput']
        assert results_by_limit[10]['throughput'] >= results_by_limit[5]['throughput']
    
    @pytest.mark.asyncio
    async def test_performance_monitor_overhead(self):
        """测试性能监控的开销"""
        # 测试启用和禁用性能监控的性能差异
        test_duration = 5
        service_count = 10
        
        async def run_test_with_monitoring(enable_monitoring: bool) -> Dict[str, Any]:
            scheduler = MonitorScheduler(
                max_concurrent_checks=5,
                enable_performance_monitoring=enable_monitoring
            )
            
            # 创建服务
            for i in range(service_count):
                service_name = f'service_{i}'
                checker = MockHealthChecker(service_name, {'type': 'mock'}, delay=0.05)
                scheduler.checkers[service_name] = checker
                scheduler.check_intervals[service_name] = 1
            
            # 收集结果
            results = []
            
            def collect_result(result: HealthCheckResult):
                results.append(result)
            
            scheduler.set_check_result_callback(collect_result)
            
            # 运行测试
            start_time = time.time()
            scheduler_task = asyncio.create_task(scheduler.start())
            
            await asyncio.sleep(test_duration)
            await scheduler.stop()
            scheduler_task.cancel()
            
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass
            
            total_time = time.time() - start_time
            
            return {
                'total_checks': len(results),
                'total_time': total_time,
                'throughput': len(results) / total_time if total_time > 0 else 0,
                'avg_response_time': statistics.mean([r.response_time for r in results]) if results else 0
            }
        
        # 测试禁用性能监控
        stats_without_monitoring = await run_test_with_monitoring(False)
        
        # 测试启用性能监控
        stats_with_monitoring = await run_test_with_monitoring(True)
        
        print(f"\n性能监控开销测试:")
        print(f"{'配置':<15} {'总检查数':<8} {'吞吐量(次/秒)':<12} {'平均响应时间(秒)':<15}")
        print("-" * 55)
        print(f"{'禁用监控':<15} {stats_without_monitoring['total_checks']:<8} "
              f"{stats_without_monitoring['throughput']:<12.2f} {stats_without_monitoring['avg_response_time']:<15.3f}")
        print(f"{'启用监控':<15} {stats_with_monitoring['total_checks']:<8} "
              f"{stats_with_monitoring['throughput']:<12.2f} {stats_with_monitoring['avg_response_time']:<15.3f}")
        
        # 计算性能开销
        throughput_overhead = (stats_without_monitoring['throughput'] - stats_with_monitoring['throughput']) / stats_without_monitoring['throughput'] * 100
        response_time_overhead = (stats_with_monitoring['avg_response_time'] - stats_without_monitoring['avg_response_time']) / stats_without_monitoring['avg_response_time'] * 100
        
        print(f"\n性能开销:")
        print(f"吞吐量下降: {throughput_overhead:.1f}%")
        print(f"响应时间增加: {response_time_overhead:.1f}%")
        
        # 验证性能监控的开销在可接受范围内
        assert throughput_overhead < 20  # 吞吐量下降不超过20%
        assert response_time_overhead < 15  # 响应时间增加不超过15%
    
    @pytest.mark.asyncio
    async def test_memory_usage_stability(self):
        """测试内存使用稳定性"""
        import psutil
        import gc
        
        scheduler = MonitorScheduler(max_concurrent_checks=5, enable_performance_monitoring=True)
        
        # 创建服务
        service_count = 15
        for i in range(service_count):
            service_name = f'service_{i}'
            checker = MockHealthChecker(service_name, {'type': 'mock'}, delay=0.1)
            scheduler.checkers[service_name] = checker
            scheduler.check_intervals[service_name] = 2
        
        # 记录初始内存使用
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        memory_samples = [initial_memory]
        
        def collect_result(result: HealthCheckResult):
            # 每10次检查记录一次内存使用
            if len(memory_samples) % 10 == 0:
                current_memory = process.memory_info().rss / 1024 / 1024
                memory_samples.append(current_memory)
        
        scheduler.set_check_result_callback(collect_result)
        
        # 运行较长时间测试内存稳定性
        scheduler_task = asyncio.create_task(scheduler.start())
        
        await asyncio.sleep(30)  # 运行30秒
        await scheduler.stop()
        scheduler_task.cancel()
        
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        
        # 最终内存使用
        gc.collect()  # 强制垃圾回收
        final_memory = process.memory_info().rss / 1024 / 1024
        memory_samples.append(final_memory)
        
        # 分析内存使用
        max_memory = max(memory_samples)
        min_memory = min(memory_samples)
        avg_memory = statistics.mean(memory_samples)
        memory_growth = final_memory - initial_memory
        
        print(f"\n内存使用稳定性测试:")
        print(f"初始内存: {initial_memory:.1f} MB")
        print(f"最终内存: {final_memory:.1f} MB")
        print(f"最大内存: {max_memory:.1f} MB")
        print(f"最小内存: {min_memory:.1f} MB")
        print(f"平均内存: {avg_memory:.1f} MB")
        print(f"内存增长: {memory_growth:.1f} MB")
        print(f"内存增长率: {(memory_growth/initial_memory)*100:.1f}%")
        
        # 验证内存使用稳定性
        assert memory_growth < 50  # 内存增长不超过50MB
        assert (memory_growth / initial_memory) < 0.5  # 内存增长率不超过50%
    
    @pytest.mark.asyncio
    async def test_error_handling_performance(self):
        """测试错误处理对性能的影响"""
        
        class FailingMockChecker(MockHealthChecker):
            """会失败的模拟检查器"""
            
            def __init__(self, name: str, config: Dict[str, Any], failure_rate: float = 0.3):
                super().__init__(name, config, delay=0.1)
                self.failure_rate = failure_rate
            
            async def check_health(self) -> HealthCheckResult:
                self.check_count += 1
                start_time = time.time()
                
                await asyncio.sleep(self.delay)
                
                # 模拟随机失败
                import random
                if random.random() < self.failure_rate:
                    response_time = time.time() - start_time
                    return HealthCheckResult(
                        service_name=self.name,
                        service_type='mock',
                        is_healthy=False,
                        response_time=response_time,
                        error_message="模拟检查失败",
                        metadata={'check_count': self.check_count}
                    )
                
                return await super().check_health()
        
        scheduler = MonitorScheduler(max_concurrent_checks=5)
        
        # 创建混合的检查器（正常和会失败的）
        normal_count = 5
        failing_count = 5
        
        for i in range(normal_count):
            service_name = f'normal_service_{i}'
            checker = MockHealthChecker(service_name, {'type': 'mock'}, delay=0.1)
            scheduler.checkers[service_name] = checker
            scheduler.check_intervals[service_name] = 2
        
        for i in range(failing_count):
            service_name = f'failing_service_{i}'
            checker = FailingMockChecker(service_name, {'type': 'mock'}, failure_rate=0.4)
            scheduler.checkers[service_name] = checker
            scheduler.check_intervals[service_name] = 2
        
        # 收集结果
        results = []
        errors = []
        
        def collect_result(result: HealthCheckResult):
            results.append(result)
        
        def collect_error(service_name: str, error: Exception):
            errors.append((service_name, error))
        
        scheduler.set_check_result_callback(collect_result)
        scheduler.set_check_error_callback(collect_error)
        
        # 运行测试
        start_time = time.time()
        scheduler_task = asyncio.create_task(scheduler.start())
        
        await asyncio.sleep(15)
        await scheduler.stop()
        scheduler_task.cancel()
        
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        
        # 分析结果
        total_time = time.time() - start_time
        total_checks = len(results)
        successful_checks = len([r for r in results if r.is_healthy])
        failed_checks = len([r for r in results if not r.is_healthy])
        
        print(f"\n错误处理性能测试:")
        print(f"总运行时间: {total_time:.2f}秒")
        print(f"总检查次数: {total_checks}")
        print(f"成功检查: {successful_checks}")
        print(f"失败检查: {failed_checks}")
        print(f"错误数量: {len(errors)}")
        print(f"失败率: {(failed_checks/total_checks)*100:.1f}%")
        print(f"平均吞吐量: {total_checks/total_time:.2f} 次/秒")
        
        # 验证错误处理不会严重影响性能
        assert total_checks > 20  # 至少完成20次检查
        assert (total_checks / total_time) > 1.0  # 吞吐量至少1次/秒
        
        # 验证错误被正确处理
        assert failed_checks > 0  # 应该有失败的检查
        assert successful_checks > 0  # 也应该有成功的检查


if __name__ == "__main__":
    # 运行基准测试
    pytest.main([__file__, "-v", "-s"])