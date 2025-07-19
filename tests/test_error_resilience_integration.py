"""错误处理和容错机制集成测试"""

import pytest
import asyncio
import time
from unittest.mock import Mock

from health_monitor.utils.exceptions import (
    CheckerError,
    ErrorCode,
    AlertSendError
)
from health_monitor.utils.error_handler import (
    retry_on_error,
    handle_errors,
    global_error_handler
)
from health_monitor.utils.resilience import (
    with_circuit_breaker,
    with_fallback,
    PartialFailureHandler,
    global_resilience_manager
)


class TestErrorResilienceIntegration:
    """错误处理和容错机制集成测试"""
    
    def setup_method(self):
        """测试前设置"""
        # 清理全局状态
        global_error_handler.reset_error_stats()
        global_resilience_manager.circuit_breakers.clear()
        global_resilience_manager.fallback_configs.clear()
        global_resilience_manager.service_states.clear()
        global_resilience_manager.failure_counts.clear()
    
    def test_retry_with_circuit_breaker_integration(self):
        """测试重试机制与熔断器集成"""
        call_count = 0
        
        @retry_on_error(max_attempts=2, base_delay=0.01)
        @with_circuit_breaker("integration-test", failure_threshold=3)
        def unstable_service():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # 前2次调用失败
                raise ConnectionError(f"连接失败 {call_count}")
            return "success"
        
        # 第一次调用会重试，但都失败（2次实际调用）
        with pytest.raises(ConnectionError):
            unstable_service()
        
        # 第二次调用应该成功（第3次实际调用）
        result = unstable_service()
        assert result == "success"
        
        # 验证调用次数
        assert call_count == 3  # 第一次调用重试2次，第二次调用成功1次
        
        # 验证熔断器没有打开（因为最后成功了）
        circuit_breaker = global_resilience_manager.get_circuit_breaker("integration-test")
        assert circuit_breaker.failure_count < 3  # 成功后失败计数被重置
    
    @pytest.mark.asyncio
    async def test_fallback_with_error_handler_integration(self):
        """测试降级机制与错误处理器集成"""
        call_count = 0
        
        def recovery_handler(error, context):
            return "recovered_value"
        
        global_error_handler.register_recovery_handler(ConnectionError, recovery_handler)
        
        @handle_errors(error_handler=global_error_handler)
        @with_fallback("integration-fallback", fallback_value="fallback_value", max_failures=1)
        async def failing_service():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("服务不可用")
        
        # 第一次调用应该返回降级值
        result = await failing_service()
        assert result == "fallback_value"
        assert call_count == 1
        
        # 第二次调用应该直接返回降级值（不调用函数）
        result = await failing_service()
        assert result == "fallback_value"
        assert call_count == 1
    
    def test_partial_failure_with_resilience(self):
        """测试部分失败处理与容错机制"""
        handler = PartialFailureHandler(continue_on_partial_failure=True)
        
        # 模拟多个服务的健康检查
        services = [
            ("redis", True, None),
            ("mysql", False, ConnectionError("连接失败")),
            ("mongodb", True, None),
            ("api", False, TimeoutError("超时")),
        ]
        
        for service_name, success, error in services:
            handler.handle_service_result(service_name, success, error)
            
            if not success:
                # 记录失败到容错管理器
                global_resilience_manager.record_failure(service_name)
        
        # 应该继续运行（有成功的服务）
        assert handler.should_continue() is True
        
        summary = handler.get_summary()
        assert summary["total_services"] == 4
        assert summary["successful_services"] == 2
        assert summary["failed_services"] == 2
        assert summary["success_rate"] == 0.5
        
        # 验证失败的服务被记录
        assert "mysql" in global_resilience_manager.failure_counts
        assert "api" in global_resilience_manager.failure_counts
    
    def test_complex_error_scenario(self):
        """测试复杂错误场景"""
        # 创建一个模拟的健康检查器，集成多种错误处理机制
        
        @handle_errors(suppress_errors=True, default_return={"status": "error", "healthy": False})
        @retry_on_error(max_attempts=2, base_delay=0.01)
        @with_fallback("complex-service", fallback_value={"status": "degraded", "healthy": False})
        @with_circuit_breaker("complex-service", failure_threshold=2)
        def complex_health_check():
            # 模拟不同类型的错误
            import random
            error_type = random.choice([
                CheckerError("服务检查失败", ErrorCode.CONNECTION_ERROR),
                AlertSendError("告警发送失败"),
                ConnectionError("网络连接失败"),
                TimeoutError("请求超时")
            ])
            raise error_type
        
        # 多次调用，观察不同的错误处理行为
        results = []
        for i in range(5):
            try:
                result = complex_health_check()
                results.append(result)
            except Exception as e:
                results.append({"error": str(e)})
        
        # 验证所有调用都有结果（通过各种错误处理机制）
        assert len(results) == 5
        
        # 验证所有调用都返回了结果（通过错误抑制机制）
        for result in results:
            assert result is not None
            # 结果应该是默认返回值或降级值
            if isinstance(result, dict):
                assert "status" in result
    
    def test_service_recovery_scenario(self):
        """测试服务恢复场景"""
        call_count = 0
        
        @with_fallback("recovery-test", fallback_value="fallback", max_failures=2)
        def recovering_service():
            nonlocal call_count
            call_count += 1
            
            # 前3次失败，第4次开始成功
            if call_count <= 3:
                raise ConnectionError(f"失败 {call_count}")
            return f"成功 {call_count}"
        
        # 前两次调用失败，触发降级
        with pytest.raises(ConnectionError):
            recovering_service()
        
        # 第二次失败后应该使用降级
        result = recovering_service()
        assert result == "fallback"
        
        # 服务恢复后应该正常工作
        # 但由于已经处于降级状态，仍然返回降级值
        result = recovering_service()
        assert result == "fallback"
        
        # 验证服务状态
        from health_monitor.utils.resilience import ServiceState
        service_state = global_resilience_manager.get_service_state("recovery-test")
        assert service_state == ServiceState.DEGRADED