"""MongoDB健康检查器"""

import time
import asyncio
from typing import Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorClient
from .base import BaseHealthChecker
from .factory import register_checker
from ..models.health_check import HealthCheckResult
from ..utils.exceptions import CheckerError


@register_checker('mongodb')
class MongoHealthChecker(BaseHealthChecker):
    """MongoDB健康检查器"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """
        初始化MongoDB健康检查器
        
        Args:
            name: 服务名称
            config: MongoDB配置
        """
        super().__init__(name, config)
        self._client: Optional[AsyncIOMotorClient] = None
    
    def validate_config(self) -> bool:
        """
        验证MongoDB配置
        
        Returns:
            bool: 配置是否有效
        """
        required_fields = ['host']
        for field in required_fields:
            if field not in self.config:
                return False
        
        # 验证端口号
        port = self.config.get('port', 27017)
        if not isinstance(port, int) or port <= 0 or port > 65535:
            return False
        
        # 验证用户名（如果提供）
        username = self.config.get('username')
        if username is not None and not isinstance(username, str):
            return False
        
        return True
    
    def _get_client(self) -> AsyncIOMotorClient:
        """
        获取MongoDB客户端实例
        
        Returns:
            AsyncIOMotorClient: MongoDB客户端
        """
        if self._client is None:
            host = self.config.get('host', 'localhost')
            port = self.config.get('port', 27017)
            username = self.config.get('username')
            password = self.config.get('password')
            database = self.config.get('database', 'admin')
            
            # 构建连接URI
            if username and password:
                uri = f"mongodb://{username}:{password}@{host}:{port}/{database}"
            else:
                uri = f"mongodb://{host}:{port}/{database}"
            
            self._client = AsyncIOMotorClient(
                uri,
                serverSelectionTimeoutMS=self.get_timeout() * 1000,
                connectTimeoutMS=self.get_timeout() * 1000,
                socketTimeoutMS=self.get_timeout() * 1000
            )
        return self._client
    
    async def check_health(self) -> HealthCheckResult:
        """
        执行MongoDB健康检查
        
        Returns:
            HealthCheckResult: 健康检查结果
        """
        self.logger.debug(f"开始执行MongoDB健康检查: {self.name}")
        start_time = time.time()
        error_message = None
        is_healthy = False
        metadata = {}
        
        try:
            client = self._get_client()
            self.logger.debug(f"MongoDB客户端已创建，连接到 {self.config.get('host')}:{self.config.get('port', 27017)}")
            
            # 执行ping命令测试连接
            ping_start = time.time()
            await client.admin.command('ping')
            ping_time = time.time() - ping_start
            
            is_healthy = True
            metadata['ping_time'] = ping_time
            self.logger.info(f"MongoDB服务 {self.name} PING测试成功，响应时间: {ping_time:.3f}秒")
            
            # 可选：执行简单的查询测试
            if self.config.get('test_queries', False):
                database_name = self.config.get('database', 'admin')
                db = client[database_name]
                
                # 测试列出集合
                collections_start = time.time()
                collections = await db.list_collection_names()
                collections_time = time.time() - collections_start
                
                metadata['collections_query_time'] = collections_time
                metadata['collections_count'] = len(collections)
                metadata['queries_test'] = 'passed'
                
                # 可选：测试简单的文档操作
                if self.config.get('test_operations', False):
                    test_collection = db['health_check_test']
                    test_doc = {'test': True, 'timestamp': time.time()}
                    
                    # 插入测试文档
                    insert_start = time.time()
                    result = await test_collection.insert_one(test_doc)
                    insert_time = time.time() - insert_start
                    
                    # 查询测试文档
                    find_start = time.time()
                    found_doc = await test_collection.find_one({'_id': result.inserted_id})
                    find_time = time.time() - find_start
                    
                    # 删除测试文档
                    await test_collection.delete_one({'_id': result.inserted_id})
                    
                    if found_doc and found_doc['test'] is True:
                        metadata['insert_time'] = insert_time
                        metadata['find_time'] = find_time
                        metadata['operations_test'] = 'passed'
                    else:
                        metadata['operations_test'] = 'failed'
            
            # 可选：收集服务器状态信息
            if self.config.get('collect_status', False):
                try:
                    status_start = time.time()
                    
                    # 获取服务器状态
                    server_status = await client.admin.command('serverStatus')
                    status_time = time.time() - status_start
                    
                    metadata['status_query_time'] = status_time
                    metadata['mongodb_version'] = server_status.get('version')
                    metadata['uptime_seconds'] = server_status.get('uptime')
                    
                    # 连接信息
                    connections = server_status.get('connections', {})
                    metadata['current_connections'] = connections.get('current')
                    metadata['available_connections'] = connections.get('available')
                    
                    # 内存使用
                    mem = server_status.get('mem', {})
                    metadata['resident_memory_mb'] = mem.get('resident')
                    metadata['virtual_memory_mb'] = mem.get('virtual')
                    
                except Exception as e:
                    # 状态查询失败不影响健康状态
                    metadata['status_error'] = str(e)
            
            # 可选：测试指定数据库的访问
            database = self.config.get('database')
            if database and database != 'admin' and self.config.get('test_database_access', False):
                try:
                    db_test_start = time.time()
                    db = client[database]
                    
                    # 测试数据库统计信息
                    stats = await db.command('dbStats')
                    db_test_time = time.time() - db_test_start
                    
                    if stats:
                        metadata['database_access_time'] = db_test_time
                        metadata['database_test'] = 'passed'
                        metadata['database_size_bytes'] = stats.get('dataSize', 0)
                        metadata['database_collections'] = stats.get('collections', 0)
                    else:
                        metadata['database_test'] = 'failed'
                        
                except Exception as e:
                    metadata['database_test'] = 'failed'
                    metadata['database_error'] = str(e)
                    
        except Exception as e:
            error_message = f"MongoDB健康检查异常: {e}"
            self.logger.error(f"MongoDB服务 {self.name} 健康检查异常: {e}", exc_info=True)
        finally:
            # 关闭连接
            if self._client:
                try:
                    self._client.close()
                    self.logger.debug(f"MongoDB客户端连接已关闭: {self.name}")
                except Exception as e:
                    self.logger.warning(f"关闭MongoDB客户端连接时出错: {e}")
                self._client = None
        
        response_time = time.time() - start_time
        
        if is_healthy:
            self.logger.info(f"MongoDB服务 {self.name} 健康检查成功，总耗时: {response_time:.3f}秒")
        else:
            self.logger.warning(f"MongoDB服务 {self.name} 健康检查失败，总耗时: {response_time:.3f}秒，错误: {error_message}")
        
        return HealthCheckResult(
            service_name=self.name,
            service_type='mongodb',
            is_healthy=is_healthy,
            response_time=response_time,
            error_message=error_message,
            metadata=metadata
        )
    
    async def close(self):
        """关闭MongoDB连接"""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None