"""健康检查器基类"""

from abc import ABC, abstractmethod
from typing import Dict, Any
from ..models.health_check import HealthCheckResult
from ..utils.log_manager import get_logger


class BaseHealthChecker(ABC):
    """健康检查器抽象基类"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """
        初始化健康检查器
        
        Args:
            name: 服务名称
            config: 服务配置参数
        """
        self.name = name
        self.config = config
        self.service_type = self.__class__.__name__.replace('HealthChecker', '').lower()
        self.logger = get_logger(f'checker.{self.service_type}.{self.name}')
    
    @abstractmethod
    async def check_health(self) -> HealthCheckResult:
        """
        执行健康检查并返回结果
        
        Returns:
            HealthCheckResult: 健康检查结果
        """
        pass
    
    @abstractmethod
    def validate_config(self) -> bool:
        """
        验证配置参数是否有效
        
        Returns:
            bool: 配置是否有效
        """
        pass
    
    def get_timeout(self) -> int:
        """
        获取超时时间配置
        
        Returns:
            int: 超时时间（秒）
        """
        return self.config.get('timeout', 10)