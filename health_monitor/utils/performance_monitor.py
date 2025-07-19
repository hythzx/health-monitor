"""性能监控模块

提供系统性能监控功能，包括内存使用、CPU占用等指标的监控
"""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable

import psutil


@dataclass
class PerformanceMetrics:
    """性能指标数据类"""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_available_mb: float
    active_threads: int
    active_tasks: int

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


class PerformanceMonitor:
    """性能监控器
    
    监控系统资源使用情况，包括CPU、内存、线程数等
    """

    def __init__(self,
                 collection_interval: int = 10,
                 history_size: int = 100,
                 alert_thresholds: Optional[Dict[str, float]] = None):
        """初始化性能监控器
        
        Args:
            collection_interval: 数据收集间隔（秒）
            history_size: 历史数据保存数量
            alert_thresholds: 告警阈值配置
        """
        self.collection_interval = collection_interval
        self.history_size = history_size
        self.alert_thresholds = alert_thresholds or {
            'cpu_percent': 80.0,
            'memory_percent': 85.0
        }

        self.metrics_history: deque = deque(maxlen=history_size)
        self.is_monitoring = False
        self.monitor_task: Optional[asyncio.Task] = None
        self.logger = logging.getLogger(__name__)

        # 回调函数
        self.on_metrics_collected: Optional[Callable[[PerformanceMetrics], None]] = None
        self.on_threshold_exceeded: Optional[Callable[[str, float, float], None]] = None

        # 进程对象
        self.process = psutil.Process()

    def set_metrics_callback(self, callback: Callable[[PerformanceMetrics], None]):
        """设置指标收集回调函数
        
        Args:
            callback: 指标收集回调函数
        """
        self.on_metrics_collected = callback

    def set_threshold_callback(self, callback: Callable[[str, float, float], None]):
        """设置阈值超限回调函数
        
        Args:
            callback: 阈值超限回调函数，参数为(指标名, 当前值, 阈值)
        """
        self.on_threshold_exceeded = callback

    async def start_monitoring(self):
        """开始性能监控"""
        if self.is_monitoring:
            self.logger.warning("性能监控已经在运行")
            return

        self.is_monitoring = True
        self.logger.info(f"开始性能监控，收集间隔: {self.collection_interval}秒")

        # 启动监控任务
        self.monitor_task = asyncio.create_task(self._monitoring_loop())

        try:
            await self.monitor_task
        except asyncio.CancelledError:
            self.logger.info("性能监控被取消")
        except Exception as e:
            self.logger.error(f"性能监控异常: {e}")
        finally:
            self.is_monitoring = False

    async def stop_monitoring(self):
        """停止性能监控"""
        if not self.is_monitoring:
            return

        self.is_monitoring = False

        if self.monitor_task and not self.monitor_task.done():
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass

        self.logger.info("性能监控已停止")

    async def _monitoring_loop(self):
        """监控循环"""
        while self.is_monitoring:
            try:
                # 收集性能指标
                metrics = self._collect_metrics()

                # 保存到历史记录
                self.metrics_history.append(metrics)

                # 检查阈值
                self._check_thresholds(metrics)

                # 调用回调函数
                if self.on_metrics_collected:
                    self.on_metrics_collected(metrics)

                # 记录日志
                self.logger.debug(
                    f"性能指标 - CPU: {metrics.cpu_percent:.1f}%, "
                    f"内存: {metrics.memory_percent:.1f}%, "
                    f"线程: {metrics.active_threads}, "
                    f"任务: {metrics.active_tasks}"
                )

                # 等待下次收集
                await asyncio.sleep(self.collection_interval)

            except Exception as e:
                self.logger.error(f"收集性能指标异常: {e}")
                await asyncio.sleep(self.collection_interval)

    def _collect_metrics(self) -> PerformanceMetrics:
        """收集当前性能指标
        
        Returns:
            性能指标对象
        """
        # CPU使用率
        cpu_percent = self.process.cpu_percent()

        # 内存信息
        memory_info = self.process.memory_info()
        system_memory = psutil.virtual_memory()

        memory_used_mb = memory_info.rss / 1024 / 1024  # 转换为MB
        memory_percent = (memory_info.rss / system_memory.total) * 100
        memory_available_mb = system_memory.available / 1024 / 1024

        # 线程数
        active_threads = self.process.num_threads()

        # 异步任务数（当前事件循环中的任务）
        active_tasks = 0
        try:
            loop = asyncio.get_running_loop()
            active_tasks = len(
                [task for task in asyncio.all_tasks(loop) if not task.done()])
        except RuntimeError:
            # 没有运行中的事件循环
            pass

        return PerformanceMetrics(
            timestamp=datetime.now(),
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_used_mb=memory_used_mb,
            memory_available_mb=memory_available_mb,
            active_threads=active_threads,
            active_tasks=active_tasks
        )

    def _check_thresholds(self, metrics: PerformanceMetrics):
        """检查性能指标是否超过阈值
        
        Args:
            metrics: 性能指标
        """
        # 检查CPU使用率
        cpu_threshold = self.alert_thresholds.get('cpu_percent')
        if cpu_threshold and metrics.cpu_percent > cpu_threshold:
            self.logger.warning(
                f"CPU使用率超过阈值: {metrics.cpu_percent:.1f}% > {cpu_threshold}%")
            if self.on_threshold_exceeded:
                self.on_threshold_exceeded('cpu_percent', metrics.cpu_percent,
                                           cpu_threshold)

        # 检查内存使用率
        memory_threshold = self.alert_thresholds.get('memory_percent')
        if memory_threshold and metrics.memory_percent > memory_threshold:
            self.logger.warning(
                f"内存使用率超过阈值: {metrics.memory_percent:.1f}% > {memory_threshold}%")
            if self.on_threshold_exceeded:
                self.on_threshold_exceeded('memory_percent', metrics.memory_percent,
                                           memory_threshold)

    def get_current_metrics(self) -> Optional[PerformanceMetrics]:
        """获取当前性能指标
        
        Returns:
            当前性能指标，如果没有数据返回None
        """
        if not self.metrics_history:
            return self._collect_metrics()
        return self.metrics_history[-1]

    def get_metrics_history(self, minutes: int = 10) -> List[PerformanceMetrics]:
        """获取指定时间范围内的性能指标历史
        
        Args:
            minutes: 时间范围（分钟）
            
        Returns:
            性能指标历史列表
        """
        if not self.metrics_history:
            return []

        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        return [
            metrics for metrics in self.metrics_history
            if metrics.timestamp >= cutoff_time
        ]

    def get_average_metrics(self, minutes: int = 10) -> Optional[Dict[str, float]]:
        """获取指定时间范围内的平均性能指标
        
        Args:
            minutes: 时间范围（分钟）
            
        Returns:
            平均性能指标字典
        """
        history = self.get_metrics_history(minutes)
        if not history:
            return None

        total_cpu = sum(m.cpu_percent for m in history)
        total_memory = sum(m.memory_percent for m in history)
        total_memory_mb = sum(m.memory_used_mb for m in history)
        total_threads = sum(m.active_threads for m in history)
        total_tasks = sum(m.active_tasks for m in history)

        count = len(history)

        return {
            'avg_cpu_percent': total_cpu / count,
            'avg_memory_percent': total_memory / count,
            'avg_memory_used_mb': total_memory_mb / count,
            'avg_active_threads': total_threads / count,
            'avg_active_tasks': total_tasks / count,
            'sample_count': count
        }

    def get_peak_metrics(self, minutes: int = 10) -> Optional[Dict[str, float]]:
        """获取指定时间范围内的峰值性能指标
        
        Args:
            minutes: 时间范围（分钟）
            
        Returns:
            峰值性能指标字典
        """
        history = self.get_metrics_history(minutes)
        if not history:
            return None

        return {
            'peak_cpu_percent': max(m.cpu_percent for m in history),
            'peak_memory_percent': max(m.memory_percent for m in history),
            'peak_memory_used_mb': max(m.memory_used_mb for m in history),
            'peak_active_threads': max(m.active_threads for m in history),
            'peak_active_tasks': max(m.active_tasks for m in history)
        }

    def update_thresholds(self, thresholds: Dict[str, float]):
        """更新告警阈值
        
        Args:
            thresholds: 新的阈值配置
        """
        self.alert_thresholds.update(thresholds)
        self.logger.info(f"更新性能告警阈值: {self.alert_thresholds}")

    def clear_history(self):
        """清空历史数据"""
        self.metrics_history.clear()
        self.logger.info("清空性能监控历史数据")

    def export_metrics(self, minutes: int = 60) -> List[Dict[str, Any]]:
        """导出性能指标数据
        
        Args:
            minutes: 导出时间范围（分钟）
            
        Returns:
            性能指标数据列表
        """
        history = self.get_metrics_history(minutes)
        return [metrics.to_dict() for metrics in history]


