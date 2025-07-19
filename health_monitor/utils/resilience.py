"""健壮性和容错机制"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
from contextlib import asynccontextmanager, contextmanager

from .exceptions import (
    HealthMonitorError,
    ErrorCode,
    ConfigError,
    CheckerError,
    AlertError
)
from .error_handler import retry_on_error, handle_errors, global_error_handler

logger = logging.getLogger(__name__)


class ServiceState(Enum):
    """服务状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class FallbackConfig:
    """降级配置"""
    enabled: bool = True
    fallback_value: Any = None
    fallback_function: Optional[Callable] = None
    max_failures: int = 5
    failure_window: int = 300  # 5分钟
    recovery_threshold: int = 2


@dataclass
class CircuitBreakerConfig:
    """熔断器配置"""
    failure_threshold: int = 5
    recovery_timeout: int = 60
    half_open_max_calls: int = 3


class CircuitBreakerState(Enum):
    """熔断器状态"""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """熔断器实现"""
    name: str
    config: CircuitBreakerConfig
    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0
    success_count: int = 0
    
    def should_allow_request(self) -> bool:
        """判断是否允许请求"""
        current_time = time.time()
        
        if self.state == CircuitBreakerState.CLOSED:
            return True
        elif self.state == CircuitBreakerState.OPEN:
            if current_time - self.last_failure_time >= self.config.recovery_timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                self.success_count = 0
                logger.info(f"熔断器 {self.name} 进入半开状态")
                return True
            return False
        elif self.state == CircuitBreakerState.HALF_OPEN:
            return self.success_count < self.config.half_open_max_calls
        
        return False
    
    def record_success(self):
        """记录成功"""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.half_open_max_calls:
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                logger.info(f"熔断器 {self.name} 恢复到关闭状态")
        elif self.state == CircuitBreakerState.CLOSED:
            self.failure_count = 0
    
    def record_failure(self):
        """记录失败"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitBreakerState.CLOSED:
            if self.failure_count >= self.config.failure_threshold:
                self.state = CircuitBreakerState.OPEN
                logger.warning(f"熔断器 {self.name} 打开，失败次数: {self.failure_count}")
        elif self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.OPEN
            logger.warning(f"熔断器 {self.name} 重新打开")


class ResilienceManager:
    """容错管理器"""
    
    def __init__(self):
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.fallback_configs: Dict[str, FallbackConfig] = {}
        self.service_states: Dict[str, ServiceState] = {}
        self.failure_counts: Dict[str, List[float]] = {}
        
    def register_circuit_breaker(
        self,
        name: str,
        config: CircuitBreakerConfig
    ) -> CircuitBreaker:
        """注册熔断器"""
        circuit_breaker = CircuitBreaker(name, config)
        self.circuit_breakers[name] = circuit_breaker
        logger.info(f"注册熔断器: {name}")
        return circuit_breaker
    
    def register_fallback(
        self,
        name: str,
        config: FallbackConfig
    ):
        """注册降级配置"""
        self.fallback_configs[name] = config
        logger.info(f"注册降级配置: {name}")
    
    def get_circuit_breaker(self, name: str) -> Optional[CircuitBreaker]:
        """获取熔断器"""
        return self.circuit_breakers.get(name)
    
    def get_fallback_config(self, name: str) -> Optional[FallbackConfig]:
        """获取降级配置"""
        return self.fallback_configs.get(name)
    
    def update_service_state(self, service_name: str, state: ServiceState):
        """更新服务状态"""
        old_state = self.service_states.get(service_name, ServiceState.UNKNOWN)
        self.service_states[service_name] = state
        
        if old_state != state:
            logger.info(f"服务 {service_name} 状态变更: {old_state.value} -> {state.value}")
    
    def get_service_state(self, service_name: str) -> ServiceState:
        """获取服务状态"""
        return self.service_states.get(service_name, ServiceState.UNKNOWN)
    
    def record_failure(self, service_name: str):
        """记录服务失败"""
        current_time = time.time()
        
        if service_name not in self.failure_counts:
            self.failure_counts[service_name] = []
        
        self.failure_counts[service_name].append(current_time)
        
        # 清理过期的失败记录
        fallback_config = self.get_fallback_config(service_name)
        if fallback_config:
            window_start = current_time - fallback_config.failure_window
            self.failure_counts[service_name] = [
                t for t in self.failure_counts[service_name] if t >= window_start
            ]
            
            # 检查是否需要降级
            if len(self.failure_counts[service_name]) >= fallback_config.max_failures:
                self.update_service_state(service_name, ServiceState.DEGRADED)
    
    def should_use_fallback(self, service_name: str) -> bool:
        """判断是否应该使用降级"""
        fallback_config = self.get_fallback_config(service_name)
        if not fallback_config or not fallback_config.enabled:
            return False
        
        service_state = self.get_service_state(service_name)
        return service_state in [ServiceState.DEGRADED, ServiceState.UNHEALTHY]
    
    def get_fallback_value(self, service_name: str) -> Any:
        """获取降级值"""
        fallback_config = self.get_fallback_config(service_name)
        if not fallback_config:
            return None
        
        if fallback_config.fallback_function:
            try:
                return fallback_config.fallback_function()
            except Exception as e:
                logger.error(f"降级函数执行失败: {str(e)}")
                return fallback_config.fallback_value
        
        return fallback_config.fallback_value


# 全局容错管理器实例
global_resilience_manager = ResilienceManager()


def with_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: int = 60,
    half_open_max_calls: int = 3
):
    """熔断器装饰器"""
    config = CircuitBreakerConfig(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        half_open_max_calls=half_open_max_calls
    )
    
    circuit_breaker = global_resilience_manager.register_circuit_breaker(name, config)
    
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            async def async_wrapper(*args, **kwargs):
                if not circuit_breaker.should_allow_request():
                    raise CheckerError(
                        f"熔断器 {name} 处于打开状态",
                        ErrorCode.SERVICE_UNAVAILABLE,
                        recoverable=False
                    )
                
                try:
                    result = await func(*args, **kwargs)
                    circuit_breaker.record_success()
                    return result
                except Exception as e:
                    circuit_breaker.record_failure()
                    raise
            
            return async_wrapper
        else:
            def sync_wrapper(*args, **kwargs):
                if not circuit_breaker.should_allow_request():
                    raise CheckerError(
                        f"熔断器 {name} 处于打开状态",
                        ErrorCode.SERVICE_UNAVAILABLE,
                        recoverable=False
                    )
                
                try:
                    result = func(*args, **kwargs)
                    circuit_breaker.record_success()
                    return result
                except Exception as e:
                    circuit_breaker.record_failure()
                    raise
            
            return sync_wrapper
    
    return decorator


def with_fallback(
    service_name: str,
    fallback_value: Any = None,
    fallback_function: Optional[Callable] = None,
    max_failures: int = 5,
    failure_window: int = 300
):
    """降级装饰器"""
    config = FallbackConfig(
        enabled=True,
        fallback_value=fallback_value,
        fallback_function=fallback_function,
        max_failures=max_failures,
        failure_window=failure_window
    )
    
    global_resilience_manager.register_fallback(service_name, config)
    
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            async def async_wrapper(*args, **kwargs):
                # 检查是否应该使用降级
                if global_resilience_manager.should_use_fallback(service_name):
                    logger.warning(f"服务 {service_name} 使用降级响应")
                    return global_resilience_manager.get_fallback_value(service_name)
                
                try:
                    result = await func(*args, **kwargs)
                    # 成功时重置服务状态
                    global_resilience_manager.update_service_state(
                        service_name, ServiceState.HEALTHY
                    )
                    return result
                except Exception as e:
                    # 先检查当前失败次数，决定是否应该抛出异常
                    current_failures = len(global_resilience_manager.failure_counts.get(service_name, []))
                    
                    # 记录失败
                    global_resilience_manager.record_failure(service_name)
                    
                    # 如果现在应该使用降级，返回降级值
                    if global_resilience_manager.should_use_fallback(service_name):
                        logger.warning(f"服务 {service_name} 失败后使用降级响应")
                        return global_resilience_manager.get_fallback_value(service_name)
                    
                    raise
            
            return async_wrapper
        else:
            def sync_wrapper(*args, **kwargs):
                # 检查是否应该使用降级
                if global_resilience_manager.should_use_fallback(service_name):
                    logger.warning(f"服务 {service_name} 使用降级响应")
                    return global_resilience_manager.get_fallback_value(service_name)
                
                try:
                    result = func(*args, **kwargs)
                    # 成功时重置服务状态
                    global_resilience_manager.update_service_state(
                        service_name, ServiceState.HEALTHY
                    )
                    return result
                except Exception as e:
                    # 先检查当前失败次数，决定是否应该抛出异常
                    current_failures = len(global_resilience_manager.failure_counts.get(service_name, []))
                    
                    # 记录失败
                    global_resilience_manager.record_failure(service_name)
                    
                    # 如果现在应该使用降级，返回降级值
                    if global_resilience_manager.should_use_fallback(service_name):
                        logger.warning(f"服务 {service_name} 失败后使用降级响应")
                        return global_resilience_manager.get_fallback_value(service_name)
                    
                    raise
            
            return sync_wrapper
    
    return decorator


@contextmanager
def graceful_degradation(service_name: str, default_value: Any = None):
    """优雅降级上下文管理器"""
    try:
        yield default_value
    except Exception as e:
        logger.warning(f"服务 {service_name} 执行失败，使用默认值: {str(e)}")
        global_resilience_manager.record_failure(service_name)
        # 不重新抛出异常，让调用者处理默认值


@asynccontextmanager
async def async_graceful_degradation(service_name: str, default_value: Any = None):
    """异步优雅降级上下文管理器"""
    try:
        yield default_value
    except Exception as e:
        logger.warning(f"服务 {service_name} 执行失败，使用默认值: {str(e)}")
        global_resilience_manager.record_failure(service_name)
        # 不重新抛出异常，让调用者处理默认值


class PartialFailureHandler:
    """部分失败处理器"""
    
    def __init__(self, continue_on_partial_failure: bool = True):
        self.continue_on_partial_failure = continue_on_partial_failure
        self.failed_services: List[str] = []
        self.successful_services: List[str] = []
    
    def handle_service_result(
        self,
        service_name: str,
        success: bool,
        error: Optional[Exception] = None
    ):
        """处理服务结果"""
        if success:
            self.successful_services.append(service_name)
            logger.debug(f"服务 {service_name} 检查成功")
        else:
            self.failed_services.append(service_name)
            logger.warning(f"服务 {service_name} 检查失败: {str(error) if error else '未知错误'}")
    
    def should_continue(self) -> bool:
        """判断是否应该继续"""
        if not self.continue_on_partial_failure:
            return len(self.failed_services) == 0
        
        # 如果有成功的服务，继续运行
        return len(self.successful_services) > 0 or len(self.failed_services) == 0
    
    def get_summary(self) -> Dict[str, Any]:
        """获取执行摘要"""
        total = len(self.successful_services) + len(self.failed_services)
        return {
            "total_services": total,
            "successful_services": len(self.successful_services),
            "failed_services": len(self.failed_services),
            "success_rate": len(self.successful_services) / total if total > 0 else 0,
            "failed_service_names": self.failed_services,
            "successful_service_names": self.successful_services
        }


def setup_resilience_recovery_handlers():
    """设置容错相关的恢复处理器"""
    
    def handle_network_error(error: Exception, context: Dict[str, Any]) -> Optional[Any]:
        """处理网络错误"""
        service_name = context.get('service_name', 'unknown')
        logger.info(f"尝试恢复网络错误，服务: {service_name}")
        
        # 记录失败并检查是否需要降级
        global_resilience_manager.record_failure(service_name)
        
        if global_resilience_manager.should_use_fallback(service_name):
            return global_resilience_manager.get_fallback_value(service_name)
        
        return None
    
    def handle_service_unavailable(error: Exception, context: Dict[str, Any]) -> Optional[Any]:
        """处理服务不可用错误"""
        service_name = context.get('service_name', 'unknown')
        logger.info(f"服务不可用，尝试降级处理: {service_name}")
        
        global_resilience_manager.update_service_state(service_name, ServiceState.UNHEALTHY)
        
        if global_resilience_manager.should_use_fallback(service_name):
            return global_resilience_manager.get_fallback_value(service_name)
        
        return None
    
    # 注册恢复处理器
    global_error_handler.register_recovery_handler(ConnectionError, handle_network_error)
    global_error_handler.register_recovery_handler(TimeoutError, handle_network_error)
    global_error_handler.register_recovery_handler(OSError, handle_network_error)
    
    # 注册CheckerError的恢复处理器
    def handle_checker_error(error: CheckerError, context: Dict[str, Any]) -> Optional[Any]:
        if error.error_code == ErrorCode.SERVICE_UNAVAILABLE:
            return handle_service_unavailable(error, context)
        elif error.error_code in [ErrorCode.CONNECTION_ERROR, ErrorCode.TIMEOUT_ERROR]:
            return handle_network_error(error, context)
        return None
    
    global_error_handler.register_recovery_handler(CheckerError, handle_checker_error)


# 初始化容错恢复处理器
setup_resilience_recovery_handlers()