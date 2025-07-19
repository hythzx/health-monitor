"""自定义异常类和错误处理系统"""

import logging
import traceback
from enum import Enum
from typing import Optional, Dict, Any, Union
from datetime import datetime


class ErrorCode(Enum):
    """错误代码枚举"""
    # 通用错误 (1000-1999)
    UNKNOWN_ERROR = 1000
    INITIALIZATION_ERROR = 1001
    VALIDATION_ERROR = 1002
    
    # 配置错误 (2000-2999)
    CONFIG_FILE_NOT_FOUND = 2000
    CONFIG_PARSE_ERROR = 2001
    CONFIG_VALIDATION_ERROR = 2002
    CONFIG_RELOAD_ERROR = 2003
    
    # 健康检查错误 (3000-3999)
    CHECKER_INITIALIZATION_ERROR = 3000
    CONNECTION_ERROR = 3001
    TIMEOUT_ERROR = 3002
    AUTHENTICATION_ERROR = 3003
    PERMISSION_ERROR = 3004
    SERVICE_UNAVAILABLE = 3005
    INVALID_RESPONSE = 3006
    
    # 告警错误 (4000-4999)
    ALERT_CONFIG_ERROR = 4000
    ALERT_SEND_ERROR = 4001
    ALERT_TEMPLATE_ERROR = 4002
    ALERT_NETWORK_ERROR = 4003
    
    # 调度错误 (5000-5999)
    SCHEDULER_ERROR = 5000
    TASK_EXECUTION_ERROR = 5001
    
    # 状态管理错误 (6000-6999)
    STATE_MANAGER_ERROR = 6000
    STATE_PERSISTENCE_ERROR = 6001


class HealthMonitorError(Exception):
    """健康监控系统基础异常类"""
    
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
        recoverable: bool = True
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.cause = cause
        self.recoverable = recoverable
        self.timestamp = datetime.now()
        
    def to_dict(self) -> Dict[str, Any]:
        """将异常转换为字典格式"""
        return {
            'error_code': self.error_code.value,
            'error_name': self.error_code.name,
            'message': self.message,
            'details': self.details,
            'recoverable': self.recoverable,
            'timestamp': self.timestamp.isoformat(),
            'cause': str(self.cause) if self.cause else None,
            'traceback': traceback.format_exc() if self.cause else None
        }
    
    def format_error(self) -> str:
        """格式化错误信息"""
        error_msg = f"[{self.error_code.name}] {self.message}"
        if self.details:
            details_str = ", ".join([f"{k}={v}" for k, v in self.details.items()])
            error_msg += f" (详情: {details_str})"
        if self.cause:
            error_msg += f" (原因: {str(self.cause)})"
        return error_msg


class ConfigError(HealthMonitorError):
    """配置相关异常"""
    
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.CONFIG_VALIDATION_ERROR,
        config_path: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if config_path:
            details['config_path'] = config_path
        super().__init__(message, error_code, details, **kwargs)


class CheckerError(HealthMonitorError):
    """健康检查器相关异常"""
    
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.CONNECTION_ERROR,
        service_name: Optional[str] = None,
        service_type: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if service_name:
            details['service_name'] = service_name
        if service_type:
            details['service_type'] = service_type
        super().__init__(message, error_code, details, **kwargs)


class AlertError(HealthMonitorError):
    """告警相关异常"""
    
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.ALERT_SEND_ERROR,
        alert_name: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if alert_name:
            details['alert_name'] = alert_name
        super().__init__(message, error_code, details, **kwargs)


class AlertConfigError(AlertError):
    """告警配置异常"""
    
    def __init__(self, message: str, alert_name: Optional[str] = None, **kwargs):
        super().__init__(
            message,
            ErrorCode.ALERT_CONFIG_ERROR,
            alert_name=alert_name,
            recoverable=False,
            **kwargs
        )


class AlertSendError(AlertError):
    """告警发送异常"""
    
    def __init__(self, message: str, alert_name: Optional[str] = None, **kwargs):
        super().__init__(
            message,
            ErrorCode.ALERT_SEND_ERROR,
            alert_name=alert_name,
            recoverable=True,
            **kwargs
        )


class SchedulerError(HealthMonitorError):
    """调度器相关异常"""
    
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.SCHEDULER_ERROR,
        task_name: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.get('details', {})
        if task_name:
            details['task_name'] = task_name
        super().__init__(message, error_code, details, **kwargs)


class StateManagerError(HealthMonitorError):
    """状态管理器相关异常"""
    
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.STATE_MANAGER_ERROR,
        **kwargs
    ):
        super().__init__(message, error_code, **kwargs)