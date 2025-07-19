"""测试配置监控器"""

import os
import time
import tempfile
import pytest
import asyncio
from unittest.mock import Mock, patch
from health_monitor.services.config_manager import ConfigManager
from health_monitor.services.config_watcher import ConfigWatcher


class TestConfigWatcher:
    """测试ConfigWatcher类"""
    
    def setup_method(self):
        """测试前准备"""
        self.config_content = """
global:
  check_interval: 30
  log_level: INFO

services:
  test-service:
    type: redis
    host: localhost
    port: 6379
"""
        
        # 创建临时配置文件
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
        self.temp_file.write(self.config_content)
        self.temp_file.close()
        
        # 创建配置管理器和监控器
        self.config_manager = ConfigManager(self.temp_file.name)
        self.config_manager.load_config()
        self.config_watcher = ConfigWatcher(self.config_manager)
    
    def teardown_method(self):
        """测试后清理"""
        if hasattr(self, 'config_watcher'):
            self.config_watcher.stop_watching()
        
        if hasattr(self, 'temp_file'):
            try:
                os.unlink(self.temp_file.name)
            except FileNotFoundError:
                pass
    
    def test_add_remove_callback(self):
        """测试添加和移除回调函数"""
        callback1 = Mock()
        callback2 = Mock()
        
        # 添加回调
        self.config_watcher.add_change_callback(callback1)
        self.config_watcher.add_change_callback(callback2)
        
        assert len(self.config_watcher.change_callbacks) == 2
        assert callback1 in self.config_watcher.change_callbacks
        assert callback2 in self.config_watcher.change_callbacks
        
        # 移除回调
        self.config_watcher.remove_change_callback(callback1)
        assert len(self.config_watcher.change_callbacks) == 1
        assert callback1 not in self.config_watcher.change_callbacks
        assert callback2 in self.config_watcher.change_callbacks
    
    def test_start_stop_watching(self):
        """测试启动和停止监控"""
        assert not self.config_watcher.is_running()
        
        # 启动监控
        self.config_watcher.start_watching()
        assert self.config_watcher.is_running()
        
        # 停止监控
        self.config_watcher.stop_watching()
        assert not self.config_watcher.is_running()
    
    def test_context_manager(self):
        """测试上下文管理器"""
        assert not self.config_watcher.is_running()
        
        with self.config_watcher:
            assert self.config_watcher.is_running()
        
        assert not self.config_watcher.is_running()
    
    def test_config_change_callback(self):
        """测试配置变更回调"""
        callback = Mock()
        self.config_watcher.add_change_callback(callback)
        
        # 模拟配置变更
        old_config = self.config_manager.config.copy()
        
        # 修改配置文件 - 添加新的全局配置
        new_content = """
global:
  check_interval: 60
  log_level: DEBUG
  new_setting: value

services:
  test-service:
    type: redis
    host: localhost
    port: 6379
"""
        with open(self.temp_file.name, 'w') as f:
            f.write(new_content)
        
        # 手动触发配置变更处理
        self.config_watcher._on_config_changed()
        
        # 验证回调被调用
        callback.assert_called_once()
        args = callback.call_args[0]
        assert len(args) == 2  # old_config, new_config
    
    def test_config_change_with_error(self):
        """测试配置变更时的错误处理"""
        # 添加一个会抛出异常的回调
        error_callback = Mock(side_effect=Exception("Test error"))
        normal_callback = Mock()
        
        self.config_watcher.add_change_callback(error_callback)
        self.config_watcher.add_change_callback(normal_callback)
        
        # 修改配置文件 - 添加新的全局配置
        new_content = """
global:
  check_interval: 60
  log_level: DEBUG

services:
  test-service:
    type: redis
    host: localhost
    port: 6379
"""
        with open(self.temp_file.name, 'w') as f:
            f.write(new_content)
        
        # 触发配置变更处理（不应该抛出异常）
        self.config_watcher._on_config_changed()
        
        # 验证两个回调都被调用了
        error_callback.assert_called_once()
        normal_callback.assert_called_once()
    
    def test_invalid_config_reload(self):
        """测试重新加载无效配置"""
        callback = Mock()
        self.config_watcher.add_change_callback(callback)
        
        # 写入无效的YAML内容
        invalid_content = "invalid: yaml: content: ["
        with open(self.temp_file.name, 'w') as f:
            f.write(invalid_content)
        
        # 触发配置变更处理（不应该抛出异常）
        self.config_watcher._on_config_changed()
        
        # 回调不应该被调用，因为配置加载失败
        callback.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_async_config_monitoring(self):
        """测试异步配置监控"""
        callback = Mock()
        self.config_watcher.add_change_callback(callback)
        
        # 启动异步监控任务
        monitor_task = asyncio.create_task(
            self.config_watcher.watch_config_changes_async(check_interval=0.1)
        )
        
        try:
            # 等待一小段时间让监控开始
            await asyncio.sleep(0.05)
            
            # 修改配置文件
            new_content = """
global:
  check_interval: 60
  log_level: DEBUG
  async_test: true

services:
  test-service:
    type: redis
    host: localhost
    port: 6379
"""
            with open(self.temp_file.name, 'w') as f:
                f.write(new_content)
            
            # 等待监控检测到变更
            await asyncio.sleep(0.2)
            
            # 验证回调被调用
            callback.assert_called()
            
        finally:
            # 取消监控任务
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
    
    def test_double_start_warning(self):
        """测试重复启动监控的警告"""
        self.config_watcher.start_watching()
        
        # 再次启动应该产生警告但不报错
        self.config_watcher.start_watching()
        
        assert self.config_watcher.is_running()
    
    def test_stop_not_running(self):
        """测试停止未运行的监控器"""
        assert not self.config_watcher.is_running()
        
        # 停止未运行的监控器不应该报错
        self.config_watcher.stop_watching()
        
        assert not self.config_watcher.is_running()