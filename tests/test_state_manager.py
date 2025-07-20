"""状态管理器测试模块"""

import pytest
import tempfile
import os
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from health_monitor.services.state_manager import StateManager
from health_monitor.models.health_check import HealthCheckResult, StateChange


class TestStateManager:
    """状态管理器测试类"""
    
    def setup_method(self):
        """测试前准备"""
        self.state_manager = StateManager()
    
    def test_init_without_persistence(self):
        """测试不带持久化的初始化"""
        manager = StateManager()
        assert manager.current_states == {}
        assert manager.state_history == []
        assert manager.state_changes == []
        assert manager.persistence_file is None
    
    def test_init_with_persistence(self):
        """测试带持久化的初始化"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            persistence_file = f.name
        
        try:
            manager = StateManager(persistence_file=persistence_file)
            assert manager.persistence_file == persistence_file
        finally:
            os.unlink(persistence_file)
    
    def test_update_state_first_time(self):
        """测试首次更新状态"""
        result = HealthCheckResult(
            service_name="test-service",
            service_type="redis",
            is_healthy=True,
            response_time=0.1
        )
        
        state_change = self.state_manager.update_state(result)
        
        # 首次检查不应该产生状态变化事件
        assert state_change is None
        assert self.state_manager.current_states["test-service"] is True
        assert len(self.state_manager.state_history) == 1
        assert self.state_manager.state_history[0] == result
    
    def test_update_state_no_change(self):
        """测试状态无变化的更新"""
        # 首次检查
        result1 = HealthCheckResult(
            service_name="test-service",
            service_type="redis",
            is_healthy=True,
            response_time=0.1
        )
        self.state_manager.update_state(result1)
        
        # 第二次检查，状态相同
        result2 = HealthCheckResult(
            service_name="test-service",
            service_type="redis",
            is_healthy=True,
            response_time=0.2
        )
        
        state_change = self.state_manager.update_state(result2)
        
        assert state_change is None
        assert self.state_manager.current_states["test-service"] is True
        assert len(self.state_manager.state_history) == 2
        assert len(self.state_manager.state_changes) == 0
    
    def test_update_state_with_change(self):
        """测试状态变化的更新"""
        # 首次检查 - 健康
        result1 = HealthCheckResult(
            service_name="test-service",
            service_type="redis",
            is_healthy=True,
            response_time=0.1
        )
        self.state_manager.update_state(result1)
        
        # 第二次检查 - 不健康
        result2 = HealthCheckResult(
            service_name="test-service",
            service_type="redis",
            is_healthy=False,
            response_time=5.0,
            error_message="连接超时"
        )
        
        state_change = self.state_manager.update_state(result2)
        
        assert state_change is not None
        assert state_change.service_name == "test-service"
        assert state_change.service_type == "redis"
        assert state_change.old_state is True
        assert state_change.new_state is False
        assert state_change.error_message == "连接超时"
        assert state_change.response_time == 5.0
        
        assert self.state_manager.current_states["test-service"] is False
        assert len(self.state_manager.state_changes) == 1
    
    def test_get_current_state(self):
        """测试获取当前状态"""
        # 未知服务
        assert self.state_manager.get_current_state("unknown") is None
        
        # 添加服务状态
        result = HealthCheckResult(
            service_name="test-service",
            service_type="redis",
            is_healthy=True,
            response_time=0.1
        )
        self.state_manager.update_state(result)
        
        assert self.state_manager.get_current_state("test-service") is True
    
    def test_get_all_states(self):
        """测试获取所有状态"""
        # 添加多个服务
        services = [
            ("redis-service", True),
            ("mysql-service", False),
            ("mongo-service", True)
        ]
        
        for service_name, is_healthy in services:
            result = HealthCheckResult(
                service_name=service_name,
                service_type="test",
                is_healthy=is_healthy,
                response_time=0.1
            )
            self.state_manager.update_state(result)
        
        all_states = self.state_manager.get_all_states()
        assert len(all_states) == 3
        assert all_states["redis-service"] is True
        assert all_states["mysql-service"] is False
        assert all_states["mongo-service"] is True
    
    def test_get_state_changes(self):
        """测试获取状态变化"""
        # 创建状态变化
        result1 = HealthCheckResult("service1", "redis", True, 0.1)
        result2 = HealthCheckResult("service1", "redis", False, 5.0, "错误")
        result3 = HealthCheckResult("service2", "mysql", True, 0.2)
        result4 = HealthCheckResult("service2", "mysql", False, 3.0, "超时")
        
        self.state_manager.update_state(result1)
        self.state_manager.update_state(result2)
        self.state_manager.update_state(result3)
        self.state_manager.update_state(result4)
        
        # 获取所有状态变化
        changes = self.state_manager.get_state_changes()
        assert len(changes) == 2
        
        # 测试时间过滤
        now = datetime.now()
        future_time = now + timedelta(hours=1)
        changes_since_future = self.state_manager.get_state_changes(since=future_time)
        assert len(changes_since_future) == 0
    
    def test_get_history(self):
        """测试获取历史记录"""
        # 添加历史记录
        results = [
            HealthCheckResult("service1", "redis", True, 0.1),
            HealthCheckResult("service1", "redis", False, 5.0),
            HealthCheckResult("service2", "mysql", True, 0.2),
        ]
        
        for result in results:
            self.state_manager.update_state(result)
        
        # 获取所有历史
        all_history = self.state_manager.get_history()
        assert len(all_history) == 3
        
        # 按服务过滤
        service1_history = self.state_manager.get_history(service_name="service1")
        assert len(service1_history) == 2
        assert all(h.service_name == "service1" for h in service1_history)
        
        # 限制数量
        limited_history = self.state_manager.get_history(limit=2)
        assert len(limited_history) == 2
    
    def test_is_state_changed(self):
        """测试状态变化检查"""
        # 初始状态
        assert not self.state_manager.is_state_changed("test-service")
        
        # 添加首次检查（无变化）
        result1 = HealthCheckResult("test-service", "redis", True, 0.1)
        self.state_manager.update_state(result1)
        assert not self.state_manager.is_state_changed("test-service")
        
        # 添加状态变化
        result2 = HealthCheckResult("test-service", "redis", False, 5.0)
        self.state_manager.update_state(result2)
        assert self.state_manager.is_state_changed("test-service")
    
    def test_clear_state_changes(self):
        """测试清空状态变化"""
        # 创建状态变化
        result1 = HealthCheckResult("service1", "redis", True, 0.1)
        result2 = HealthCheckResult("service1", "redis", False, 5.0)
        
        self.state_manager.update_state(result1)
        self.state_manager.update_state(result2)
        
        assert len(self.state_manager.state_changes) == 1
        
        self.state_manager.clear_state_changes()
        assert len(self.state_manager.state_changes) == 0
    
    def test_cleanup_history(self):
        """测试清理历史记录"""
        # 创建不同时间的记录
        old_time = datetime.now() - timedelta(days=10)
        recent_time = datetime.now() - timedelta(days=1)
        
        with patch('health_monitor.services.state_manager.datetime') as mock_datetime:
            # 添加旧记录
            mock_datetime.now.return_value = old_time
            old_result = HealthCheckResult("service1", "redis", True, 0.1)
            old_result.timestamp = old_time
            self.state_manager.state_history.append(old_result)
            
            # 添加新记录
            mock_datetime.now.return_value = recent_time
            recent_result = HealthCheckResult("service1", "redis", False, 5.0)
            recent_result.timestamp = recent_time
            self.state_manager.state_history.append(recent_result)
            
            # 重置mock以使cleanup_history正常工作
            mock_datetime.now.return_value = datetime.now()
            
            assert len(self.state_manager.state_history) == 2
            
            # 清理7天前的记录
            self.state_manager.cleanup_history(keep_days=7)
            
            # 应该只保留最近的记录
            assert len(self.state_manager.state_history) == 1
            assert self.state_manager.state_history[0].timestamp == recent_time
    
    def test_persistence_save_and_load(self):
        """测试状态持久化保存和加载"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            persistence_file = f.name
        
        try:
            # 创建带持久化的管理器
            manager = StateManager(persistence_file=persistence_file)
            
            # 添加状态
            result1 = HealthCheckResult("service1", "redis", True, 0.1)
            result2 = HealthCheckResult("service1", "redis", False, 5.0, "错误")
            
            manager.update_state(result1)
            manager.update_state(result2)
            
            # 验证文件已创建
            assert os.path.exists(persistence_file)
            
            # 创建新的管理器并加载状态
            new_manager = StateManager(persistence_file=persistence_file)
            
            # 验证状态已加载
            assert new_manager.current_states["service1"] is False
            assert len(new_manager.state_changes) == 1
            assert new_manager.state_changes[0].service_name == "service1"
            
        finally:
            if os.path.exists(persistence_file):
                os.unlink(persistence_file)
    
    def test_get_service_stats(self):
        """测试获取服务统计信息"""
        # 添加多次检查记录
        results = [
            HealthCheckResult("test-service", "redis", True, 0.1),
            HealthCheckResult("test-service", "redis", True, 0.2),
            HealthCheckResult("test-service", "redis", False, 5.0, "错误"),
            HealthCheckResult("test-service", "redis", True, 0.15),
        ]
        
        for result in results:
            self.state_manager.update_state(result)
        
        stats = self.state_manager.get_service_stats("test-service")
        
        assert stats["service_name"] == "test-service"
        assert stats["current_state"] is True
        assert stats["total_checks"] == 4
        assert stats["healthy_checks"] == 3
        assert stats["unhealthy_checks"] == 1
        assert stats["health_rate"] == 0.75
        assert stats["avg_response_time"] == (0.1 + 0.2 + 5.0 + 0.15) / 4
        assert stats["state_changes_count"] == 2  # True->False, False->True
        # 比较latest_check的各个属性而不是对象本身
        latest_check = stats["latest_check"]
        expected_check = results[-1]
        assert latest_check.service_name == expected_check.service_name
        assert latest_check.service_type == expected_check.service_type
        assert latest_check.is_healthy == expected_check.is_healthy
        assert latest_check.response_time == expected_check.response_time
        assert latest_check.error_message == expected_check.error_message
    
    def test_get_service_stats_empty(self):
        """测试获取不存在服务的统计信息"""
        stats = self.state_manager.get_service_stats("nonexistent")
        assert stats == {}


if __name__ == "__main__":
    pytest.main([__file__])