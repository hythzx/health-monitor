"""Redis健康检查器"""

import time
from typing import Dict, Any, Optional

import redis.asyncio as redis

from .base import BaseHealthChecker
from .factory import register_checker
from ..models.health_check import HealthCheckResult
from ..utils.performance_monitor import connection_pool_manager


@register_checker('redis')
class RedisHealthChecker(BaseHealthChecker):
    """Redis健康检查器"""

    def __init__(self, name: str, config: Dict[str, Any]):
        """
        初始化Redis健康检查器
        
        Args:
            name: 服务名称
            config: Redis配置
        """
        super().__init__(name, config)
        self._client: Optional[redis.Redis] = None
        self._pool_key = f"redis_{name}"
        self._use_pool = config.get('use_connection_pool', True)

    def validate_config(self) -> bool:
        """
        验证Redis配置
        
        Returns:
            bool: 配置是否有效
        """
        required_fields = ['host']
        for field in required_fields:
            if field not in self.config:
                return False

        # 验证端口号
        port = self.config.get('port', 6379)
        if not isinstance(port, int) or port <= 0 or port > 65535:
            return False

        # 验证数据库编号
        database = self.config.get('database', 0)
        if not isinstance(database, int) or database < 0:
            return False

        return True

    def _get_client(self) -> redis.Redis:
        """
        获取Redis客户端实例
        
        Returns:
            redis.Redis: Redis客户端
        """
        if self._use_pool:
            # 使用连接池
            pool = connection_pool_manager.get_pool(self._pool_key)
            if pool is None:
                # 创建连接池
                pool_config = {
                    'host': self.config.get('host', 'localhost'),
                    'port': self.config.get('port', 6379),
                    'password': self.config.get('password'),
                    'database': self.config.get('database', 0),
                    'timeout': self.get_timeout(),
                    'max_connections': self.config.get('max_connections', 10)
                }
                pool = connection_pool_manager.create_redis_pool(self._pool_key,
                                                                 pool_config)

            return redis.Redis(connection_pool=pool, decode_responses=True)
        else:
            # 使用单独连接
            if self._client is None:
                self._client = redis.Redis(
                    host=self.config.get('host', 'localhost'),
                    port=self.config.get('port', 6379),
                    db=self.config.get('database', 0),
                    password=self.config.get('password'),
                    socket_timeout=self.get_timeout(),
                    socket_connect_timeout=self.get_timeout(),
                    decode_responses=True
                )
            return self._client

    async def check_health(self) -> HealthCheckResult:
        """
        执行Redis健康检查
        
        Returns:
            HealthCheckResult: 健康检查结果
        """
        self.logger.debug(f"开始执行Redis健康检查: {self.name}")
        start_time = time.time()
        error_message = None
        is_healthy = False
        metadata = {}

        try:
            client = self._get_client()
            self.logger.debug(
                f"Redis客户端已创建，连接到 {self.config.get('host')}:{self.config.get('port', 6379)}")

            # 执行PING命令测试连接
            ping_start = time.time()
            ping_result = await client.ping()
            ping_time = time.time() - ping_start

            self.logger.debug(
                f"PING命令执行完成，结果: {ping_result}, 耗时: {ping_time:.3f}秒")

            if ping_result:
                is_healthy = True
                metadata['ping_time'] = ping_time
                self.logger.info(
                    f"Redis服务 {self.name} PING测试成功，响应时间: {ping_time:.3f}秒")

                # 可选：执行简单的SET/GET操作测试
                if self.config.get('test_operations', False):
                    self.logger.debug("开始执行SET/GET操作测试")
                    test_key = f"health_check:{self.name}:{int(time.time())}"
                    test_value = "health_check_value"

                    # SET操作
                    set_start = time.time()
                    await client.set(test_key, test_value, ex=60)  # 60秒过期
                    set_time = time.time() - set_start

                    # GET操作
                    get_start = time.time()
                    retrieved_value = await client.get(test_key)
                    get_time = time.time() - get_start

                    # 清理测试键
                    await client.delete(test_key)

                    if retrieved_value == test_value:
                        metadata['set_time'] = set_time
                        metadata['get_time'] = get_time
                        metadata['operations_test'] = 'passed'
                        self.logger.info(
                            f"Redis服务 {self.name} SET/GET操作测试成功，SET耗时: {set_time:.3f}秒, GET耗时: {get_time:.3f}秒")
                    else:
                        is_healthy = False
                        error_message = "SET/GET操作测试失败"
                        metadata['operations_test'] = 'failed'
                        self.logger.error(
                            f"Redis服务 {self.name} SET/GET操作测试失败，期望值: {test_value}, 实际值: {retrieved_value}")

                # 获取Redis信息
                if self.config.get('collect_info', False):
                    try:
                        self.logger.debug("开始收集Redis信息")
                        info = await client.info()
                        metadata['redis_version'] = info.get('redis_version')
                        metadata['connected_clients'] = info.get('connected_clients')
                        metadata['used_memory'] = info.get('used_memory')
                        metadata['uptime_in_seconds'] = info.get('uptime_in_seconds')
                        self.logger.debug(
                            f"Redis信息收集成功，版本: {info.get('redis_version')}, 连接数: {info.get('connected_clients')}")
                    except Exception as e:
                        # INFO命令失败不影响健康状态
                        metadata['info_error'] = str(e)
                        self.logger.warning(f"Redis服务 {self.name} 信息收集失败: {e}")
            else:
                error_message = "PING命令返回False"
                self.logger.error(f"Redis服务 {self.name} PING命令返回False")

        except redis.ConnectionError as e:
            error_message = f"Redis连接错误: {e}"
            self.logger.error(f"Redis服务 {self.name} 连接错误: {e}")
        except redis.TimeoutError as e:
            error_message = f"Redis连接超时: {e}"
            self.logger.error(f"Redis服务 {self.name} 连接超时: {e}")
        except redis.AuthenticationError as e:
            error_message = f"Redis认证失败: {e}"
            self.logger.error(f"Redis服务 {self.name} 认证失败: {e}")
        except redis.ResponseError as e:
            error_message = f"Redis响应错误: {e}"
            self.logger.error(f"Redis服务 {self.name} 响应错误: {e}")
        except Exception as e:
            error_message = f"Redis健康检查异常: {e}"
            self.logger.error(f"Redis服务 {self.name} 健康检查异常: {e}", exc_info=True)
        finally:
            # 如果不使用连接池，关闭连接
            if not self._use_pool and self._client:
                try:
                    await self._client.aclose()
                    self.logger.debug(f"Redis客户端连接已关闭: {self.name}")
                except Exception as e:
                    self.logger.warning(f"关闭Redis客户端连接时出错: {e}")
                self._client = None

        response_time = time.time() - start_time

        if is_healthy:
            self.logger.info(
                f"Redis服务 {self.name} 健康检查成功，总耗时: {response_time:.3f}秒")
        else:
            self.logger.warning(
                f"Redis服务 {self.name} 健康检查失败，总耗时: {response_time:.3f}秒，错误: {error_message}")

        return HealthCheckResult(
            service_name=self.name,
            service_type='redis',
            is_healthy=is_healthy,
            response_time=response_time,
            error_message=error_message,
            metadata=metadata
        )

    async def close(self):
        """关闭Redis连接"""
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None
