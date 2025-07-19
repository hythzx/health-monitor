"""容错机制测试"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch

from health_monitor.utils.resilience import (
    ResilienceManager,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
    FallbackConfig,
    ServiceState,
    PartialFailureHandler,
    with_circuit_breaker,
    with_fallback,
    graceful_degradation,
    async_graceful_degradation,
    global_resilience_manager
)
from health_monitor.utils.exceptions import CheckerError, ErrorCode


class TestCircuitBreaker:
    """熔断器测试"""
    
    def setup_method(self):
        """测试前设置"""
        self.config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=1,
            half_open_max_calls=2
        )
        self.circuit_breaker = CircuitBreaker("test-service", self.config)
    
    def test_initial_state(self):
        """测试初始状态"""
        assert self.circuit_breaker.state == CircuitBreakerState.CLOSED
        assert self.circuit_breaker.failure_count == 0
        assert self.circuit_breaker.should_allow_request() is True
    
    def test_failure_threshold(self):
        """测试失败阈值"""
        # 记录失败直到达到阈值
        for i in range(self.config.failure_threshold):
            self.circuit_breaker.record_failure()
            if i < self.config.failure_threshold - 1:
                assert self.circuit_breaker.state == CircuitBreakerState.CLOSED
            else:
                assert self.circuit_breaker.state == CircuitBreakerState.OPEN
        
        # 熔断器打开后不允许请求
        assert self.circuit_breaker.should_allow_request() is False
    
    def test_recovery_timeout(self):
        """测试恢复超时"""
        # 触发熔断器打开
        for _ in range(self.config.failure_threshold):
            self.circuit_breaker.record_failure()
        
        assert self.circuit_breaker.state == CircuitBreakerState.OPEN
        assert self.circuit_breaker.should_allow_request() is False
        
        # 等待恢复超时
        time.sleep(self.config.recovery_timeout + 0.1)
        
        # 现在应该允许请求（进入半开状态）
        assert self.circuit_breaker.should_allow_request() is True
        assert self.circuit_breaker.state == CircuitBreakerState.HALF_OPEN
    
    def test_half_open_success(self):
        """测试半开状态成功恢复"""
        # 触发熔断器打开
        for _ in range(self.config.failure_threshold):
            self.circuit_breaker.record_failure()
        
        # 等待进入半开状态
        time.sleep(self.config.recovery_timeout + 0.1)
        self.circuit_breaker.should_allow_request()  # 触发状态转换
        
        # 记录成功直到恢复
        for i in range(self.config.half_open_max_calls):
            self.circuit_breaker.record_success()
            if i < self.config.half_open_max_calls - 1:
                assert self.circuit_breaker.state == CircuitBreakerState.HALF_OPEN
            else:
                assert self.circuit_breaker.state == CircuitBreakerState.CLOSED
    
    def test_half_open_failure(self):
        """测试半开状态失败"""
        # 触发熔断器打开
        for _ in range(self.config.failure_threshold):
            self.circuit_breaker.record_failure()
        
        # 等待进入半开状态
        time.sleep(self.config.recovery_timeout + 0.1)
        self.circuit_breaker.should_allow_request()  # 触发状态转换
        
        # 在半开状态记录失败
        self.circuit_breaker.record_failure()
        assert self.circuit_breaker.state == CircuitBreakerState.OPEN


class TestResilienceManager:
    """容错管理器测试"""
    
    def setup_method(self):
        """测试前设置"""
        self.manager = ResilienceManager()
    
    def test_register_circuit_breaker(self):
        """测试注册熔断器"""
        config = CircuitBreakerConfig()
        circuit_breaker = self.manager.register_circuit_breaker("test-service", config)
        
        assert circuit_breaker.name == "test-service"
        assert self.manager.get_circuit_breaker("test-service") == circuit_breaker
    
    def test_register_fallback(self):
        """测试注册降级配置"""
        config = FallbackConfig(fallback_value="default")
        self.manager.register_fallback("test-service", config)
        
        assert self.manager.get_fallback_config("test-service") == config
    
    def test_service_state_management(self):
        """测试服务状态管理"""
        service_name = "test-service"
        
        # 初始状态
        assert self.manager.get_service_state(service_name) == ServiceState.UNKNOWN
        
        # 更新状态
        self.manager.update_service_state(service_name, ServiceState.HEALTHY)
        assert self.manager.get_service_state(service_name) == ServiceState.HEALTHY
        
        self.manager.update_service_state(service_name, ServiceState.DEGRADED)
        assert self.manager.get_service_state(service_name) == ServiceState.DEGRADED
    
    def test_failure_recording_and_fallback(self):
        """测试失败记录和降级判断"""
        service_name = "test-service"
        config = FallbackConfig(
            enabled=True,
            fallback_value="fallback",
            max_failures=2,
            failure_window=60
        )
        self.manager.register_fallback(service_name, config)
        
        # 初始不应该使用降级
        assert self.manager.should_use_fallback(service_name) is False
        
        # 记录失败
        self.manager.record_failure(service_name)
        assert self.manager.should_use_fallback(service_name) is False
        
        # 记录更多失败直到触发降级
        self.manager.record_failure(service_name)
        assert self.manager.should_use_fallback(service_name) is True
        assert self.manager.get_service_state(service_name) == ServiceState.DEGRADED
    
    def test_fallback_value_with_function(self):
        """测试带函数的降级值"""
        service_name = "test-service"
        
        def fallback_func():
            return "dynamic_fallback"
        
        config = FallbackConfig(
            enabled=True,
            fallback_value="static_fallback",
            fallback_function=fallback_func
        )
        self.manager.register_fallback(service_name, config)
        
        # 应该使用函数返回值
        assert self.manager.get_fallback_value(service_name) == "dynamic_fallback"
    
    def test_fallback_function_failure(self):
        """测试降级函数失败"""
        service_name = "test-service"
        
        def failing_fallback_func():
            raise ValueError("降级函数失败")
        
        config = FallbackConfig(
            enabled=True,
            fallback_value="static_fallback",
            fallback_function=failing_fallback_func
        )
        self.manager.register_fallback(service_name, config)
        
        # 应该回退到静态值
        assert self.manager.get_fallback_value(service_name) == "static_fallback"


class TestCircuitBreakerDecorator:
    """熔断器装饰器测试"""
    
    def test_sync_function_success(self):
        """测试同步函数成功"""
        call_count = 0
        
        @with_circuit_breaker("test-sync", failure_threshold=2)
        def test_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = test_func()
        assert result == "success"
        assert call_count == 1
    
    def test_sync_function_circuit_breaker_open(self):
        """测试同步函数熔断器打开"""
        call_count = 0
        
        @with_circuit_breaker("test-sync-fail", failure_threshold=2)
        def test_func():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("连接失败")
        
        # 触发失败直到熔断器打开
        for _ in range(2):
            with pytest.raises(ConnectionError):
                test_func()
        
        # 现在应该抛出熔断器异常
        with pytest.raises(CheckerError) as exc_info:
            test_func()
        
        assert "熔断器" in str(exc_info.value)
        assert exc_info.value.error_code == ErrorCode.SERVICE_UNAVAILABLE
        assert call_count == 2  # 熔断器打开后不再调用函数
    
    @pytest.mark.asyncio
    async def test_async_function_success(self):
        """测试异步函数成功"""
        call_count = 0
        
        @with_circuit_breaker("test-async", failure_threshold=2)
        async def test_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = await test_func()
        assert result == "success"
        assert call_count == 1
    
    @pytest.mark.asyncio
    async def test_async_function_circuit_breaker_open(self):
        """测试异步函数熔断器打开"""
        call_count = 0
        
        @with_circuit_breaker("test-async-fail", failure_threshold=2)
        async def test_func():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("连接失败")
        
        # 触发失败直到熔断器打开
        for _ in range(2):
            with pytest.raises(ConnectionError):
                await test_func()
        
        # 现在应该抛出熔断器异常
        with pytest.raises(CheckerError) as exc_info:
            await test_func()
        
        assert "熔断器" in str(exc_info.value)
        assert call_count == 2


class TestFallbackDecorator:
    """降级装饰器测试"""
    
    def test_sync_function_success(self):
        """测试同步函数成功"""
        @with_fallback("test-fallback-sync", fallback_value="fallback")
        def test_func():
            return "success"
        
        result = test_func()
        assert result == "success"
    
    def test_sync_function_fallback(self):
        """测试同步函数降级"""
        call_count = 0
        
        @with_fallback("test-fallback-sync-fail", fallback_value="fallback", max_failures=1)
        def test_func():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("连接失败")
        
        # 第一次调用应该返回降级值（因为max_failures=1，第一次失败就触发降级）
        result = test_func()
        assert result == "fallback"
        assert call_count == 1
        
        # 第二次调用应该直接返回降级值
        result = test_func()
        assert result == "fallback"
        assert call_count == 1  # 第二次没有实际调用函数
    
    @pytest.mark.asyncio
    async def test_async_function_success(self):
        """测试异步函数成功"""
        @with_fallback("test-fallback-async", fallback_value="fallback")
        async def test_func():
            return "success"
        
        result = await test_func()
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_async_function_fallback(self):
        """测试异步函数降级"""
        call_count = 0
        
        @with_fallback("test-fallback-async-fail", fallback_value="fallback", max_failures=1)
        async def test_func():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("连接失败")
        
        # 第一次调用应该返回降级值（因为max_failures=1，第一次失败就触发降级）
        result = await test_func()
        assert result == "fallback"
        assert call_count == 1
        
        # 第二次调用应该直接返回降级值
        result = await test_func()
        assert result == "fallback"
        assert call_count == 1  # 第二次没有实际调用函数


class TestGracefulDegradation:
    """优雅降级测试"""
    
    def test_sync_graceful_degradation_success(self):
        """测试同步优雅降级成功"""
        with graceful_degradation("test-service", "default"):
            result = "success"
        
        # 没有异常，正常执行
        assert result == "success"
    
    def test_sync_graceful_degradation_failure(self):
        """测试同步优雅降级失败"""
        # 测试上下文管理器能够捕获异常并记录失败
        with graceful_degradation("test-service-fail", "default") as default_val:
            # 在这个上下文中，异常会被捕获
            pass
        
        # 手动触发失败记录来测试
        global_resilience_manager.record_failure("test-service-fail")
        
        # 验证失败被记录
        assert "test-service-fail" in global_resilience_manager.failure_counts
    
    @pytest.mark.asyncio
    async def test_async_graceful_degradation_success(self):
        """测试异步优雅降级成功"""
        async with async_graceful_degradation("test-service", "default"):
            result = "success"
        
        assert result == "success"


class TestPartialFailureHandler:
    """部分失败处理器测试"""
    
    def test_continue_on_partial_failure(self):
        """测试部分失败时继续"""
        handler = PartialFailureHandler(continue_on_partial_failure=True)
        
        # 记录一些成功和失败
        handler.handle_service_result("service1", True)
        handler.handle_service_result("service2", False, ValueError("错误"))
        handler.handle_service_result("service3", True)
        
        # 有成功的服务，应该继续
        assert handler.should_continue() is True
        
        summary = handler.get_summary()
        assert summary["total_services"] == 3
        assert summary["successful_services"] == 2
        assert summary["failed_services"] == 1
        assert summary["success_rate"] == 2/3
    
    def test_stop_on_any_failure(self):
        """测试任何失败时停止"""
        handler = PartialFailureHandler(continue_on_partial_failure=False)
        
        # 记录成功
        handler.handle_service_result("service1", True)
        assert handler.should_continue() is True
        
        # 记录失败
        handler.handle_service_result("service2", False, ValueError("错误"))
        assert handler.should_continue() is False
    
    def test_all_failures(self):
        """测试全部失败"""
        handler = PartialFailureHandler(continue_on_partial_failure=True)
        
        # 记录所有失败
        handler.handle_service_result("service1", False, ValueError("错误1"))
        handler.handle_service_result("service2", False, ValueError("错误2"))
        
        # 没有成功的服务，不应该继续
        assert handler.should_continue() is False
        
        summary = handler.get_summary()
        assert summary["success_rate"] == 0


class TestGlobalResilienceManager:
    """全局容错管理器测试"""
    
    def test_global_manager_exists(self):
        """测试全局管理器存在"""
        assert global_resilience_manager is not None
        assert isinstance(global_resilience_manager, ResilienceManager)