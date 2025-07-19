"""健康检查相关的数据模型"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from datetime import datetime


@dataclass
class HealthCheckResult:
    """健康检查结果数据模型"""
    service_name: str
    service_type: str
    is_healthy: bool
    response_time: float
    error_message: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StateChange:
    """服务状态变化事件模型"""
    service_name: str
    service_type: str
    old_state: bool
    new_state: bool
    timestamp: datetime = field(default_factory=datetime.now)
    error_message: Optional[str] = None
    response_time: Optional[float] = None


@dataclass
class AlertMessage:
    """告警消息模型"""
    service_name: str
    service_type: str
    status: str  # "DOWN", "UP", "DEGRADED"
    timestamp: datetime = field(default_factory=datetime.now)
    error_message: Optional[str] = None
    response_time: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)