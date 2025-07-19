"""监控调度器模块

负责管理定时健康检查任务的调度和执行
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Set, Callable, Awaitable

from ..checkers.base import BaseHealthChecker
from ..checkers.factory import health_checker_factory
from ..models.health_check import HealthCheckResult
from ..utils.exceptions import ConfigError
from ..utils.performance_monitor import PerformanceMonitor


class MonitorScheduler:
    """监控调度器
    
    管理定时健康检查任务，支持异步任务调度和并发控制
    """

    def __init__(self, max_concurrent_checks: int = 10,
                 enable_performance_monitoring: bool = True):
        """初始化监控调度器
        
        Args:
            max_concurrent_checks: 最大并发检查数量
            enable_performance_monitoring: 是否启用性能监控
        """
        self.max_concurrent_checks = max_concurrent_checks
        self.checkers: Dict[str, BaseHealthChecker] = {}
        self.check_intervals: Dict[str, int] = {}  # 服务名 -> 检查间隔(秒)
        self.last_check_times: Dict[str, datetime] = {}  # 服务名 -> 上次检查时间
        self.running_tasks: Set[asyncio.Task] = set()
        self.is_running = False
        self.semaphore: Optional[asyncio.Semaphore] = None
        self.executor: Optional[ThreadPoolExecutor] = None
        self.logger = logging.getLogger(__name__)

        # 性能监控
        self.enable_performance_monitoring = enable_performance_monitoring
        self.performance_monitor: Optional[PerformanceMonitor] = None
        if enable_performance_monitoring:
            self.performance_monitor = PerformanceMonitor(
                collection_interval=30,  # 30秒收集一次性能数据
                history_size=200,  # 保存200个历史记录
                alert_thresholds={
                    'cpu_percent': 80.0,
                    'memory_percent': 85.0
                }
            )
            self.performance_monitor.set_threshold_callback(
                self._on_performance_threshold_exceeded)

        # 回调函数
        self.on_check_result: Optional[
            Callable[[HealthCheckResult], Awaitable[None]]] = None
        self.on_check_error: Optional[Callable[[str, Exception], Awaitable[None]]] = None
        self.on_performance_alert: Optional[
            Callable[[str, float, float], Awaitable[None]]] = None

    def configure_services(self, services_config: Dict[str, Any],
                           global_config: Optional[Dict[str, Any]] = None):
        """配置监控服务
        
        Args:
            services_config: 服务配置字典
            global_config: 全局配置字典
            
        Raises:
            ConfigError: 配置错误
            CheckerError: 检查器创建错误
        """
        if global_config is None:
            global_config = {}

        default_interval = global_config.get('check_interval', 30)

        # 清空现有配置
        self.checkers.clear()
        self.check_intervals.clear()
        self.last_check_times.clear()

        # 创建健康检查器
        for service_name, service_config in services_config.items():
            try:
                # 创建检查器
                checker = health_checker_factory.create_checker(service_name,
                                                                service_config)
                self.checkers[service_name] = checker

                # 设置检查间隔
                check_interval = service_config.get('check_interval', default_interval)
                if not isinstance(check_interval, int) or check_interval <= 0:
                    raise ConfigError(f"服务 {service_name} 的检查间隔必须是正整数")

                self.check_intervals[service_name] = check_interval

                self.logger.info(
                    f"配置服务 {service_name}: 类型={service_config.get('type')}, 间隔={check_interval}秒")

            except Exception as e:
                self.logger.error(f"配置服务 {service_name} 失败: {e}")
                raise

    def set_check_result_callback(self, callback: Callable[
        [HealthCheckResult], Awaitable[None]]):
        """设置检查结果回调函数
        
        Args:
            callback: 检查结果回调函数
        """
        self.on_check_result = callback

    def set_check_error_callback(self,
                                 callback: Callable[[str, Exception], Awaitable[None]]):
        """设置检查错误回调函数
        
        Args:
            callback: 检查错误回调函数
        """
        self.on_check_error = callback

    def set_performance_alert_callback(self, callback: Callable[
        [str, float, float], Awaitable[None]]):
        """设置性能告警回调函数
        
        Args:
            callback: 性能告警回调函数，参数为(指标名, 当前值, 阈值)
        """
        self.on_performance_alert = callback

    async def start(self):
        """启动监控调度器"""
        if self.is_running:
            self.logger.warning("监控调度器已经在运行")
            return

        self.is_running = True
        self.semaphore = asyncio.Semaphore(self.max_concurrent_checks)
        self.executor = ThreadPoolExecutor(max_workers=self.max_concurrent_checks)

        self.logger.info(f"启动监控调度器，最大并发检查数: {self.max_concurrent_checks}")

        # 启动性能监控
        performance_task = None
        if self.performance_monitor:
            performance_task = asyncio.create_task(
                self.performance_monitor.start_monitoring())
            self.logger.info("性能监控已启动")

        # 启动调度循环
        try:
            await self._schedule_loop()
        except asyncio.CancelledError:
            self.logger.info("监控调度器被取消")
        except Exception as e:
            self.logger.error(f"监控调度器运行异常: {e}")
        finally:
            # 停止性能监控
            if performance_task and not performance_task.done():
                performance_task.cancel()
                try:
                    await performance_task
                except asyncio.CancelledError:
                    pass
            await self.stop()

    async def stop(self):
        """停止监控调度器"""
        if not self.is_running:
            return

        self.is_running = False
        self.logger.info("正在停止监控调度器...")

        # 取消所有运行中的任务
        for task in self.running_tasks:
            if not task.done():
                task.cancel()

        # 等待所有任务完成
        if self.running_tasks:
            await asyncio.gather(*self.running_tasks, return_exceptions=True)

        self.running_tasks.clear()

        # 关闭线程池
        if self.executor:
            self.executor.shutdown(wait=True)
            self.executor = None

        self.semaphore = None

        # 停止性能监控
        if self.performance_monitor:
            await self.performance_monitor.stop_monitoring()
            self.logger.info("性能监控已停止")

        self.logger.info("监控调度器已停止")

    async def _schedule_loop(self):
        """调度循环"""
        while self.is_running:
            try:
                current_time = datetime.now()

                # 检查哪些服务需要执行健康检查
                for service_name in self.checkers:
                    if self._should_check_service(service_name, current_time):
                        # 创建检查任务
                        task = asyncio.create_task(self._check_service(service_name))
                        self.running_tasks.add(task)

                        # 添加任务完成回调，用于清理
                        task.add_done_callback(self.running_tasks.discard)

                # 等待一小段时间再进行下一轮检查
                await asyncio.sleep(1)

            except Exception as e:
                self.logger.error(f"调度循环异常: {e}")
                await asyncio.sleep(5)  # 异常时等待更长时间

    def _should_check_service(self, service_name: str, current_time: datetime) -> bool:
        """判断服务是否需要检查
        
        Args:
            service_name: 服务名称
            current_time: 当前时间
            
        Returns:
            是否需要检查
        """
        if service_name not in self.check_intervals:
            return False

        last_check = self.last_check_times.get(service_name)
        if last_check is None:
            return True  # 从未检查过

        interval = self.check_intervals[service_name]
        next_check_time = last_check + timedelta(seconds=interval)

        return current_time >= next_check_time

    async def _check_service(self, service_name: str):
        """执行服务健康检查
        
        Args:
            service_name: 服务名称
        """
        if not self.semaphore:
            return

        async with self.semaphore:  # 控制并发数量
            try:
                checker = self.checkers.get(service_name)
                if not checker:
                    self.logger.error(f"服务 {service_name} 的检查器不存在")
                    return

                self.logger.debug(f"开始检查服务: {service_name}")
                start_time = datetime.now()

                # 执行健康检查
                result = await checker.check_health()

                # 更新最后检查时间
                self.last_check_times[service_name] = start_time

                # 记录检查结果
                status = "健康" if result.is_healthy else "不健康"
                self.logger.info(
                    f"服务 {service_name} 检查完成: {status}, "
                    f"响应时间: {result.response_time:.3f}s"
                )

                # 调用结果回调
                if self.on_check_result:
                    await self.on_check_result(result)

            except Exception as e:
                self.logger.error(f"检查服务 {service_name} 时发生异常: {e}")

                # 调用错误回调
                if self.on_check_error:
                    await self.on_check_error(service_name, e)

    async def check_service_now(self, service_name: str) -> Optional[HealthCheckResult]:
        """立即检查指定服务
        
        Args:
            service_name: 服务名称
            
        Returns:
            检查结果，如果检查失败返回None
        """
        checker = self.checkers.get(service_name)
        if not checker:
            self.logger.error(f"服务 {service_name} 的检查器不存在")
            return None

        try:
            self.logger.info(f"立即检查服务: {service_name}")
            result = await checker.check_health()

            # 更新最后检查时间
            self.last_check_times[service_name] = datetime.now()

            return result

        except Exception as e:
            self.logger.error(f"立即检查服务 {service_name} 失败: {e}")

            # 调用错误回调
            if self.on_check_error:
                try:
                    await self.on_check_error(service_name, e)
                except Exception as callback_error:
                    self.logger.error(f"错误回调执行失败: {callback_error}")

            return None

    async def check_all_services_now(self) -> Dict[str, Optional[HealthCheckResult]]:
        """立即检查所有服务
        
        Returns:
            所有服务的检查结果字典
        """
        results = {}

        # 创建所有检查任务
        tasks = []
        service_names = []

        for service_name in self.checkers:
            task = asyncio.create_task(self.check_service_now(service_name))
            tasks.append(task)
            service_names.append(service_name)

        # 等待所有任务完成
        if tasks:
            task_results = await asyncio.gather(*tasks, return_exceptions=True)

            for service_name, result in zip(service_names, task_results):
                if isinstance(result, Exception):
                    self.logger.error(f"检查服务 {service_name} 异常: {result}")
                    results[service_name] = None
                else:
                    results[service_name] = result

        return results

    def update_check_interval(self, service_name: str, interval: int):
        """更新服务检查间隔
        
        Args:
            service_name: 服务名称
            interval: 新的检查间隔（秒）
            
        Raises:
            ValueError: 间隔值无效
        """
        if interval <= 0:
            raise ValueError("检查间隔必须是正整数")

        if service_name not in self.checkers:
            raise ValueError(f"服务 {service_name} 不存在")

        old_interval = self.check_intervals.get(service_name, 0)
        self.check_intervals[service_name] = interval

        self.logger.info(
            f"更新服务 {service_name} 检查间隔: {old_interval}s -> {interval}s")

    def get_service_status(self) -> Dict[str, Any]:
        """获取所有服务的状态信息
        
        Returns:
            服务状态信息字典
        """
        status = {}
        current_time = datetime.now()

        for service_name in self.checkers:
            last_check = self.last_check_times.get(service_name)
            interval = self.check_intervals.get(service_name, 0)

            next_check = None
            if last_check:
                next_check = last_check + timedelta(seconds=interval)

            status[service_name] = {
                'service_type': self.checkers[service_name].config.get('type', 'unknown'),
                'check_interval': interval,
                'last_check_time': last_check.isoformat() if last_check else None,
                'next_check_time': next_check.isoformat() if next_check else None,
                'should_check_now': self._should_check_service(service_name, current_time)
            }

        return status

    def get_scheduler_stats(self) -> Dict[str, Any]:
        """获取调度器统计信息
        
        Returns:
            调度器统计信息
        """
        stats = {
            'is_running': self.is_running,
            'total_services': len(self.checkers),
            'max_concurrent_checks': self.max_concurrent_checks,
            'running_tasks_count': len(self.running_tasks),
            'configured_services': list(self.checkers.keys()),
            'performance_monitoring_enabled': self.enable_performance_monitoring
        }

        # 添加性能监控统计
        if self.performance_monitor:
            current_metrics = self.performance_monitor.get_current_metrics()
            if current_metrics:
                stats['current_performance'] = current_metrics.to_dict()

            avg_metrics = self.performance_monitor.get_average_metrics(10)  # 10分钟平均值
            if avg_metrics:
                stats['avg_performance_10min'] = avg_metrics

            peak_metrics = self.performance_monitor.get_peak_metrics(10)  # 10分钟峰值
            if peak_metrics:
                stats['peak_performance_10min'] = peak_metrics

        return stats

    def _on_performance_threshold_exceeded(self, metric_name: str, current_value: float,
                                           threshold: float):
        """性能阈值超限回调
        
        Args:
            metric_name: 指标名称
            current_value: 当前值
            threshold: 阈值
        """
        self.logger.warning(
            f"性能指标 {metric_name} 超过阈值: {current_value:.1f} > {threshold:.1f}")

        # 异步调用告警回调
        if self.on_performance_alert:
            asyncio.create_task(
                self.on_performance_alert(metric_name, current_value, threshold))

    def get_performance_metrics(self, minutes: int = 10) -> Optional[Dict[str, Any]]:
        """获取性能指标
        
        Args:
            minutes: 时间范围（分钟）
            
        Returns:
            性能指标数据
        """
        if not self.performance_monitor:
            return None

        return {
            'current': self.performance_monitor.get_current_metrics().to_dict() if self.performance_monitor.get_current_metrics() else None,
            'average': self.performance_monitor.get_average_metrics(minutes),
            'peak': self.performance_monitor.get_peak_metrics(minutes),
            'history': [m.to_dict() for m in
                        self.performance_monitor.get_metrics_history(minutes)]
        }

    def update_performance_thresholds(self, thresholds: Dict[str, float]):
        """更新性能告警阈值
        
        Args:
            thresholds: 新的阈值配置
        """
        if self.performance_monitor:
            self.performance_monitor.update_thresholds(thresholds)
            self.logger.info(f"更新性能告警阈值: {thresholds}")

    async def optimize_concurrent_checks(self):
        """动态优化并发检查数量"""
        if not self.performance_monitor:
            return

        current_metrics = self.performance_monitor.get_current_metrics()
        if not current_metrics:
            return

        # 根据CPU和内存使用情况调整并发数
        cpu_percent = current_metrics.cpu_percent
        memory_percent = current_metrics.memory_percent

        # 如果CPU或内存使用率过高，减少并发数
        if cpu_percent > 70 or memory_percent > 75:
            new_concurrent = max(1, self.max_concurrent_checks - 2)
            if new_concurrent != self.max_concurrent_checks:
                self.max_concurrent_checks = new_concurrent
                # 更新信号量
                if self.semaphore:
                    self.semaphore = asyncio.Semaphore(new_concurrent)
                self.logger.info(f"由于资源使用率过高，降低并发检查数至: {new_concurrent}")

        # 如果资源使用率较低，可以适当增加并发数
        elif cpu_percent < 30 and memory_percent < 50:
            new_concurrent = min(20, self.max_concurrent_checks + 1)  # 最大不超过20
            if new_concurrent != self.max_concurrent_checks:
                self.max_concurrent_checks = new_concurrent
                # 更新信号量
                if self.semaphore:
                    self.semaphore = asyncio.Semaphore(new_concurrent)
                self.logger.info(f"由于资源使用率较低，提高并发检查数至: {new_concurrent}")
