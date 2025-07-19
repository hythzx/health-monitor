"""配置管理器"""

import os
import yaml
from typing import Dict, Any, Optional
from ..utils.exceptions import ConfigError
from ..utils.config_validator import ConfigValidator
from ..utils.log_manager import get_logger


class ConfigManager:
    """配置管理器，负责YAML配置文件的加载、解析和验证"""
    
    def __init__(self, config_path: str):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.last_modified: Optional[float] = None
        self.logger = get_logger('config_manager')
    
    def load_config(self) -> Dict[str, Any]:
        """
        加载YAML配置文件
        
        Returns:
            Dict[str, Any]: 配置字典
            
        Raises:
            ConfigError: 配置加载或验证失败
        """
        self.logger.info(f"开始加载配置文件: {self.config_path}")
        
        try:
            if not os.path.exists(self.config_path):
                self.logger.error(f"配置文件不存在: {self.config_path}")
                raise ConfigError(f"配置文件不存在: {self.config_path}")
            
            self.logger.debug(f"读取配置文件: {self.config_path}")
            with open(self.config_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)
            
            if config is None:
                self.logger.error("配置文件为空")
                raise ConfigError("配置文件为空")
            
            self.logger.debug("开始验证配置文件内容")
            # 验证配置
            self._validate_config(config)
            
            # 统计配置信息
            services_count = len(config.get('services', {}))
            alerts_count = len(config.get('alerts', []))
            self.logger.info(f"配置验证成功，包含 {services_count} 个服务和 {alerts_count} 个告警配置")
            
            # 更新配置和修改时间
            old_config = self.config.copy() if self.config else {}
            self.config = config
            self.last_modified = os.path.getmtime(self.config_path)
            
            # 记录配置变更
            if old_config:
                self._log_config_changes(old_config, config)
            else:
                self.logger.info("首次加载配置文件")
            
            return self.config
            
        except yaml.YAMLError as e:
            self.logger.error(f"YAML格式错误: {e}")
            raise ConfigError(f"YAML格式错误: {e}")
        except FileNotFoundError:
            self.logger.error(f"配置文件不存在: {self.config_path}")
            raise ConfigError(f"配置文件不存在: {self.config_path}")
        except PermissionError:
            self.logger.error(f"没有权限读取配置文件: {self.config_path}")
            raise ConfigError(f"没有权限读取配置文件: {self.config_path}")
        except Exception as e:
            self.logger.error(f"加载配置文件失败: {e}", exc_info=True)
            raise ConfigError(f"加载配置文件失败: {e}")
    
    def _validate_config(self, config: Dict[str, Any]) -> None:
        """
        验证配置文件内容
        
        Args:
            config: 配置字典
            
        Raises:
            ConfigError: 配置验证失败
        """
        if not isinstance(config, dict):
            raise ConfigError("配置文件根节点必须是字典类型")
        
        # 验证全局配置
        if 'global' in config:
            ConfigValidator.validate_global_config(config['global'])
        
        # 验证服务配置
        if 'services' in config:
            if not isinstance(config['services'], dict):
                raise ConfigError("services配置必须是字典类型")
            
            for service_name, service_config in config['services'].items():
                ConfigValidator.validate_service_config(service_name, service_config)
        
        # 验证告警配置
        if 'alerts' in config:
            if not isinstance(config['alerts'], list):
                raise ConfigError("alerts配置必须是列表类型")
            
            for alert_config in config['alerts']:
                ConfigValidator.validate_alert_config(alert_config)
    
    def get_global_config(self) -> Dict[str, Any]:
        """
        获取全局配置
        
        Returns:
            Dict[str, Any]: 全局配置字典
        """
        return self.config.get('global', {})
    
    def get_services_config(self) -> Dict[str, Any]:
        """
        获取服务配置
        
        Returns:
            Dict[str, Any]: 服务配置字典
        """
        return self.config.get('services', {})
    
    def get_alerts_config(self) -> list:
        """
        获取告警配置
        
        Returns:
            list: 告警配置列表
        """
        return self.config.get('alerts', [])
    
    def get_service_config(self, service_name: str) -> Optional[Dict[str, Any]]:
        """
        获取指定服务的配置
        
        Args:
            service_name: 服务名称
            
        Returns:
            Optional[Dict[str, Any]]: 服务配置，如果不存在返回None
        """
        services = self.get_services_config()
        return services.get(service_name)
    
    def is_config_changed(self) -> bool:
        """
        检查配置文件是否已修改
        
        Returns:
            bool: 配置文件是否已修改
        """
        try:
            if not os.path.exists(self.config_path):
                return False
            
            current_modified = os.path.getmtime(self.config_path)
            return self.last_modified is None or current_modified > self.last_modified
            
        except OSError:
            return False
    
    def reload_config(self) -> Dict[str, Any]:
        """
        重新加载配置文件
        
        Returns:
            Dict[str, Any]: 新的配置字典
            
        Raises:
            ConfigError: 配置重新加载失败
        """
        self.logger.info("重新加载配置文件")
        return self.load_config()
    
    def _log_config_changes(self, old_config: Dict[str, Any], new_config: Dict[str, Any]) -> None:
        """
        记录配置变更
        
        Args:
            old_config: 旧配置
            new_config: 新配置
        """
        try:
            # 比较服务配置变更
            old_services = old_config.get('services', {})
            new_services = new_config.get('services', {})
            
            # 新增的服务
            added_services = set(new_services.keys()) - set(old_services.keys())
            if added_services:
                self.logger.info(f"新增服务: {', '.join(added_services)}")
            
            # 删除的服务
            removed_services = set(old_services.keys()) - set(new_services.keys())
            if removed_services:
                self.logger.info(f"删除服务: {', '.join(removed_services)}")
            
            # 修改的服务
            for service_name in set(old_services.keys()) & set(new_services.keys()):
                if old_services[service_name] != new_services[service_name]:
                    self.logger.info(f"服务配置已修改: {service_name}")
                    self.logger.debug(f"服务 {service_name} 旧配置: {old_services[service_name]}")
                    self.logger.debug(f"服务 {service_name} 新配置: {new_services[service_name]}")
            
            # 比较告警配置变更
            old_alerts = old_config.get('alerts', [])
            new_alerts = new_config.get('alerts', [])
            
            if len(old_alerts) != len(new_alerts):
                self.logger.info(f"告警配置数量变更: {len(old_alerts)} -> {len(new_alerts)}")
            elif old_alerts != new_alerts:
                self.logger.info("告警配置已修改")
                self.logger.debug(f"旧告警配置: {old_alerts}")
                self.logger.debug(f"新告警配置: {new_alerts}")
            
            # 比较全局配置变更
            old_global = old_config.get('global', {})
            new_global = new_config.get('global', {})
            
            if old_global != new_global:
                self.logger.info("全局配置已修改")
                self.logger.debug(f"旧全局配置: {old_global}")
                self.logger.debug(f"新全局配置: {new_global}")
                
        except Exception as e:
            self.logger.warning(f"记录配置变更时出错: {e}")