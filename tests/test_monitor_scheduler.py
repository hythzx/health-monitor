"""监控调度器测试模块"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta

from health_monitor.services.monitor_scheduler import MonitorScheduler
from health_monitor.models.health_check import HealthCheckResult
from health_monitor.checkers.base import BaseHealthChecker
from health_monitor.utils.exceptions import ConfigError, CheckerError


class MockHealthChecker(BaseHealthChecker):
    """模拟健康检查器"""
    
    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.check_result = HealthCheckResult(
            service_name=name,
            service_type=config.get('type', 'mock'),
            is_healthy=True,
            response_time=0.1
        )
        self.check_called = False
        self.check_delay = 0
    
    async def check_health(self) -> HealthCheckResult:
        """模拟健康检查"""
        self.check_called = True
        if self.check_delay > 0:
            await asyncio.sleep(self.check_delay)
        return self.check_result
    
    def validate_config(self) -> bool:
        """验证配置"""
        return True


class TestMonitorScheduler:
    """监控调度器测试类"""
    
    def setup_method(self):
        """测试前准备"""
        self.scheduler = MonitorScheduler(max_concurrent_checks=5)
    
    def teardown_method(self):
        """测试后清理"""
        if self.scheduler.is_running:
            # 在同步方法中处理异步清理
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果事件循环正在运行，创建任务
                    asyncio.create_task(self.scheduler.stop())
                else:
                    # 如果事件循环未运行，直接运行
                    loop.run_until_complete(self.scheduler.stop())
            except RuntimeError:
                # 如果没有事件循环，创建新的
                asyncio.run(self.scheduler.stop())
    
    def test_init(self):
        """测试初始化"""
        scheduler = MonitorScheduler(max_concurrent_checks=10)
        assert scheduler.max_concurrent_checks == 10
        assert scheduler.checkers == {}
        assert scheduler.check_intervals == {}
        assert scheduler.last_check_times == {}
        assert not scheduler.is_running
        assert scheduler.semaphore is None
        assert scheduler.executor is None
    
    @patch('health_monitor.services.monitor_scheduler.health_checker_factory')
    def test_configure_services(self, mock_factory):
        """测试配置服务"""
        # 设置模拟工厂
        mock_checker = MockHealthChecker("test-service", {"type": "mock"})
        mock_factory.create_checker.return_value = mock_checker
        
        services_config = {
            "test-service": {
                "type": "mock",
                "check_interval": 60
            }
        }
        global_config = {
            "check_interval": 30
        }
        
        self.scheduler.configure_services(services_config, global_config)
        
        # 验证配置结果
        assert "test-service" in self.scheduler.checkers
        assert self.scheduler.checkers["test-service"] == mock_checker
        assert self.scheduler.check_intervals["test-service"] == 60
        
        # 验证工厂调用
        mock_factory.create_checker.assert_called_once_with("test-service", services_config["test-service"])
    
    @patch('health_monitor.services.monitor_scheduler.health_checker_factory')
    def test_configure_services_with_default_interval(self, mock_factory):
        """测试使用默认检查间隔配置服务"""
        mock_checker = MockHealthChecker("test-service", {"type": "mock"})
        mock_factory.create_checker.return_value = mock_checker
        
        services_config = {
            "test-service": {
                "type": "mock"
                # 没有指定 check_interval
            }
        }
        global_config = {
            "check_interval": 45
        }
        
        self.scheduler.configure_services(services_config, global_config)
        
        # 应该使用全局默认间隔
        assert self.scheduler.check_intervals["test-service"] == 45
    
    @patch('health_monitor.services.monitor_scheduler.health_checker_factory')
    def test_configure_services_invalid_interval(self, mock_factory):
        """测试配置无效检查间隔"""
        mock_checker = MockHealthChecker("test-service", {"type": "mock"})
        mock_factory.create_checker.return_value = mock_checker
        
        services_config = {
            "test-service": {
                "type": "mock",
                "check_interval": -1  # 无效间隔
            }
        }
        
        with pytest.raises(ConfigError, match="检查间隔必须是正整数"):
            self.scheduler.configure_services(services_config)
    
    @patch('health_monitor.services.monitor_scheduler.health_checker_factory')
    def test_configure_services_factory_error(self, mock_factory):
        """测试工厂创建检查器失败"""
        mock_factory.create_checker.side_effect = CheckerError("创建失败")
        
        services_config = {
            "test-service": {
                "type": "mock",
                "check_interval": 30
            }
        }
        
        with pytest.raises(CheckerError):
            self.scheduler.configure_services(services_config)
    
    def test_set_callbacks(self):
        """测试设置回调函数"""
        result_callback = AsyncMock()
        error_callback = AsyncMock()
        
        self.scheduler.set_check_result_callback(result_callback)
        self.scheduler.set_check_error_callback(error_callback)
        
        assert self.scheduler.on_check_result == result_callback
        assert self.scheduler.on_check_error == error_callback
    
    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        """测试启动和停止调度器"""
        # 启动
        start_task = asyncio.create_task(self.scheduler.start())
        await asyncio.sleep(0.1)  # 让调度器启动
        
        assert self.scheduler.is_running
        assert self.scheduler.semaphore is not None
        assert self.scheduler.executor is not None
        
        # 停止
        await self.scheduler.stop()
        
        assert not self.scheduler.is_running
        assert self.scheduler.semaphore is None
        assert self.scheduler.executor is None
        
        # 清理启动任务
        start_task.cancel()
        try:
            await start_task
        except asyncio.CancelledError:
            pass
    
    def test_should_check_service(self):
        """测试判断服务是否需要检查"""
        service_name = "test-service"
        current_time = datetime.now()
        
        # 服务不存在
        assert not self.scheduler._should_check_service(service_name, current_time)
        
        # 添加服务配置
        self.scheduler.check_intervals[service_name] = 60
        
        # 从未检查过
        assert self.scheduler._should_check_service(service_name, current_time)
        
        # 刚刚检查过
        self.scheduler.last_check_times[service_name] = current_time
        assert not self.scheduler._should_check_service(service_name, current_time)
        
        # 超过检查间隔
        past_time = current_time - timedelta(seconds=70)
        self.scheduler.last_check_times[service_name] = past_time
        assert self.scheduler._should_check_service(service_name, current_time)
    
    @pytest.mark.asyncio
    @patch('health_monitor.services.monitor_scheduler.health_checker_factory')
    async def test_check_service_now(self, mock_factory):
        """测试立即检查服务"""
        # 设置模拟检查器
        mock_checker = MockHealthChecker("test-service", {"type": "mock"})
        mock_factory.create_checker.return_value = mock_checker
        
        # 配置服务
        services_config = {"test-service": {"type": "mock", "check_interval": 60}}
        self.scheduler.configure_services(services_config)
        
        # 立即检查
        result = await self.scheduler.check_service_now("test-service")
        
        assert result is not None
        assert result.service_name == "test-service"
        assert mock_checker.check_called
        assert "test-service" in self.scheduler.last_check_times
    
    @pytest.mark.asyncio
    async def test_check_service_now_nonexistent(self):
        """测试立即检查不存在的服务"""
        result = await self.scheduler.check_service_now("nonexistent")
        assert result is None
    
    @pytest.mark.asyncio
    @patch('health_monitor.services.monitor_scheduler.health_checker_factory')
    async def test_check_all_services_now(self, mock_factory):
        """测试立即检查所有服务"""
        # 设置多个模拟检查器
        mock_checker1 = MockHealthChecker("service1", {"type": "mock"})
        mock_checker2 = MockHealthChecker("service2", {"type": "mock"})
        
        def create_checker_side_effect(name, config):
            if name == "service1":
                return mock_checker1
            elif name == "service2":
                return mock_checker2
            
        mock_factory.create_checker.side_effect = create_checker_side_effect
        
        # 配置服务
        services_config = {
            "service1": {"type": "mock", "check_interval": 30},
            "service2": {"type": "mock", "check_interval": 60}
        }
        self.scheduler.configure_services(services_config)
        
        # 检查所有服务
        results = await self.scheduler.check_all_services_now()
        
        assert len(results) == 2
        assert "service1" in results
        assert "service2" in results
        assert results["service1"] is not None
        assert results["service2"] is not None
        assert mock_checker1.check_called
        assert mock_checker2.check_called
    
    @pytest.mark.asyncio
    @patch('health_monitor.services.monitor_scheduler.health_checker_factory')
    async def test_check_service_with_callbacks(self, mock_factory):
        """测试带回调的服务检查"""
        # 设置模拟检查器
        mock_checker = MockHealthChecker("test-service", {"type": "mock"})
        mock_factory.create_checker.return_value = mock_checker
        
        # 设置回调
        result_callback = AsyncMock()
        error_callback = AsyncMock()
        self.scheduler.set_check_result_callback(result_callback)
        self.scheduler.set_check_error_callback(error_callback)
        
        # 配置服务
        services_config = {"test-service": {"type": "mock", "check_interval": 60}}
        self.scheduler.configure_services(services_config)
        
        # 启动调度器并执行检查
        self.scheduler.semaphore = asyncio.Semaphore(5)
        await self.scheduler._check_service("test-service")
        
        # 验证回调被调用
        result_callback.assert_called_once()
        error_callback.assert_not_called()
    
    @pytest.mark.asyncio
    @patch('health_monitor.services.monitor_scheduler.health_checker_factory')
    async def test_check_service_with_error(self, mock_factory):
        """测试检查服务时发生错误"""
        # 设置会抛出异常的模拟检查器
        mock_checker = Mock()
        mock_checker.check_health = AsyncMock(side_effect=Exception("检查失败"))
        mock_factory.create_checker.return_value = mock_checker
        
        # 设置回调
        result_callback = AsyncMock()
        error_callback = AsyncMock()
        self.scheduler.set_check_result_callback(result_callback)
        self.scheduler.set_check_error_callback(error_callback)
        
        # 配置服务
        services_config = {"test-service": {"type": "mock", "check_interval": 60}}
        self.scheduler.configure_services(services_config)
        
        # 启动调度器并执行检查
        self.scheduler.semaphore = asyncio.Semaphore(5)
        await self.scheduler._check_service("test-service")
        
        # 验证错误回调被调用
        result_callback.assert_not_called()
        error_callback.assert_called_once_with("test-service", mock_checker.check_health.side_effect)
    
    def test_update_check_interval(self):
        """测试更新检查间隔"""
        # 添加服务
        self.scheduler.checkers["test-service"] = Mock()
        self.scheduler.check_intervals["test-service"] = 30
        
        # 更新间隔
        self.scheduler.update_check_interval("test-service", 60)
        assert self.scheduler.check_intervals["test-service"] == 60
        
        # 测试无效间隔
        with pytest.raises(ValueError, match="检查间隔必须是正整数"):
            self.scheduler.update_check_interval("test-service", -1)
        
        # 测试不存在的服务
        with pytest.raises(ValueError, match="服务 nonexistent 不存在"):
            self.scheduler.update_check_interval("nonexistent", 60)
    
    @patch('health_monitor.services.monitor_scheduler.health_checker_factory')
    def test_get_service_status(self, mock_factory):
        """测试获取服务状态"""
        # 设置模拟检查器
        mock_checker = MockHealthChecker("test-service", {"type": "mock"})
        mock_factory.create_checker.return_value = mock_checker
        
        # 配置服务
        services_config = {"test-service": {"type": "mock", "check_interval": 60}}
        self.scheduler.configure_services(services_config)
        
        # 设置最后检查时间
        last_check = datetime.now() - timedelta(seconds=30)
        self.scheduler.last_check_times["test-service"] = last_check
        
        # 获取状态
        status = self.scheduler.get_service_status()
        
        assert "test-service" in status
        service_status = status["test-service"]
        assert service_status["service_type"] == "mock"
        assert service_status["check_interval"] == 60
        assert service_status["last_check_time"] == last_check.isoformat()
        assert service_status["next_check_time"] is not None
        assert isinstance(service_status["should_check_now"], bool)
    
    def test_get_scheduler_stats(self):
        """测试获取调度器统计信息"""
        # 添加一些模拟数据
        self.scheduler.checkers["service1"] = Mock()
        self.scheduler.checkers["service2"] = Mock()
        self.scheduler.is_running = True
        
        stats = self.scheduler.get_scheduler_stats()
        
        assert stats["is_running"] is True
        assert stats["total_services"] == 2
        assert stats["max_concurrent_checks"] == 5
        assert stats["running_tasks_count"] == 0
        assert stats["configured_services"] == ["service1", "service2"]
    
    @pytest.mark.asyncio
    @patch('health_monitor.services.monitor_scheduler.health_checker_factory')
    async def test_concurrent_checks_limit(self, mock_factory):
        """测试并发检查数量限制"""
        # 创建会延迟的模拟检查器
        checkers = []
        for i in range(10):
            checker = MockHealthChecker(f"service{i}", {"type": "mock"})
            checker.check_delay = 0.1  # 100ms延迟
            checkers.append(checker)
        
        def create_checker_side_effect(name, config):
            index = int(name.replace("service", ""))
            return checkers[index]
        
        mock_factory.create_checker.side_effect = create_checker_side_effect
        
        # 配置多个服务
        services_config = {}
        for i in range(10):
            services_config[f"service{i}"] = {"type": "mock", "check_interval": 1}
        
        # 设置较小的并发限制
        scheduler = MonitorScheduler(max_concurrent_checks=3)
        scheduler.configure_services(services_config)
        
        # 启动调度器
        start_task = asyncio.create_task(scheduler.start())
        await asyncio.sleep(0.05)  # 让调度器启动
        
        # 等待一段时间让检查执行
        await asyncio.sleep(0.2)
        
        # 停止调度器
        await scheduler.stop()
        
        # 清理启动任务
        start_task.cancel()
        try:
            await start_task
        except asyncio.CancelledError:
            pass
        
        # 验证至少有一些检查被执行了
        executed_count = sum(1 for checker in checkers if checker.check_called)
        assert executed_count > 0


if __name__ == "__main__":
    pytest.main([__file__])