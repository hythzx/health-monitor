"""错误处理器测试"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch

from health_monitor.utils.error_handler import (
    ErrorHandler,
    RetryHandler,
    RetryConfig,
    RetryStrategy,
    retry_on_error,
    handle_errors,
    global_error_handler
)
from health_monitor.utils.exceptions import (
    HealthMonitorError,
    ErrorCode,
    CheckerError,
    ConfigError
)


class TestErrorHandler:
    """错误处理器测试"""
    
    def setup_method(self):
        """测试前设置"""
        self.error_handler = ErrorHandler()
    
    def test_handle_health_monitor_error(self):
        """测试处理HealthMonitorError"""
        error = CheckerError(
            "连接失败",
            ErrorCode.CONNECTION_ERROR,
            service_name="redis-test",
            service_type="redis"
        )
        
        result = self.error_handler.handle_error(error)
        assert result is None
        assert "CheckerError" in self.error_handler.get_error_stats()
        assert self.error_handler.get_error_stats()["CheckerError"] == 1
    
    def test_handle_unknown_error(self):
        """测试处理未知错误"""
        error = ValueError("测试错误")
        
        result = self.error_handler.handle_error(error)
        assert result is None
        assert "ValueError" in self.error_handler.get_error_stats()
    
    def test_register_recovery_handler(self):
        """测试注册恢复处理器"""
        def recovery_handler(error, context):
            return "recovered"
        
        self.error_handler.register_recovery_handler(ValueError, recovery_handler)
        
        error = ValueError("测试错误")
        result = self.error_handler.handle_error(error)
        assert result == "recovered"
    
    def test_recovery_handler_failure(self):
        """测试恢复处理器失败"""
        def failing_recovery_handler(error, context):
            raise RuntimeError("恢复失败")
        
        self.error_handler.register_recovery_handler(ValueError, failing_recovery_handler)
        
        error = ValueError("测试错误")
        result = self.error_handler.handle_error(error)
        assert result is None
    
    def test_error_stats(self):
        """测试错误统计"""
        self.error_handler.handle_error(ValueError("错误1"))
        self.error_handler.handle_error(ValueError("错误2"))
        self.error_handler.handle_error(TypeError("错误3"))
        
        stats = self.error_handler.get_error_stats()
        assert stats["ValueError"] == 2
        assert stats["TypeError"] == 1
        
        self.error_handler.reset_error_stats()
        assert len(self.error_handler.get_error_stats()) == 0


class TestRetryHandler:
    """重试处理器测试"""
    
    def test_fixed_delay_strategy(self):
        """测试固定延迟策略"""
        config = RetryConfig(
            base_delay=2.0,
            strategy=RetryStrategy.FIXED_DELAY,
            jitter=False
        )
        handler = RetryHandler(config)
        
        assert handler.calculate_delay(1) == 2.0
        assert handler.calculate_delay(3) == 2.0
    
    def test_exponential_backoff_strategy(self):
        """测试指数退避策略"""
        config = RetryConfig(
            base_delay=1.0,
            strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            backoff_multiplier=2.0,
            jitter=False
        )
        handler = RetryHandler(config)
        
        assert handler.calculate_delay(1) == 1.0
        assert handler.calculate_delay(2) == 2.0
        assert handler.calculate_delay(3) == 4.0
    
    def test_linear_backoff_strategy(self):
        """测试线性退避策略"""
        config = RetryConfig(
            base_delay=1.0,
            strategy=RetryStrategy.LINEAR_BACKOFF,
            jitter=False
        )
        handler = RetryHandler(config)
        
        assert handler.calculate_delay(1) == 1.0
        assert handler.calculate_delay(2) == 2.0
        assert handler.calculate_delay(3) == 3.0
    
    def test_max_delay_limit(self):
        """测试最大延迟限制"""
        config = RetryConfig(
            base_delay=1.0,
            max_delay=5.0,
            strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            backoff_multiplier=2.0,
            jitter=False
        )
        handler = RetryHandler(config)
        
        assert handler.calculate_delay(10) <= 5.0
    
    def test_should_retry_health_monitor_error(self):
        """测试HealthMonitorError重试判断"""
        config = RetryConfig(max_attempts=3)
        handler = RetryHandler(config)
        
        # 可恢复错误应该重试
        recoverable_error = CheckerError("连接失败", recoverable=True)
        assert handler.should_retry(recoverable_error, 1) is True
        assert handler.should_retry(recoverable_error, 3) is False
        
        # 不可恢复错误不应该重试
        non_recoverable_error = ConfigError("配置错误", recoverable=False)
        assert handler.should_retry(non_recoverable_error, 1) is False
    
    def test_should_retry_specific_errors(self):
        """测试特定错误类型重试判断"""
        config = RetryConfig(
            max_attempts=3,
            retryable_errors=[ConnectionError, TimeoutError]
        )
        handler = RetryHandler(config)
        
        assert handler.should_retry(ConnectionError("连接失败"), 1) is True
        assert handler.should_retry(ValueError("值错误"), 1) is False
    
    def test_should_retry_max_attempts(self):
        """测试最大重试次数限制"""
        config = RetryConfig(max_attempts=2)
        handler = RetryHandler(config)
        
        error = ConnectionError("连接失败")
        assert handler.should_retry(error, 1) is True
        assert handler.should_retry(error, 2) is False


class TestRetryDecorator:
    """重试装饰器测试"""
    
    def test_sync_function_success(self):
        """测试同步函数成功执行"""
        call_count = 0
        
        @retry_on_error(max_attempts=3)
        def test_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = test_func()
        assert result == "success"
        assert call_count == 1
    
    def test_sync_function_retry_success(self):
        """测试同步函数重试后成功"""
        call_count = 0
        
        @retry_on_error(max_attempts=3, base_delay=0.01)
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("连接失败")
            return "success"
        
        result = test_func()
        assert result == "success"
        assert call_count == 3
    
    def test_sync_function_retry_failure(self):
        """测试同步函数重试失败"""
        call_count = 0
        
        @retry_on_error(max_attempts=2, base_delay=0.01)
        def test_func():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("连接失败")
        
        with pytest.raises(ConnectionError):
            test_func()
        assert call_count == 2
    
    @pytest.mark.asyncio
    async def test_async_function_success(self):
        """测试异步函数成功执行"""
        call_count = 0
        
        @retry_on_error(max_attempts=3)
        async def test_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = await test_func()
        assert result == "success"
        assert call_count == 1
    
    @pytest.mark.asyncio
    async def test_async_function_retry_success(self):
        """测试异步函数重试后成功"""
        call_count = 0
        
        @retry_on_error(max_attempts=3, base_delay=0.01)
        async def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("连接失败")
            return "success"
        
        result = await test_func()
        assert result == "success"
        assert call_count == 3
    
    def test_non_retryable_error(self):
        """测试不可重试错误"""
        call_count = 0
        
        @retry_on_error(max_attempts=3, base_delay=0.01)
        def test_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("值错误")
        
        with pytest.raises(ValueError):
            test_func()
        assert call_count == 1


class TestHandleErrorsDecorator:
    """错误处理装饰器测试"""
    
    def test_sync_function_no_error(self):
        """测试同步函数无错误"""
        @handle_errors()
        def test_func():
            return "success"
        
        result = test_func()
        assert result == "success"
    
    def test_sync_function_suppress_error(self):
        """测试同步函数抑制错误"""
        @handle_errors(suppress_errors=True, default_return="default")
        def test_func():
            raise ValueError("测试错误")
        
        result = test_func()
        assert result == "default"
    
    def test_sync_function_with_error_handler(self):
        """测试同步函数使用错误处理器"""
        error_handler = ErrorHandler()
        
        def recovery_handler(error, context):
            return "recovered"
        
        error_handler.register_recovery_handler(ValueError, recovery_handler)
        
        @handle_errors(error_handler=error_handler)
        def test_func():
            raise ValueError("测试错误")
        
        result = test_func()
        assert result == "recovered"
    
    @pytest.mark.asyncio
    async def test_async_function_no_error(self):
        """测试异步函数无错误"""
        @handle_errors()
        async def test_func():
            return "success"
        
        result = await test_func()
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_async_function_suppress_error(self):
        """测试异步函数抑制错误"""
        @handle_errors(suppress_errors=True, default_return="default")
        async def test_func():
            raise ValueError("测试错误")
        
        result = await test_func()
        assert result == "default"


class TestGlobalErrorHandler:
    """全局错误处理器测试"""
    
    def test_global_error_handler_exists(self):
        """测试全局错误处理器存在"""
        assert global_error_handler is not None
        assert isinstance(global_error_handler, ErrorHandler)
    
    def test_default_recovery_handlers_registered(self):
        """测试默认恢复处理器已注册"""
        assert len(global_error_handler.recovery_handlers) > 0