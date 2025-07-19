"""错误处理器和重试机制"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import Callable, Any, Optional, Dict, List, Union, TypeVar

from .exceptions import HealthMonitorError

T = TypeVar('T')
logger = logging.getLogger(__name__)


class RetryStrategy(Enum):
    """重试策略"""
    FIXED_DELAY = "fixed_delay"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"


@dataclass
class RetryConfig:
    """重试配置"""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    backoff_multiplier: float = 2.0
    jitter: bool = True
    retryable_errors: Optional[List[type]] = None


class ErrorHandler:
    """统一错误处理器"""

    def __init__(self):
        self.error_stats: Dict[str, int] = {}
        self.recovery_handlers: Dict[type, Callable] = {}

    def register_recovery_handler(self, error_type: type, handler: Callable):
        """注册错误恢复处理器"""
        self.recovery_handlers[error_type] = handler
        logger.info(f"注册错误恢复处理器: {error_type.__name__}")

    def handle_error(
            self,
            error: Exception,
            context: Optional[Dict[str, Any]] = None
    ) -> Optional[Any]:
        """处理错误并尝试恢复"""
        context = context or {}

        # 记录错误统计
        error_type = type(error).__name__
        self.error_stats[error_type] = self.error_stats.get(error_type, 0) + 1

        # 格式化错误信息
        if isinstance(error, HealthMonitorError):
            error_msg = error.format_error()
            error_dict = error.to_dict()
            logger.error(f"处理系统错误: {error_msg}",
                         extra={'error_details': error_dict})
        else:
            logger.error(f"处理未知错误: {str(error)}", exc_info=True)

        # 尝试错误恢复
        for error_type, handler in self.recovery_handlers.items():
            if isinstance(error, error_type):
                try:
                    logger.info(f"尝试使用恢复处理器: {error_type.__name__}")
                    return handler(error, context)
                except Exception as recovery_error:
                    logger.error(f"错误恢复失败: {str(recovery_error)}", exc_info=True)

        return None

    def get_error_stats(self) -> Dict[str, int]:
        """获取错误统计信息"""
        return self.error_stats.copy()

    def reset_error_stats(self):
        """重置错误统计"""
        self.error_stats.clear()


class RetryHandler:
    """重试处理器"""

    def __init__(self, config: RetryConfig):
        self.config = config

    def calculate_delay(self, attempt: int) -> float:
        """计算重试延迟时间"""
        if self.config.strategy == RetryStrategy.FIXED_DELAY:
            delay = self.config.base_delay
        elif self.config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = self.config.base_delay * (
                        self.config.backoff_multiplier ** (attempt - 1))
        elif self.config.strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = self.config.base_delay * attempt
        else:
            delay = self.config.base_delay

        # 限制最大延迟
        delay = min(delay, self.config.max_delay)

        # 添加抖动
        if self.config.jitter:
            import random
            delay = delay * (0.5 + random.random() * 0.5)

        return delay

    def should_retry(self, error: Exception, attempt: int) -> bool:
        """判断是否应该重试"""
        if attempt >= self.config.max_attempts:
            return False

        # 检查是否为可重试的错误类型
        if self.config.retryable_errors:
            return any(isinstance(error, error_type) for error_type in
                       self.config.retryable_errors)

        # 对于HealthMonitorError，检查recoverable标志
        if isinstance(error, HealthMonitorError):
            return error.recoverable

        # 默认情况下，网络相关错误可重试
        retryable_error_types = (
            ConnectionError,
            TimeoutError,
            OSError,
        )

        return isinstance(error, retryable_error_types)


def retry_on_error(
        max_attempts: int = 3,
        base_delay: float = 1.0,
        strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF,
        retryable_errors: Optional[List[type]] = None
):
    """重试装饰器"""
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        strategy=strategy,
        retryable_errors=retryable_errors
    )
    retry_handler = RetryHandler(config)

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs) -> T:
                last_error = None

                for attempt in range(1, config.max_attempts + 1):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as error:
                        last_error = error

                        if not retry_handler.should_retry(error, attempt):
                            logger.warning(
                                f"错误不可重试或达到最大重试次数: {str(error)}")
                            raise

                        if attempt < config.max_attempts:
                            delay = retry_handler.calculate_delay(attempt)
                            logger.warning(
                                f"函数 {func.__name__} 执行失败 (尝试 {attempt}/{config.max_attempts}): "
                                f"{str(error)}，{delay:.2f}秒后重试"
                            )
                            await asyncio.sleep(delay)
                        else:
                            logger.error(
                                f"函数 {func.__name__} 重试失败，已达到最大重试次数")

                raise last_error

            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs) -> T:
                last_error = None

                for attempt in range(1, config.max_attempts + 1):
                    try:
                        return func(*args, **kwargs)
                    except Exception as error:
                        last_error = error

                        if not retry_handler.should_retry(error, attempt):
                            logger.warning(
                                f"错误不可重试或达到最大重试次数: {str(error)}")
                            raise

                        if attempt < config.max_attempts:
                            delay = retry_handler.calculate_delay(attempt)
                            logger.warning(
                                f"函数 {func.__name__} 执行失败 (尝试 {attempt}/{config.max_attempts}): "
                                f"{str(error)}，{delay:.2f}秒后重试"
                            )
                            time.sleep(delay)
                        else:
                            logger.error(
                                f"函数 {func.__name__} 重试失败，已达到最大重试次数")

                raise last_error

            return sync_wrapper

    return decorator


def handle_errors(
        error_handler: Optional[ErrorHandler] = None,
        suppress_errors: bool = False,
        default_return: Any = None
):
    """错误处理装饰器"""

    def decorator(func: Callable[..., T]) -> Callable[..., Union[T, Any]]:
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs) -> Union[T, Any]:
                try:
                    return await func(*args, **kwargs)
                except Exception as error:
                    if error_handler:
                        recovery_result = error_handler.handle_error(
                            error,
                            {'function': func.__name__, 'args': args, 'kwargs': kwargs}
                        )
                        if recovery_result is not None:
                            return recovery_result

                    if suppress_errors:
                        logger.warning(f"抑制错误: {str(error)}")
                        return default_return

                    raise

            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs) -> Union[T, Any]:
                try:
                    return func(*args, **kwargs)
                except Exception as error:
                    if error_handler:
                        recovery_result = error_handler.handle_error(
                            error,
                            {'function': func.__name__, 'args': args, 'kwargs': kwargs}
                        )
                        if recovery_result is not None:
                            return recovery_result

                    if suppress_errors:
                        logger.warning(f"抑制错误: {str(error)}")
                        return default_return

                    raise

            return sync_wrapper

    return decorator


# 全局错误处理器实例
global_error_handler = ErrorHandler()


def setup_default_recovery_handlers():
    """设置默认的错误恢复处理器"""

    def handle_connection_error(error: Exception, context: Dict[str, Any]) -> Optional[
        Any]:
        """处理连接错误"""
        logger.info("尝试恢复连接错误")
        # 这里可以实现连接重置、重新初始化等逻辑
        return None

    def handle_config_error(error: Exception, context: Dict[str, Any]) -> Optional[Any]:
        """处理配置错误"""
        logger.info("尝试恢复配置错误")
        # 这里可以实现配置回滚、使用默认配置等逻辑
        return None

    # 延迟导入以避免循环导入
    from .exceptions import ConfigError

    global_error_handler.register_recovery_handler(ConnectionError,
                                                   handle_connection_error)
    global_error_handler.register_recovery_handler(ConfigError, handle_config_error)


# 初始化默认恢复处理器
setup_default_recovery_handlers()
