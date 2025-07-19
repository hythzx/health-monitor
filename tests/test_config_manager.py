"""测试配置管理器"""

import os
import tempfile
import pytest
from health_monitor.services.config_manager import ConfigManager
from health_monitor.utils.exceptions import ConfigError


class TestConfigManager:
    """测试ConfigManager类"""
    
    def test_load_valid_config(self):
        """测试加载有效配置"""
        config_content = """
global:
  check_interval: 30
  log_level: INFO

services:
  test-redis:
    type: redis
    host: localhost
    port: 6379

alerts:
  - name: test-alert
    type: http
    url: https://example.com/webhook
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name
        
        try:
            manager = ConfigManager(config_path)
            config = manager.load_config()
            
            assert 'global' in config
            assert 'services' in config
            assert 'alerts' in config
            assert config['global']['check_interval'] == 30
            assert config['services']['test-redis']['type'] == 'redis'
            
        finally:
            os.unlink(config_path)
    
    def test_load_nonexistent_file(self):
        """测试加载不存在的配置文件"""
        manager = ConfigManager('/nonexistent/config.yaml')
        
        with pytest.raises(ConfigError, match="配置文件不存在"):
            manager.load_config()
    
    def test_load_invalid_yaml(self):
        """测试加载无效的YAML文件"""
        config_content = """
global:
  check_interval: 30
  invalid_yaml: [
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name
        
        try:
            manager = ConfigManager(config_path)
            
            with pytest.raises(ConfigError, match="YAML格式错误"):
                manager.load_config()
                
        finally:
            os.unlink(config_path)
    
    def test_load_empty_config(self):
        """测试加载空配置文件"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("")
            config_path = f.name
        
        try:
            manager = ConfigManager(config_path)
            
            with pytest.raises(ConfigError, match="配置文件为空"):
                manager.load_config()
                
        finally:
            os.unlink(config_path)
    
    def test_validate_invalid_service_config(self):
        """测试验证无效的服务配置"""
        config_content = """
services:
  test-service:
    host: localhost
    # missing type field
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write(config_content)
            config_path = f.name
        
        try:
            manager = ConfigManager(config_path)
            
            with pytest.raises(ConfigError, match="缺少必需的配置项: type"):
                manager.load_config()
                
        finally:
            os.unlink(config_path)
    
    def test_get_global_config(self):
        """测试获取全局配置"""
        config_content = """
global:
  check_interval: 60
  log_level: DEBUG
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name
        
        try:
            manager = ConfigManager(config_path)
            manager.load_config()
            
            global_config = manager.get_global_config()
            assert global_config['check_interval'] == 60
            assert global_config['log_level'] == 'DEBUG'
            
        finally:
            os.unlink(config_path)
    
    def test_get_services_config(self):
        """测试获取服务配置"""
        config_content = """
services:
  redis-1:
    type: redis
    host: localhost
  mysql-1:
    type: mysql
    host: localhost
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name
        
        try:
            manager = ConfigManager(config_path)
            manager.load_config()
            
            services_config = manager.get_services_config()
            assert 'redis-1' in services_config
            assert 'mysql-1' in services_config
            assert services_config['redis-1']['type'] == 'redis'
            
        finally:
            os.unlink(config_path)
    
    def test_get_service_config(self):
        """测试获取指定服务配置"""
        config_content = """
services:
  test-service:
    type: redis
    host: localhost
    port: 6379
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name
        
        try:
            manager = ConfigManager(config_path)
            manager.load_config()
            
            service_config = manager.get_service_config('test-service')
            assert service_config is not None
            assert service_config['type'] == 'redis'
            assert service_config['host'] == 'localhost'
            
            # 测试不存在的服务
            nonexistent_config = manager.get_service_config('nonexistent')
            assert nonexistent_config is None
            
        finally:
            os.unlink(config_path)
    
    def test_get_alerts_config(self):
        """测试获取告警配置"""
        config_content = """
alerts:
  - name: alert-1
    type: http
    url: https://example.com/1
  - name: alert-2
    type: http
    url: https://example.com/2
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name
        
        try:
            manager = ConfigManager(config_path)
            manager.load_config()
            
            alerts_config = manager.get_alerts_config()
            assert len(alerts_config) == 2
            assert alerts_config[0]['name'] == 'alert-1'
            assert alerts_config[1]['name'] == 'alert-2'
            
        finally:
            os.unlink(config_path)
    
    def test_is_config_changed(self):
        """测试检查配置文件是否已修改"""
        config_content = """
global:
  check_interval: 30
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name
        
        try:
            manager = ConfigManager(config_path)
            
            # 初始状态应该检测到变化
            assert manager.is_config_changed() is True
            
            # 加载配置后应该没有变化
            manager.load_config()
            assert manager.is_config_changed() is False
            
            # 修改文件后应该检测到变化
            import time
            time.sleep(0.1)  # 确保修改时间不同
            with open(config_path, 'a') as f:
                f.write("\n# comment")
            
            assert manager.is_config_changed() is True
            
        finally:
            os.unlink(config_path)
    
    def test_reload_config(self):
        """测试重新加载配置"""
        config_content = """
global:
  check_interval: 30
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name
        
        try:
            manager = ConfigManager(config_path)
            config = manager.reload_config()
            
            assert config['global']['check_interval'] == 30
            
        finally:
            os.unlink(config_path)