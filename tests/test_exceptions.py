"""异常类测试"""

import pytest
from datetime import datetime

from health_monitor.utils.exceptions import (
    HealthMonitorError,
    ErrorCode,
    ConfigError,
    CheckerError,
    AlertError,
    AlertConfigError,
    AlertSendError,
    SchedulerError,
    StateManagerError
)


class TestErrorCode:
    """错误代码测试"""
    
    def test_error_code_values(self):
        """测试错误代码值"""
        assert ErrorCode.UNKNOWN_ERROR.value == 1000
        assert ErrorCode.CONFIG_FILE_NOT_FOUND.value == 2000
        assert ErrorCode.CONNECTION_ERROR.value == 3001
        assert ErrorCode.ALERT_SEND_ERROR.value == 4001
    
    def test_error_code_names(self):
        """测试错误代码名称"""
        assert ErrorCode.UNKNOWN_ERROR.name == "UNKNOWN_ERROR"
        assert ErrorCode.CONFIG_VALIDATION_ERROR.name == "CONFIG_VALIDATION_ERROR"
        assert ErrorCode.TIMEOUT_ERROR.name == "TIMEOUT_ERROR"


class TestHealthMonitorError:
    """HealthMonitorError基础异常测试"""
    
    def test_basic_error_creation(self):
        """测试基础错误创建"""
        error = HealthMonitorError("测试错误")
        
        assert str(error) == "测试错误"
        assert error.message == "测试错误"
        assert error.error_code == ErrorCode.UNKNOWN_ERROR
        assert error.details == {}
        assert error.cause is None
        assert error.recoverable is True
        assert isinstance(error.timestamp, datetime)
    
    def test_error_with_details(self):
        """测试带详情的错误"""
        details = {"key1": "value1", "key2": 123}
        error = HealthMonitorError(
            "测试错误",
            ErrorCode.VALIDATION_ERROR,
            details=details,
            recoverable=False
        )
        
        assert error.error_code == ErrorCode.VALIDATION_ERROR
        assert error.details == details
        assert error.recoverable is False
    
    def test_error_with_cause(self):
        """测试带原因的错误"""
        cause = ValueError("原始错误")
        error = HealthMonitorError("测试错误", cause=cause)
        
        assert error.cause == cause
    
    def test_to_dict(self):
        """测试转换为字典"""
        details = {"service": "redis"}
        cause = ConnectionError("连接失败")
        error = HealthMonitorError(
            "测试错误",
            ErrorCode.CONNECTION_ERROR,
            details=details,
            cause=cause,
            recoverable=False
        )
        
        error_dict = error.to_dict()
        
        assert error_dict["error_code"] == ErrorCode.CONNECTION_ERROR.value
        assert error_dict["error_name"] == "CONNECTION_ERROR"
        assert error_dict["message"] == "测试错误"
        assert error_dict["details"] == details
        assert error_dict["recoverable"] is False
        assert "timestamp" in error_dict
        assert error_dict["cause"] == str(cause)
    
    def test_format_error(self):
        """测试格式化错误信息"""
        # 基础错误格式化
        error = HealthMonitorError("测试错误", ErrorCode.CONNECTION_ERROR)
        formatted = error.format_error()
        assert "[CONNECTION_ERROR] 测试错误" in formatted
        
        # 带详情的错误格式化
        error_with_details = HealthMonitorError(
            "测试错误",
            ErrorCode.CONNECTION_ERROR,
            details={"host": "localhost", "port": 6379}
        )
        formatted_with_details = error_with_details.format_error()
        assert "详情: host=localhost, port=6379" in formatted_with_details
        
        # 带原因的错误格式化
        cause = ValueError("原始错误")
        error_with_cause = HealthMonitorError("测试错误", cause=cause)
        formatted_with_cause = error_with_cause.format_error()
        assert "原因: 原始错误" in formatted_with_cause


class TestConfigError:
    """配置错误测试"""
    
    def test_config_error_creation(self):
        """测试配置错误创建"""
        error = ConfigError("配置文件不存在", ErrorCode.CONFIG_FILE_NOT_FOUND)
        
        assert isinstance(error, HealthMonitorError)
        assert error.error_code == ErrorCode.CONFIG_FILE_NOT_FOUND
        assert error.message == "配置文件不存在"
    
    def test_config_error_with_path(self):
        """测试带路径的配置错误"""
        error = ConfigError(
            "配置文件格式错误",
            ErrorCode.CONFIG_PARSE_ERROR,
            config_path="/path/to/config.yaml"
        )
        
        assert error.details["config_path"] == "/path/to/config.yaml"


class TestCheckerError:
    """健康检查器错误测试"""
    
    def test_checker_error_creation(self):
        """测试健康检查器错误创建"""
        error = CheckerError("连接失败", ErrorCode.CONNECTION_ERROR)
        
        assert isinstance(error, HealthMonitorError)
        assert error.error_code == ErrorCode.CONNECTION_ERROR
        assert error.message == "连接失败"
    
    def test_checker_error_with_service_info(self):
        """测试带服务信息的检查器错误"""
        error = CheckerError(
            "Redis连接超时",
            ErrorCode.TIMEOUT_ERROR,
            service_name="redis-cache",
            service_type="redis"
        )
        
        assert error.details["service_name"] == "redis-cache"
        assert error.details["service_type"] == "redis"


class TestAlertError:
    """告警错误测试"""
    
    def test_alert_error_creation(self):
        """测试告警错误创建"""
        error = AlertError("告警发送失败")
        
        assert isinstance(error, HealthMonitorError)
        assert error.error_code == ErrorCode.ALERT_SEND_ERROR
        assert error.message == "告警发送失败"
    
    def test_alert_error_with_name(self):
        """测试带告警名称的错误"""
        error = AlertError(
            "HTTP请求失败",
            ErrorCode.ALERT_NETWORK_ERROR,
            alert_name="dingtalk-robot"
        )
        
        assert error.details["alert_name"] == "dingtalk-robot"


class TestAlertConfigError:
    """告警配置错误测试"""
    
    def test_alert_config_error_creation(self):
        """测试告警配置错误创建"""
        error = AlertConfigError("告警配置无效", alert_name="webhook")
        
        assert isinstance(error, AlertError)
        assert error.error_code == ErrorCode.ALERT_CONFIG_ERROR
        assert error.recoverable is False
        assert error.details["alert_name"] == "webhook"


class TestAlertSendError:
    """告警发送错误测试"""
    
    def test_alert_send_error_creation(self):
        """测试告警发送错误创建"""
        error = AlertSendError("网络连接失败", alert_name="http-alert")
        
        assert isinstance(error, AlertError)
        assert error.error_code == ErrorCode.ALERT_SEND_ERROR
        assert error.recoverable is True
        assert error.details["alert_name"] == "http-alert"


class TestSchedulerError:
    """调度器错误测试"""
    
    def test_scheduler_error_creation(self):
        """测试调度器错误创建"""
        error = SchedulerError("任务调度失败", task_name="redis-check")
        
        assert isinstance(error, HealthMonitorError)
        assert error.error_code == ErrorCode.SCHEDULER_ERROR
        assert error.details["task_name"] == "redis-check"


class TestStateManagerError:
    """状态管理器错误测试"""
    
    def test_state_manager_error_creation(self):
        """测试状态管理器错误创建"""
        error = StateManagerError("状态持久化失败", ErrorCode.STATE_PERSISTENCE_ERROR)
        
        assert isinstance(error, HealthMonitorError)
        assert error.error_code == ErrorCode.STATE_PERSISTENCE_ERROR
        assert error.message == "状态持久化失败"