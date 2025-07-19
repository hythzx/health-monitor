"""MySQL健康检查器"""

import time
import asyncio
from typing import Dict, Any, Optional
import aiomysql
from .base import BaseHealthChecker
from .factory import register_checker
from ..models.health_check import HealthCheckResult
from ..utils.exceptions import CheckerError


@register_checker('mysql')
class MySQLHealthChecker(BaseHealthChecker):
    """MySQL健康检查器"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """
        初始化MySQL健康检查器
        
        Args:
            name: 服务名称
            config: MySQL配置
        """
        super().__init__(name, config)
        self._connection: Optional[aiomysql.Connection] = None
        self.logger.info(f"初始化MySQL检查器: {name}")
    
    def validate_config(self) -> bool:
        """
        验证MySQL配置
        
        Returns:
            bool: 配置是否有效
        """
        required_fields = ['host']
        for field in required_fields:
            if field not in self.config:
                self.logger.error(f"MySQL配置缺少必需字段: {field}")
                return False
        
        # 验证端口号
        port = self.config.get('port', 3306)
        if not isinstance(port, int) or port <= 0 or port > 65535:
            self.logger.error(f"MySQL端口号无效: {port}")
            return False
        
        # 验证用户名（如果提供）
        username = self.config.get('username')
        if username is not None and not isinstance(username, str):
            self.logger.error(f"MySQL用户名类型无效: {type(username)}")
            return False
        
        self.logger.debug(f"MySQL配置验证通过: host={self.config.get('host')}, port={port}")
        return True
    
    async def _create_connection(self) -> aiomysql.Connection:
        """
        创建新的MySQL连接
        
        Returns:
            aiomysql.Connection: MySQL连接
            
        Raises:
            CheckerError: 连接创建失败
        """
        host = self.config.get('host', 'localhost')
        port = self.config.get('port', 3306)
        username = self.config.get('username', 'root')
        password = self.config.get('password', '')
        database = self.config.get('database', '')
        timeout = self.get_timeout()
        
        self.logger.debug(f"创建MySQL连接: {username}@{host}:{port}/{database}, timeout={timeout}s")
        
        try:
            connection = await aiomysql.connect(
                host=host,
                port=port,
                user=username,
                password=password,
                db=database,
                connect_timeout=timeout,
                autocommit=True
            )
            self.logger.debug(f"MySQL连接创建成功: {host}:{port}")
            return connection
            
        except aiomysql.Error as e:
            error_msg = f"MySQL连接失败: {e}"
            self.logger.error(error_msg)
            raise CheckerError(error_msg)
        except Exception as e:
            error_msg = f"创建MySQL连接时发生未知错误: {e}"
            self.logger.error(error_msg, exc_info=True)
            raise CheckerError(error_msg)
    
    async def _test_connection(self, connection: aiomysql.Connection) -> bool:
        """
        测试连接是否有效
        
        Args:
            connection: MySQL连接
            
        Returns:
            bool: 连接是否有效
        """
        try:
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT 1")
                result = await cursor.fetchone()
                return result is not None and result[0] == 1
        except Exception as e:
            self.logger.warning(f"连接测试失败: {e}")
            return False
    
    async def check_health(self) -> HealthCheckResult:
        """
        执行MySQL健康检查
        
        Returns:
            HealthCheckResult: 健康检查结果
        """
        start_time = time.time()
        error_message = None
        is_healthy = False
        metadata = {}
        connection = None
        
        self.logger.debug(f"开始MySQL健康检查: {self.name}")
        
        try:
            # 创建新连接（每次都创建新连接以确保可靠性）
            connection_start = time.time()
            connection = await self._create_connection()
            connection_time = time.time() - connection_start
            metadata['connection_time'] = connection_time
            self.logger.debug(f"MySQL连接建立用时: {connection_time:.3f}s")
            
            # 执行基本的SELECT查询测试连接
            ping_start = time.time()
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT 1 AS test_value")
                result = await cursor.fetchone()
            ping_time = time.time() - ping_start
            
            self.logger.debug(f"MySQL基础查询结果: {result}, 用时: {ping_time:.3f}s")
            
            if result and result[0] == 1:
                is_healthy = True
                metadata['ping_time'] = ping_time
                self.logger.debug(f"MySQL基础健康检查通过")
                
                # 可选：执行更复杂的查询测试
                if self.config.get('test_queries', False):
                    self.logger.debug("执行扩展查询测试")
                    try:
                        # 测试数据库版本查询
                        version_start = time.time()
                        async with connection.cursor() as cursor:
                            await cursor.execute("SELECT VERSION()")
                            version_result = await cursor.fetchone()
                        version_time = time.time() - version_start
                        
                        if version_result:
                            metadata['version_query_time'] = version_time
                            metadata['mysql_version'] = version_result[0]
                            metadata['queries_test'] = 'passed'
                            self.logger.debug(f"MySQL版本查询成功: {version_result[0]}")
                        else:
                            metadata['queries_test'] = 'failed'
                            self.logger.warning("MySQL版本查询返回空结果")
                    except Exception as e:
                        metadata['queries_test'] = 'failed'
                        metadata['queries_error'] = str(e)
                        self.logger.warning(f"MySQL版本查询失败: {e}")
                
                # 可选：收集数据库状态信息
                if self.config.get('collect_status', False):
                    self.logger.debug("收集MySQL状态信息")
                    try:
                        status_start = time.time()
                        async with connection.cursor() as cursor:
                            # 获取连接数
                            await cursor.execute("SHOW STATUS LIKE 'Threads_connected'")
                            threads_result = await cursor.fetchone()
                            if threads_result:
                                metadata['connected_threads'] = int(threads_result[1])
                            
                            # 获取运行时间
                            await cursor.execute("SHOW STATUS LIKE 'Uptime'")
                            uptime_result = await cursor.fetchone()
                            if uptime_result:
                                metadata['uptime_seconds'] = int(uptime_result[1])
                            
                            # 获取查询数量
                            await cursor.execute("SHOW STATUS LIKE 'Questions'")
                            questions_result = await cursor.fetchone()
                            if questions_result:
                                metadata['total_questions'] = int(questions_result[1])
                        
                        status_time = time.time() - status_start
                        metadata['status_query_time'] = status_time
                        self.logger.debug(f"MySQL状态信息收集完成，用时: {status_time:.3f}s")
                        
                    except Exception as e:
                        # 状态查询失败不影响健康状态
                        metadata['status_error'] = str(e)
                        self.logger.warning(f"MySQL状态信息收集失败: {e}")
                
                # 可选：测试指定数据库的访问
                database = self.config.get('database')
                if database and self.config.get('test_database_access', False):
                    self.logger.debug(f"测试数据库访问: {database}")
                    try:
                        db_test_start = time.time()
                        async with connection.cursor() as cursor:
                            await cursor.execute(f"USE `{database}`")
                            await cursor.execute("SELECT DATABASE()")
                            db_result = await cursor.fetchone()
                        db_test_time = time.time() - db_test_start
                        
                        if db_result and db_result[0] == database:
                            metadata['database_access_time'] = db_test_time
                            metadata['database_test'] = 'passed'
                            self.logger.debug(f"数据库 {database} 访问测试成功")
                        else:
                            metadata['database_test'] = 'failed'
                            self.logger.warning(f"数据库 {database} 访问测试失败，期望: {database}, 实际: {db_result}")
                            
                    except Exception as e:
                        metadata['database_test'] = 'failed'
                        metadata['database_error'] = str(e)
                        self.logger.warning(f"数据库 {database} 访问测试异常: {e}")
            else:
                error_message = f"基础查询测试失败，返回结果: {result}"
                self.logger.error(error_message)
                
        except aiomysql.Error as e:
            error_message = f"MySQL数据库错误: {e}"
            self.logger.error(error_message)
        except asyncio.TimeoutError:
            error_message = "MySQL连接超时"
            self.logger.error(error_message)
        except CheckerError as e:
            error_message = str(e)
            self.logger.error(error_message)
        except Exception as e:
            error_message = f"MySQL健康检查异常: {e}"
            self.logger.error(error_message, exc_info=True)
        finally:
            # 确保连接被正确关闭
            if connection:
                try:
                    connection.close()
                    self.logger.debug("MySQL连接已关闭")
                except Exception as e:
                    self.logger.warning(f"关闭MySQL连接时出错: {e}")
        
        response_time = time.time() - start_time
        
        if is_healthy:
            self.logger.info(f"MySQL服务 {self.name} 健康检查成功，总用时: {response_time:.3f}s")
        else:
            self.logger.warning(f"MySQL服务 {self.name} 健康检查失败，总用时: {response_time:.3f}s，错误: {error_message}")
        
        return HealthCheckResult(
            service_name=self.name,
            service_type='mysql',
            is_healthy=is_healthy,
            response_time=response_time,
            error_message=error_message,
            metadata=metadata
        )
    
    async def close(self):
        """关闭MySQL连接"""
        # 由于每次检查都创建新连接，这里不需要特殊处理
        self.logger.debug(f"MySQL检查器 {self.name} 关闭")
        pass