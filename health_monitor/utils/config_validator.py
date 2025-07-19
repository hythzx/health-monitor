"""配置验证工具"""

from typing import Dict, Any

from .exceptions import ConfigError


class ConfigValidator:
    """配置验证器"""

    @staticmethod
    def validate_service_config(service_name: str, config: Dict[str, Any]) -> None:
        """
        验证服务配置
        
        Args:
            service_name: 服务名称
            config: 服务配置
            
        Raises:
            ConfigError: 配置验证失败
        """
        if not isinstance(config, dict):
            raise ConfigError(f"服务 '{service_name}' 的配置必须是字典类型")

        # 检查必需的字段
        required_fields = ['type']
        for field in required_fields:
            if field not in config:
                raise ConfigError(f"服务 '{service_name}' 缺少必需的配置项: {field}")

        # 验证服务类型
        supported_types = ['redis', 'mysql', 'mongodb', 'emqx', 'restful']
        service_type = config.get('type')
        if service_type not in supported_types:
            raise ConfigError(
                f"服务 '{service_name}' 的类型 '{service_type}' 不受支持。支持的类型: {supported_types}")

    @staticmethod
    def validate_alert_config(alert_config: Dict[str, Any]) -> None:
        """
        验证告警配置
        
        Args:
            alert_config: 告警配置
            
        Raises:
            ConfigError: 配置验证失败
        """
        if not isinstance(alert_config, dict):
            raise ConfigError("告警配置必须是字典类型")

        required_fields = ['name', 'type', 'url']
        for field in required_fields:
            if field not in alert_config:
                raise ConfigError(f"告警配置缺少必需的配置项: {field}")

    @staticmethod
    def validate_global_config(global_config: Dict[str, Any]) -> None:
        """
        验证全局配置
        
        Args:
            global_config: 全局配置
            
        Raises:
            ConfigError: 配置验证失败
        """
        if not isinstance(global_config, dict):
            raise ConfigError("全局配置必须是字典类型")

        # 验证检查间隔
        check_interval = global_config.get('check_interval')
        if check_interval is not None:
            if not isinstance(check_interval, int) or check_interval <= 0:
                raise ConfigError("check_interval 必须是正整数")

        # 验证日志级别
        log_level = global_config.get('log_level')
        if log_level is not None:
            valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
            if log_level not in valid_levels:
                raise ConfigError(f"log_level 必须是以下值之一: {valid_levels}")