class ConnectionPoolManager:
    """连接池管理器
    
    管理各种服务的连接池，实现连接复用和资源优化
    """

    def __init__(self):
        self.pools: Dict[str, Any] = {}
        self.pool_configs: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger(__name__)

    def create_redis_pool(self, pool_key: str, config: Dict[str, Any]) -> Any:
        """创建Redis连接池
        
        Args:
            pool_key: 连接池键名
            config: Redis配置
            
        Returns:
            Redis连接池对象
        """
        try:
            import redis.asyncio as redis

            pool_config = {
                'host': config.get('host', 'localhost'),
                'port': config.get('port', 6379),
                'password': config.get('password'),
                'db': config.get('database', 0),
                'max_connections': config.get('max_connections', 10),
                'retry_on_timeout': True,
                'socket_timeout': config.get('timeout', 5),
                'socket_connect_timeout': config.get('timeout', 5)
            }

            # 移除None值
            pool_config = {k: v for k, v in pool_config.items() if v is not None}

            pool = redis.ConnectionPool(**pool_config)
            self.pools[pool_key] = pool
            self.pool_configs[pool_key] = pool_config

            self.logger.info(f"创建Redis连接池: {pool_key}")
            return pool

        except ImportError:
            self.logger.error("Redis库未安装，无法创建Redis连接池")
            raise
        except Exception as e:
            self.logger.error(f"创建Redis连接池失败: {e}")
            raise

    def create_mysql_pool(self, pool_key: str, config: Dict[str, Any]) -> Any:
        """创建MySQL连接池
        
        Args:
            pool_key: 连接池键名
            config: MySQL配置
            
        Returns:
            MySQL连接池对象
        """
        try:
            import aiomysql

            pool_config = {
                'host': config.get('host', 'localhost'),
                'port': config.get('port', 3306),
                'user': config.get('username', 'root'),
                'password': config.get('password', ''),
                'db': config.get('database', ''),
                'minsize': config.get('min_connections', 1),
                'maxsize': config.get('max_connections', 10),
                'connect_timeout': config.get('timeout', 10)
            }

            # 这里返回配置，实际的池创建需要在异步环境中
            self.pool_configs[pool_key] = pool_config
            self.logger.info(f"配置MySQL连接池: {pool_key}")
            return pool_config

        except ImportError:
            self.logger.error("aiomysql库未安装，无法创建MySQL连接池")
            raise
        except Exception as e:
            self.logger.error(f"配置MySQL连接池失败: {e}")
            raise

    def create_mongodb_pool(self, pool_key: str, config: Dict[str, Any]) -> Any:
        """创建MongoDB连接池
        
        Args:
            pool_key: 连接池键名
            config: MongoDB配置
            
        Returns:
            MongoDB客户端对象
        """
        try:
            from motor.motor_asyncio import AsyncIOMotorClient

            # 构建连接URI
            host = config.get('host', 'localhost')
            port = config.get('port', 27017)
            username = config.get('username')
            password = config.get('password')
            database = config.get('database', 'test')

            if username and password:
                uri = f"mongodb://{username}:{password}@{host}:{port}/{database}"
            else:
                uri = f"mongodb://{host}:{port}/{database}"

            client_config = {
                'maxPoolSize': config.get('max_connections', 10),
                'minPoolSize': config.get('min_connections', 1),
                'serverSelectionTimeoutMS': config.get('timeout', 10) * 1000,
                'connectTimeoutMS': config.get('timeout', 10) * 1000
            }

            client = AsyncIOMotorClient(uri, **client_config)
            self.pools[pool_key] = client
            self.pool_configs[pool_key] = {'uri': uri, **client_config}

            self.logger.info(f"创建MongoDB连接池: {pool_key}")
            return client

        except ImportError:
            self.logger.error("motor库未安装，无法创建MongoDB连接池")
            raise
        except Exception as e:
            self.logger.error(f"创建MongoDB连接池失败: {e}")
            raise

    def get_pool(self, pool_key: str) -> Optional[Any]:
        """获取连接池
        
        Args:
            pool_key: 连接池键名
            
        Returns:
            连接池对象，如果不存在返回None
        """
        return self.pools.get(pool_key)

    def remove_pool(self, pool_key: str):
        """移除连接池
        
        Args:
            pool_key: 连接池键名
        """
        if pool_key in self.pools:
            pool = self.pools[pool_key]

            # 尝试关闭连接池
            try:
                if hasattr(pool, 'close'):
                    pool.close()
                elif hasattr(pool, 'disconnect'):
                    pool.disconnect()
            except Exception as e:
                self.logger.warning(f"关闭连接池 {pool_key} 时出现异常: {e}")

            del self.pools[pool_key]
            if pool_key in self.pool_configs:
                del self.pool_configs[pool_key]

            self.logger.info(f"移除连接池: {pool_key}")

    def get_pool_stats(self) -> Dict[str, Any]:
        """获取连接池统计信息
        
        Returns:
            连接池统计信息
        """
        stats = {}

        for pool_key, pool in self.pools.items():
            pool_stats = {
                'pool_key': pool_key,
                'pool_type': type(pool).__name__,
                'config': self.pool_configs.get(pool_key, {})
            }

            # 尝试获取连接池特定的统计信息
            try:
                if hasattr(pool, 'created_connections'):
                    pool_stats['created_connections'] = pool.created_connections
                if hasattr(pool, 'available_connections'):
                    pool_stats['available_connections'] = len(pool.available_connections)
                if hasattr(pool, 'in_use_connections'):
                    pool_stats['in_use_connections'] = len(pool.in_use_connections)
            except Exception as e:
                self.logger.debug(f"获取连接池 {pool_key} 统计信息失败: {e}")

            stats[pool_key] = pool_stats

        return stats

    def cleanup_all_pools(self):
        """清理所有连接池"""
        pool_keys = list(self.pools.keys())
        for pool_key in pool_keys:
            self.remove_pool(pool_key)

        self.logger.info("清理所有连接池完成")


# 全局连接池管理器实例
connection_pool_manager = ConnectionPoolManager()
