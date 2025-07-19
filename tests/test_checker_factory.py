"""测试健康检查器工厂"""

import pytest
from health_monitor.checkers.factory import HealthCheckerFactory, register_checker
from health_monitor.checkers.base import BaseHealthChecker
from health_monitor.models.health_check import HealthCheckResult
from health_monitor.utils.exceptions import CheckerError


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


class InvalidChecker:
    """无效的检查器类（不继承BaseHealthChecker）"""
    pass


class TestHealthCheckerFactory:
    """测试HealthCheckerFactory类"""
    
    def setup_method(self):
        """测试前准备"""
        self.factory = HealthCheckerFactory()
    
    def test_register_checker(self):
        """测试注册健康检查器"""
        self.factory.register_checker('mock', MockHealthChecker)
        
        assert self.factory.is_type_supported('mock')
        assert 'mock' in self.factory.get_supported_types()
        assert self.factory.get_checker_class('mock') == MockHealthChecker
    
    def test_register_invalid_checker(self):
        """测试注册无效的检查器类"""
        with pytest.raises(CheckerError, match="必须继承自 BaseHealthChecker"):
            self.factory.register_checker('invalid', InvalidChecker)
    
    def test_register_duplicate_checker(self):
        """测试重复注册检查器"""
        self.factory.register_checker('mock', MockHealthChecker)
        
        with pytest.raises(CheckerError, match="已经注册了检查器"):
            self.factory.register_checker('mock', MockHealthChecker)
    
    def test_unregister_checker(self):
        """测试取消注册检查器"""
        self.factory.register_checker('mock', MockHealthChecker)
        assert self.factory.is_type_supported('mock')
        
        self.factory.unregister_checker('mock')
        assert not self.factory.is_type_supported('mock')
        
        # 取消注册不存在的类型不应该报错
        self.factory.unregister_checker('nonexistent')
    
    def test_create_checker_success(self):
        """测试成功创建检查器"""
        self.factory.register_checker('mock', MockHealthChecker)
        
        config = {
            'type': 'mock',
            'host': 'localhost',
            'port': 6379
        }
        
        checker = self.factory.create_checker('test-service', config)
        
        assert isinstance(checker, MockHealthChecker)
        assert checker.name == 'test-service'
        assert checker.config == config
    
    def test_create_checker_missing_type(self):
        """测试创建检查器时缺少type配置"""
        config = {
            'host': 'localhost',
            'port': 6379
        }
        
        with pytest.raises(CheckerError, match="缺少 'type' 配置"):
            self.factory.create_checker('test-service', config)
    
    def test_create_checker_unsupported_type(self):
        """测试创建不支持的服务类型检查器"""
        config = {
            'type': 'unsupported',
            'host': 'localhost'
        }
        
        with pytest.raises(CheckerError, match="不支持的服务类型"):
            self.factory.create_checker('test-service', config)
    
    def test_create_checker_invalid_config(self):
        """测试创建检查器时配置验证失败"""
        self.factory.register_checker('mock', MockHealthChecker)
        
        config = {
            'type': 'mock',
            'port': 6379
            # 缺少host配置，会导致validate_config返回False
        }
        
        with pytest.raises(CheckerError, match="配置验证失败"):
            self.factory.create_checker('test-service', config)
    
    def test_get_supported_types(self):
        """测试获取支持的服务类型"""
        assert self.factory.get_supported_types() == []
        
        self.factory.register_checker('mock1', MockHealthChecker)
        self.factory.register_checker('mock2', MockHealthChecker)
        
        supported_types = self.factory.get_supported_types()
        assert len(supported_types) == 2
        assert 'mock1' in supported_types
        assert 'mock2' in supported_types
    
    def test_is_type_supported(self):
        """测试检查服务类型是否支持"""
        assert not self.factory.is_type_supported('mock')
        
        self.factory.register_checker('mock', MockHealthChecker)
        assert self.factory.is_type_supported('mock')
        assert not self.factory.is_type_supported('other')
    
    def test_get_checker_class(self):
        """测试获取检查器类"""
        self.factory.register_checker('mock', MockHealthChecker)
        
        checker_class = self.factory.get_checker_class('mock')
        assert checker_class == MockHealthChecker
        
        with pytest.raises(CheckerError, match="不支持的服务类型"):
            self.factory.get_checker_class('unsupported')


class TestRegisterDecorator:
    """测试注册装饰器"""
    
    def test_register_decorator(self):
        """测试使用装饰器注册检查器"""
        # 创建新的工厂实例避免影响其他测试
        from health_monitor.checkers.factory import health_checker_factory
        
        @register_checker('decorated')
        class DecoratedChecker(BaseHealthChecker):
            async def check_health(self) -> HealthCheckResult:
                return HealthCheckResult(
                    service_name=self.name,
                    service_type=self.service_type,
                    is_healthy=True,
                    response_time=0.1
                )
            
            def validate_config(self) -> bool:
                return True
        
        assert health_checker_factory.is_type_supported('decorated')
        assert health_checker_factory.get_checker_class('decorated') == DecoratedChecker
        
        # 清理
        health_checker_factory.unregister_checker('decorated')