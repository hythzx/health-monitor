"""EMQX健康检查器"""

import asyncio
import time
from typing import Dict, Any, Optional

import aiohttp
from aiomqtt import Client as MQTTClient

from .base import BaseHealthChecker
from .factory import register_checker
from ..models.health_check import HealthCheckResult


@register_checker('emqx')
class EMQXHealthChecker(BaseHealthChecker):
    """EMQX健康检查器"""

    def __init__(self, name: str, config: Dict[str, Any]):
        """
        初始化EMQX健康检查器
        
        Args:
            name: 服务名称
            config: EMQX配置
        """
        super().__init__(name, config)

    def validate_config(self) -> bool:
        """
        验证EMQX配置
        
        Returns:
            bool: 配置是否有效
        """
        required_fields = ['host']
        for field in required_fields:
            if field not in self.config:
                return False

        # 验证端口号
        port = self.config.get('port', 1883)
        if not isinstance(port, int) or port <= 0 or port > 65535:
            return False

        # 验证用户名（如果提供）
        username = self.config.get('username')
        if username is not None and not isinstance(username, str):
            return False

        # 验证客户端ID（如果提供）
        client_id = self.config.get('client_id')
        if client_id is not None and not isinstance(client_id, str):
            return False

        return True

    async def _check_mqtt_connection(self) -> tuple[
        bool, float, Optional[str], Dict[str, Any]]:
        """
        通过MQTT协议检查EMQX连接
        
        Returns:
            tuple: (是否健康, 响应时间, 错误信息, 元数据)
        """
        start_time = time.time()
        error_message = None
        metadata = {}

        try:
            host = self.config.get('host', 'localhost')
            port = self.config.get('port', 1883)
            username = self.config.get('username')
            password = self.config.get('password')
            client_id = self.config.get('client_id', f'health_check_{int(time.time())}')

            # 创建MQTT客户端
            async with MQTTClient(
                    hostname=host,
                    port=port,
                    username=username,
                    password=password,
                    client_id=client_id,
                    timeout=self.get_timeout()
            ) as client:
                connect_time = time.time() - start_time
                metadata['connect_time'] = connect_time

                # 可选：测试发布/订阅功能
                if self.config.get('test_pubsub', False):
                    test_topic = f"health_check/{self.name}/{int(time.time())}"
                    test_message = f"health_check_message_{int(time.time())}"

                    # 订阅测试主题
                    subscribe_start = time.time()
                    await client.subscribe(test_topic)
                    subscribe_time = time.time() - subscribe_start
                    metadata['subscribe_time'] = subscribe_time

                    # 发布测试消息
                    publish_start = time.time()
                    await client.publish(test_topic, test_message)
                    publish_time = time.time() - publish_start
                    metadata['publish_time'] = publish_time

                    # 等待接收消息
                    try:
                        async with asyncio.timeout(2):  # 2秒超时
                            async for message in client.messages:
                                if message.topic.matches(
                                        test_topic) and message.payload.decode() == test_message:
                                    metadata['pubsub_test'] = 'passed'
                                    break
                    except asyncio.TimeoutError:
                        metadata['pubsub_test'] = 'timeout'
                    except Exception as e:
                        metadata['pubsub_test'] = 'failed'
                        metadata['pubsub_error'] = str(e)

                return True, time.time() - start_time, None, metadata

        except Exception as e:
            error_message = f"MQTT连接测试失败: {e}"
            return False, time.time() - start_time, error_message, metadata

    async def _check_http_api(self) -> tuple[bool, float, Optional[str], Dict[str, Any]]:
        """
        通过HTTP API检查EMQX状态
        
        Returns:
            tuple: (是否健康, 响应时间, 错误信息, 元数据)
        """
        start_time = time.time()
        error_message = None
        metadata = {}

        try:
            host = self.config.get('host', 'localhost')
            api_port = self.config.get('api_port', 18083)
            api_username = self.config.get('api_username', 'admin')
            api_password = self.config.get('api_password', 'public')

            # EMQX API端点
            api_url = f"http://{host}:{api_port}/api/v5/status"

            timeout = aiohttp.ClientTimeout(total=self.get_timeout())
            auth = aiohttp.BasicAuth(api_username, api_password)

            async with aiohttp.ClientSession(timeout=timeout, auth=auth) as session:
                async with session.get(api_url) as response:
                    api_time = time.time() - start_time
                    metadata['api_response_time'] = api_time

                    if response.status == 200:
                        data = await response.json()
                        metadata['api_status'] = 'success'
                        metadata['emqx_status'] = data

                        # 可选：获取更多统计信息
                        if self.config.get('collect_stats', False):
                            stats_url = f"http://{host}:{api_port}/api/v5/stats"
                            async with session.get(stats_url) as stats_response:
                                if stats_response.status == 200:
                                    stats_data = await stats_response.json()
                                    metadata['emqx_stats'] = stats_data

                                    # 提取关键统计信息
                                    if isinstance(stats_data, dict):
                                        metadata['connections_count'] = stats_data.get(
                                            'connections.count', 0)
                                        metadata['sessions_count'] = stats_data.get(
                                            'sessions.count', 0)
                                        metadata['topics_count'] = stats_data.get(
                                            'topics.count', 0)
                                        metadata['subscriptions_count'] = stats_data.get(
                                            'subscriptions.count', 0)

                        return True, time.time() - start_time, None, metadata
                    else:
                        error_message = f"HTTP API返回状态码: {response.status}"
                        return False, time.time() - start_time, error_message, metadata

        except Exception as e:
            error_message = f"HTTP API检查失败: {e}"
            return False, time.time() - start_time, error_message, metadata

    async def check_health(self) -> HealthCheckResult:
        """
        执行EMQX健康检查
        
        Returns:
            HealthCheckResult: 健康检查结果
        """
        start_time = time.time()
        error_message = None
        is_healthy = False
        metadata = {}

        try:
            # 优先使用MQTT连接测试
            check_method = self.config.get('check_method', 'mqtt')

            if check_method == 'mqtt':
                is_healthy, response_time, error_message, mqtt_metadata = await self._check_mqtt_connection()
                metadata.update(mqtt_metadata)
                metadata['check_method'] = 'mqtt'

                # 如果MQTT检查成功且配置了API检查，也执行API检查
                if is_healthy and self.config.get('also_check_api', False):
                    try:
                        api_healthy, api_time, api_error, api_metadata = await self._check_http_api()
                        metadata.update({f'api_{k}': v for k, v in api_metadata.items()})
                        metadata['api_check'] = 'passed' if api_healthy else 'failed'
                        if api_error:
                            metadata['api_error'] = api_error
                    except Exception as e:
                        metadata['api_check'] = 'failed'
                        metadata['api_error'] = str(e)

            elif check_method == 'http':
                is_healthy, response_time, error_message, http_metadata = await self._check_http_api()
                metadata.update(http_metadata)
                metadata['check_method'] = 'http'

            else:
                error_message = f"不支持的检查方法: {check_method}"

        except Exception as e:
            error_message = f"EMQX健康检查异常: {e}"

        response_time = time.time() - start_time

        return HealthCheckResult(
            service_name=self.name,
            service_type='emqx',
            is_healthy=is_healthy,
            response_time=response_time,
            error_message=error_message,
            metadata=metadata
        )

    async def close(self):
        """关闭EMQX连接（无需特殊处理）"""
        pass
