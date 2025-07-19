"""测试基础健康检查器"""

import pytest
from health_monitor.checkers.base import BaseHealthChecker
from health_monitor.models.health_check import HealthCheckResult


class MockHealthChecker(BaseHealthChecker):
    """模拟健康检查器用于测试"""
    
    async def check_health(self) -> HealthCheckResult:
        return HealthCheckResult(
            service_name=self.name,
            service_type=self.service_type,
            is_healthy=True,
            response_time=0.1
        )
    
    def validate_config(self) -> bool:
        return 'host' in self.config


class TestBaseHealthChecker:
    """测试BaseHealthChecker基类"""
    
    def test_init_checker(self):
        """测试初始化健康检查器"""
        config = {'host': 'localhost', 'port': 6379}
        checker = MockHealthChecker('test-service', config)
        
        assert checker.name == 'test-service'
        assert checker.config == config
        assert checker.service_type == 'mock'
    
    def test_get_timeout_default(self):
        """测试获取默认超时时间"""
        config = {'host': 'localhost'}
        checker = MockHealthChecker('test-service', config)
        
        assert checker.get_timeout() == 10
    
    def test_get_timeout_custom(self):
        """测试获取自定义超时时间"""
        config = {'host': 'localhost', 'timeout': 30}
        checker = MockHealthChecker('test-service', config)
        
        assert checker.get_timeout() == 30
    
    @pytest.mark.asyncio
    async def test_check_health(self):
        """测试健康检查方法"""
        config = {'host': 'localhost'}
        checker = MockHealthChecker('test-service', config)
        
        result = await checker.check_health()
        
        assert isinstance(result, HealthCheckResult)
        assert result.service_name == 'test-service'
        assert result.service_type == 'mock'
        assert result.is_healthy is True
    
    def test_validate_config(self):
        """测试配置验证"""
        # 有效配置
        config = {'host': 'localhost'}
        checker = MockHealthChecker('test-service', config)
        assert checker.validate_config() is True
        
        # 无效配置
        config = {'port': 6379}
        checker = MockHealthChecker('test-service', config)
        assert checker.validate_config() is False