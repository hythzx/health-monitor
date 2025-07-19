"""测试配置验证器"""

import pytest
from health_monitor.utils.config_validator import ConfigValidator
from health_monitor.utils.exceptions import ConfigError


class TestConfigValidator:
    """测试ConfigValidator类"""
    
    def test_validate_service_config_valid(self):
        """测试有效的服务配置"""
        config = {
            'type': 'redis',
            'host': 'localhost',
            'port': 6379
        }
        
        # 不应该抛出异常
        ConfigValidator.validate_service_config('test-service', config)
    
    def test_validate_service_config_missing_type(self):
        """测试缺少type字段的服务配置"""
        config = {
            'host': 'localhost',
            'port': 6379
        }
        
        with pytest.raises(ConfigError, match="缺少必需的配置项: type"):
            ConfigValidator.validate_service_config('test-service', config)
    
    def test_validate_service_config_invalid_type(self):
        """测试无效的服务类型"""
        config = {
            'type': 'invalid_type',
            'host': 'localhost'
        }
        
        with pytest.raises(ConfigError, match="不受支持"):
            ConfigValidator.validate_service_config('test-service', config)
    
    def test_validate_service_config_not_dict(self):
        """测试非字典类型的服务配置"""
        config = "invalid config"
        
        with pytest.raises(ConfigError, match="必须是字典类型"):
            ConfigValidator.validate_service_config('test-service', config)
    
    def test_validate_alert_config_valid(self):
        """测试有效的告警配置"""
        config = {
            'name': 'dingtalk',
            'type': 'http',
            'url': 'https://example.com/webhook'
        }
        
        # 不应该抛出异常
        ConfigValidator.validate_alert_config(config)
    
    def test_validate_alert_config_missing_fields(self):
        """测试缺少必需字段的告警配置"""
        config = {
            'name': 'dingtalk',
            'type': 'http'
            # 缺少url字段
        }
        
        with pytest.raises(ConfigError, match="缺少必需的配置项: url"):
            ConfigValidator.validate_alert_config(config)
    
    def test_validate_global_config_valid(self):
        """测试有效的全局配置"""
        config = {
            'check_interval': 30,
            'log_level': 'INFO',
            'log_file': '/var/log/health-monitor.log'
        }
        
        # 不应该抛出异常
        ConfigValidator.validate_global_config(config)
    
    def test_validate_global_config_invalid_interval(self):
        """测试无效的检查间隔"""
        config = {
            'check_interval': -1
        }
        
        with pytest.raises(ConfigError, match="必须是正整数"):
            ConfigValidator.validate_global_config(config)
    
    def test_validate_global_config_invalid_log_level(self):
        """测试无效的日志级别"""
        config = {
            'log_level': 'INVALID'
        }
        
        with pytest.raises(ConfigError, match="必须是以下值之一"):
            ConfigValidator.validate_global_config(config)