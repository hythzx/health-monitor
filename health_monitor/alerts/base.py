"""告警器基类"""

from abc import ABC, abstractmethod
from typing import Dict, Any

from ..models.health_check import AlertMessage


class BaseAlerter(ABC):
    """告警器抽象基类"""

    def __init__(self, name: str, config: Dict[str, Any]):
        """
        初始化告警器
        
        Args:
            name: 告警器名称
            config: 告警器配置参数
        """
        self.name = name
        self.config = config
        self.alerter_type = self.__class__.__name__.replace('Alerter', '').lower()

    @abstractmethod
    async def send_alert(self, message: AlertMessage) -> bool:
        """
        发送告警消息
        
        Args:
            message: 告警消息对象
            
        Returns:
            bool: 发送是否成功
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
        return self.config.get('timeout', 30)
