"""健康检查器工厂"""

from typing import Dict, Type, Any
from .base import BaseHealthChecker
from ..utils.exceptions import CheckerError


class HealthCheckerFactory:
    """健康检查器工厂类，负责创建和管理不同类型的健康检查器"""
    
    def __init__(self):
        """初始化工厂"""
        self._checkers: Dict[str, Type[BaseHealthChecker]] = {}
    
    def register_checker(self, service_type: str, checker_class: Type[BaseHealthChecker]):
        """
        注册健康检查器类
        
        Args:
            service_type: 服务类型名称
            checker_class: 健康检查器类
            
        Raises:
            CheckerError: 注册失败
        """
        if not issubclass(checker_class, BaseHealthChecker):
            raise CheckerError(f"检查器类 {checker_class.__name__} 必须继承自 BaseHealthChecker")
        
        if service_type in self._checkers:
            raise CheckerError(f"服务类型 '{service_type}' 已经注册了检查器")
        
        self._checkers[service_type] = checker_class
    
    def unregister_checker(self, service_type: str):
        """
        取消注册健康检查器类
        
        Args:
            service_type: 服务类型名称
        """
        if service_type in self._checkers:
            del self._checkers[service_type]
    
    def create_checker(self, service_name: str, service_config: Dict[str, Any]) -> BaseHealthChecker:
        """
        创建健康检查器实例
        
        Args:
            service_name: 服务名称
            service_config: 服务配置
            
        Returns:
            BaseHealthChecker: 健康检查器实例
            
        Raises:
            CheckerError: 创建失败
        """
        service_type = service_config.get('type')
        if not service_type:
            raise CheckerError(f"服务 '{service_name}' 缺少 'type' 配置")
        
        if service_type not in self._checkers:
            raise CheckerError(f"不支持的服务类型: '{service_type}'")
        
        checker_class = self._checkers[service_type]
        
        try:
            checker = checker_class(service_name, service_config)
            
            # 验证配置
            if not checker.validate_config():
                raise CheckerError(f"服务 '{service_name}' 的配置验证失败")
            
            return checker
            
        except Exception as e:
            raise CheckerError(f"创建服务 '{service_name}' 的健康检查器失败: {e}")
    
    def get_supported_types(self) -> list:
        """
        获取支持的服务类型列表
        
        Returns:
            list: 支持的服务类型列表
        """
        return list(self._checkers.keys())
    
    def is_type_supported(self, service_type: str) -> bool:
        """
        检查是否支持指定的服务类型
        
        Args:
            service_type: 服务类型
            
        Returns:
            bool: 是否支持
        """
        return service_type in self._checkers
    
    def get_checker_class(self, service_type: str) -> Type[BaseHealthChecker]:
        """
        获取指定服务类型的检查器类
        
        Args:
            service_type: 服务类型
            
        Returns:
            Type[BaseHealthChecker]: 检查器类
            
        Raises:
            CheckerError: 服务类型不支持
        """
        if service_type not in self._checkers:
            raise CheckerError(f"不支持的服务类型: '{service_type}'")
        
        return self._checkers[service_type]


# 全局工厂实例
health_checker_factory = HealthCheckerFactory()


def register_checker(service_type: str):
    """
    装饰器：注册健康检查器类
    
    Args:
        service_type: 服务类型名称
        
    Returns:
        装饰器函数
    """
    def decorator(checker_class: Type[BaseHealthChecker]):
        health_checker_factory.register_checker(service_type, checker_class)
        return checker_class
    
    return decorator