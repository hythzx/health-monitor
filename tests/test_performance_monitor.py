"""性能监控器测试"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

from health_monitor.utils.performance_monitor import (
    PerformanceMonitor, 
    PerformanceMetrics,
    ConnectionPoolManager
)


class TestPerformanceMetrics:
    """性能指标测试"""
    
    def test_performance_metrics_creation(self):
        """测试性能指标创建"""
        timestamp = datetime.now()
        metrics = PerformanceMetrics(
            timestamp=timestamp,
            cpu_percent=50.5,
            memory_percent=60.2,
            memory_used_mb=1024.5,
            memory_available_mb=2048.0,
            active_threads=10,
            active_tasks=5
        )
        
        assert metrics.timestamp == timestamp
        assert metrics.cpu_percent == 50.5
        assert metrics.memory_percent == 60.2
        assert metrics.memory_used_mb == 1024.5
        assert metrics.memory_available_mb == 2048.0
        assert metrics.active_threads == 10
        assert metrics.active_tasks == 5
    
    def test_performance_metrics_to_dict(self):
        """测试性能指标转换为字典"""
        timestamp = datetime.now()
        metrics = PerformanceMetrics(
            timestamp=timestamp,
            cpu_percent=50.5,
            memory_percent=60.2,
            memory_used_mb=1024.5,
            memory_available_mb=2048.0,
            active_threads=10,
            active_tasks=5
        )
        
        data = metrics.to_dict()
        
        assert data['timestamp'] == timestamp.isoformat()
        assert data['cpu_percent'] == 50.5
        assert data['memory_percent'] == 60.2
        assert data['memory_used_mb'] == 1024.5
        assert data['memory_available_mb'] == 2048.0
        assert data['active_threads'] == 10
        assert data['active_tasks'] == 5


class TestPerformanceMonitor:
    """性能监控器测试"""
    
    @pytest.fixture
    def monitor(self):
        """创建性能监控器实例"""
        return PerformanceMonitor(
            collection_interval=1,  # 1秒间隔，便于测试
            history_size=10,
            alert_thresholds={'cpu_percent': 80.0, 'memory_percent': 85.0}
        )
    
    def test_monitor_initialization(self, monitor):
        """测试监控器初始化"""
        assert monitor.collection_interval == 1
        assert monitor.history_size == 10
        assert monitor.alert_thresholds['cpu_percent'] == 80.0
        assert monitor.alert_thresholds['memory_percent'] == 85.0
        assert not monitor.is_monitoring
        assert len(monitor.metrics_history) == 0
    
    def test_set_callbacks(self, monitor):
        """测试设置回调函数"""
        metrics_callback = Mock()
        threshold_callback = Mock()
        
        monitor.set_metrics_callback(metrics_callback)
        monitor.set_threshold_callback(threshold_callback)
        
        assert monitor.on_metrics_collected == metrics_callback
        assert monitor.on_threshold_exceeded == threshold_callback
    
    def test_collect_metrics(self, monitor):
        """测试收集性能指标"""
        with patch.object(monitor, 'process') as mock_process:
            # 模拟进程信息
            mock_process.cpu_percent.return_value = 45.5
            mock_process.memory_info.return_value = Mock(rss=1024 * 1024 * 512)  # 512MB
            mock_process.num_threads.return_value = 8
            
            with patch('health_monitor.utils.performance_monitor.psutil.virtual_memory') as mock_virtual_memory:
                # 模拟系统内存信息
                mock_virtual_memory.return_value = Mock(
                    total=1024 * 1024 * 1024 * 8,  # 8GB
                    available=1024 * 1024 * 1024 * 4  # 4GB
                )
                
                metrics = monitor._collect_metrics()
                
                assert metrics.cpu_percent == 45.5
                assert metrics.memory_used_mb == 512.0
                assert metrics.memory_available_mb == 4096.0
                assert metrics.active_threads == 8
                assert isinstance(metrics.timestamp, datetime)
    
    def test_threshold_checking(self, monitor):
        """测试阈值检查"""
        with patch.object(monitor, 'process') as mock_process:
            # 模拟高CPU使用率
            mock_process.cpu_percent.return_value = 85.0  # 超过80%阈值
            mock_process.memory_info.return_value = Mock(rss=1024 * 1024 * 512)
            mock_process.num_threads.return_value = 8
            
            with patch('health_monitor.utils.performance_monitor.psutil.virtual_memory') as mock_virtual_memory:
                mock_virtual_memory.return_value = Mock(
                    total=1024 * 1024 * 1024 * 8,
                    available=1024 * 1024 * 1024 * 4
                )
                
                threshold_callback = Mock()
                monitor.set_threshold_callback(threshold_callback)
                
                metrics = monitor._collect_metrics()
                monitor._check_thresholds(metrics)
                
                # 验证阈值超限回调被调用
                threshold_callback.assert_called_once_with('cpu_percent', 85.0, 80.0)
    
    @pytest.mark.asyncio
    async def test_monitoring_lifecycle(self, monitor):
        """测试监控生命周期"""
        assert not monitor.is_monitoring
        
        # 启动监控（短时间后停止）
        monitor_task = asyncio.create_task(monitor.start_monitoring())
        
        # 等待监控启动
        await asyncio.sleep(0.1)
        assert monitor.is_monitoring
        
        # 停止监控
        await monitor.stop_monitoring()
        assert not monitor.is_monitoring
        
        # 取消任务
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
    
    def test_get_current_metrics(self, monitor):
        """测试获取当前指标"""
        # 没有历史数据时应该收集新数据
        with patch.object(monitor, '_collect_metrics') as mock_collect:
            mock_metrics = Mock()
            mock_collect.return_value = mock_metrics
            
            result = monitor.get_current_metrics()
            assert result == mock_metrics
            mock_collect.assert_called_once()
    
    def test_get_metrics_history(self, monitor):
        """测试获取历史指标"""
        # 添加一些测试数据
        now = datetime.now()
        old_metrics = PerformanceMetrics(
            timestamp=now - timedelta(minutes=15),
            cpu_percent=30.0, memory_percent=40.0, memory_used_mb=500.0,
            memory_available_mb=1500.0, active_threads=5, active_tasks=2
        )
        recent_metrics = PerformanceMetrics(
            timestamp=now - timedelta(minutes=5),
            cpu_percent=50.0, memory_percent=60.0, memory_used_mb=800.0,
            memory_available_mb=1200.0, active_threads=8, active_tasks=4
        )
        
        monitor.metrics_history.extend([old_metrics, recent_metrics])
        
        # 获取10分钟内的历史
        history = monitor.get_metrics_history(10)
        assert len(history) == 1  # 只有recent_metrics在10分钟内
        assert history[0] == recent_metrics
    
    def test_get_average_metrics(self, monitor):
        """测试获取平均指标"""
        # 添加测试数据
        now = datetime.now()
        metrics1 = PerformanceMetrics(
            timestamp=now - timedelta(minutes=5),
            cpu_percent=40.0, memory_percent=50.0, memory_used_mb=600.0,
            memory_available_mb=1400.0, active_threads=6, active_tasks=3
        )
        metrics2 = PerformanceMetrics(
            timestamp=now - timedelta(minutes=2),
            cpu_percent=60.0, memory_percent=70.0, memory_used_mb=800.0,
            memory_available_mb=1200.0, active_threads=8, active_tasks=5
        )
        
        monitor.metrics_history.extend([metrics1, metrics2])
        
        avg = monitor.get_average_metrics(10)
        
        assert avg is not None
        assert avg['avg_cpu_percent'] == 50.0  # (40 + 60) / 2
        assert avg['avg_memory_percent'] == 60.0  # (50 + 70) / 2
        assert avg['avg_memory_used_mb'] == 700.0  # (600 + 800) / 2
        assert avg['sample_count'] == 2
    
    def test_get_peak_metrics(self, monitor):
        """测试获取峰值指标"""
        # 添加测试数据
        now = datetime.now()
        metrics1 = PerformanceMetrics(
            timestamp=now - timedelta(minutes=5),
            cpu_percent=40.0, memory_percent=50.0, memory_used_mb=600.0,
            memory_available_mb=1400.0, active_threads=6, active_tasks=3
        )
        metrics2 = PerformanceMetrics(
            timestamp=now - timedelta(minutes=2),
            cpu_percent=60.0, memory_percent=70.0, memory_used_mb=800.0,
            memory_available_mb=1200.0, active_threads=8, active_tasks=5
        )
        
        monitor.metrics_history.extend([metrics1, metrics2])
        
        peak = monitor.get_peak_metrics(10)
        
        assert peak is not None
        assert peak['peak_cpu_percent'] == 60.0
        assert peak['peak_memory_percent'] == 70.0
        assert peak['peak_memory_used_mb'] == 800.0
        assert peak['peak_active_threads'] == 8
        assert peak['peak_active_tasks'] == 5
    
    def test_update_thresholds(self, monitor):
        """测试更新阈值"""
        new_thresholds = {'cpu_percent': 90.0, 'memory_percent': 95.0}
        monitor.update_thresholds(new_thresholds)
        
        assert monitor.alert_thresholds['cpu_percent'] == 90.0
        assert monitor.alert_thresholds['memory_percent'] == 95.0
    
    def test_clear_history(self, monitor):
        """测试清空历史数据"""
        # 添加一些数据
        metrics = PerformanceMetrics(
            timestamp=datetime.now(),
            cpu_percent=50.0, memory_percent=60.0, memory_used_mb=700.0,
            memory_available_mb=1300.0, active_threads=7, active_tasks=4
        )
        monitor.metrics_history.append(metrics)
        
        assert len(monitor.metrics_history) == 1
        
        monitor.clear_history()
        assert len(monitor.metrics_history) == 0
    
    def test_export_metrics(self, monitor):
        """测试导出指标数据"""
        # 添加测试数据
        now = datetime.now()
        metrics = PerformanceMetrics(
            timestamp=now - timedelta(minutes=5),
            cpu_percent=45.0, memory_percent=55.0, memory_used_mb=650.0,
            memory_available_mb=1350.0, active_threads=7, active_tasks=3
        )
        monitor.metrics_history.append(metrics)
        
        exported = monitor.export_metrics(10)
        
        assert len(exported) == 1
        assert exported[0]['cpu_percent'] == 45.0
        assert exported[0]['memory_percent'] == 55.0
        assert 'timestamp' in exported[0]


class TestConnectionPoolManager:
    """连接池管理器测试"""
    
    @pytest.fixture
    def pool_manager(self):
        """创建连接池管理器实例"""
        return ConnectionPoolManager()
    
    def test_pool_manager_initialization(self, pool_manager):
        """测试连接池管理器初始化"""
        assert len(pool_manager.pools) == 0
        assert len(pool_manager.pool_configs) == 0
    
    def test_create_redis_pool(self, pool_manager):
        """测试创建Redis连接池"""
        with patch('redis.asyncio.ConnectionPool') as mock_pool_class:
            mock_pool = Mock()
            mock_pool_class.return_value = mock_pool
            
            config = {
                'host': 'localhost',
                'port': 6379,
                'password': 'test_password',
                'database': 1,
                'timeout': 10,
                'max_connections': 20
            }
            
            result = pool_manager.create_redis_pool('test_redis', config)
            
            assert result == mock_pool
            assert 'test_redis' in pool_manager.pools
            assert pool_manager.pools['test_redis'] == mock_pool
            assert 'test_redis' in pool_manager.pool_configs
            
            # 验证连接池配置
            mock_pool_class.assert_called_once()
            call_args = mock_pool_class.call_args[1]
            assert call_args['host'] == 'localhost'
            assert call_args['port'] == 6379
            assert call_args['password'] == 'test_password'
            assert call_args['db'] == 1
            assert call_args['max_connections'] == 20
    
    def test_create_mysql_pool(self, pool_manager):
        """测试创建MySQL连接池配置"""
        config = {
            'host': 'localhost',
            'port': 3306,
            'username': 'test_user',
            'password': 'test_password',
            'database': 'test_db',
            'timeout': 15,
            'max_connections': 15
        }
        
        result = pool_manager.create_mysql_pool('test_mysql', config)
        
        assert 'test_mysql' in pool_manager.pool_configs
        pool_config = pool_manager.pool_configs['test_mysql']
        assert pool_config['host'] == 'localhost'
        assert pool_config['port'] == 3306
        assert pool_config['user'] == 'test_user'
        assert pool_config['password'] == 'test_password'
        assert pool_config['db'] == 'test_db'
        assert pool_config['maxsize'] == 15
    
    def test_create_mongodb_pool(self, pool_manager):
        """测试创建MongoDB连接池"""
        with patch('motor.motor_asyncio.AsyncIOMotorClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            
            config = {
                'host': 'localhost',
                'port': 27017,
                'username': 'test_user',
                'password': 'test_password',
                'database': 'test_db',
                'timeout': 20,
                'max_connections': 25
            }
            
            result = pool_manager.create_mongodb_pool('test_mongo', config)
            
            assert result == mock_client
            assert 'test_mongo' in pool_manager.pools
            assert pool_manager.pools['test_mongo'] == mock_client
            
            # 验证客户端创建参数
            mock_client_class.assert_called_once()
            call_args = mock_client_class.call_args
            uri = call_args[0][0]
            assert 'test_user:test_password@localhost:27017/test_db' in uri
            
            kwargs = call_args[1]
            assert kwargs['maxPoolSize'] == 25
            assert kwargs['serverSelectionTimeoutMS'] == 20000
    
    def test_get_pool(self, pool_manager):
        """测试获取连接池"""
        # 不存在的连接池
        assert pool_manager.get_pool('nonexistent') is None
        
        # 添加一个模拟连接池
        mock_pool = Mock()
        pool_manager.pools['test_pool'] = mock_pool
        
        assert pool_manager.get_pool('test_pool') == mock_pool
    
    def test_remove_pool(self, pool_manager):
        """测试移除连接池"""
        # 添加模拟连接池
        mock_pool = Mock()
        pool_manager.pools['test_pool'] = mock_pool
        pool_manager.pool_configs['test_pool'] = {'host': 'localhost'}
        
        # 移除连接池
        pool_manager.remove_pool('test_pool')
        
        assert 'test_pool' not in pool_manager.pools
        assert 'test_pool' not in pool_manager.pool_configs
        
        # 验证close方法被调用
        mock_pool.close.assert_called_once()
    
    def test_get_pool_stats(self, pool_manager):
        """测试获取连接池统计信息"""
        # 添加模拟连接池
        mock_pool = Mock()
        mock_pool.__class__.__name__ = 'MockPool'
        pool_manager.pools['test_pool'] = mock_pool
        pool_manager.pool_configs['test_pool'] = {'host': 'localhost', 'port': 6379}
        
        stats = pool_manager.get_pool_stats()
        
        assert 'test_pool' in stats
        pool_stats = stats['test_pool']
        assert pool_stats['pool_key'] == 'test_pool'
        assert pool_stats['pool_type'] == 'MockPool'
        assert pool_stats['config']['host'] == 'localhost'
        assert pool_stats['config']['port'] == 6379
    
    def test_cleanup_all_pools(self, pool_manager):
        """测试清理所有连接池"""
        # 添加多个模拟连接池
        mock_pool1 = Mock()
        mock_pool2 = Mock()
        pool_manager.pools['pool1'] = mock_pool1
        pool_manager.pools['pool2'] = mock_pool2
        pool_manager.pool_configs['pool1'] = {}
        pool_manager.pool_configs['pool2'] = {}
        
        pool_manager.cleanup_all_pools()
        
        assert len(pool_manager.pools) == 0
        assert len(pool_manager.pool_configs) == 0
        
        # 验证close方法被调用
        mock_pool1.close.assert_called_once()
        mock_pool2.close.assert_called_once()