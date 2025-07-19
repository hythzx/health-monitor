"""测试数据模型"""

import pytest
from datetime import datetime
from health_monitor.models.health_check import HealthCheckResult, StateChange, AlertMessage


class TestHealthCheckResult:
    """测试HealthCheckResult数据模型"""
    
    def test_create_health_check_result(self):
        """测试创建健康检查结果"""
        result = HealthCheckResult(
            service_name="test-service",
            service_type="redis",
            is_healthy=True,
            response_time=0.5
        )
        
        assert result.service_name == "test-service"
        assert result.service_type == "redis"
        assert result.is_healthy is True
        assert result.response_time == 0.5
        assert result.error_message is None
        assert isinstance(result.timestamp, datetime)
        assert isinstance(result.metadata, dict)
    
    def test_create_unhealthy_result(self):
        """测试创建不健康的检查结果"""
        result = HealthCheckResult(
            service_name="test-service",
            service_type="mysql",
            is_healthy=False,
            response_time=5.0,
            error_message="连接超时"
        )
        
        assert result.is_healthy is False
        assert result.error_message == "连接超时"


class TestStateChange:
    """测试StateChange数据模型"""
    
    def test_create_state_change(self):
        """测试创建状态变化事件"""
        change = StateChange(
            service_name="test-service",
            service_type="redis",
            old_state=True,
            new_state=False,
            error_message="服务不可用"
        )
        
        assert change.service_name == "test-service"
        assert change.service_type == "redis"
        assert change.old_state is True
        assert change.new_state is False
        assert change.error_message == "服务不可用"
        assert isinstance(change.timestamp, datetime)


class TestAlertMessage:
    """测试AlertMessage数据模型"""
    
    def test_create_alert_message(self):
        """测试创建告警消息"""
        alert = AlertMessage(
            service_name="test-service",
            service_type="mongodb",
            status="DOWN",
            error_message="数据库连接失败"
        )
        
        assert alert.service_name == "test-service"
        assert alert.service_type == "mongodb"
        assert alert.status == "DOWN"
        assert alert.error_message == "数据库连接失败"
        assert isinstance(alert.timestamp, datetime)
        assert isinstance(alert.metadata, dict)