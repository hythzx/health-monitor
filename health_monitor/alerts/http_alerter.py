"""HTTP告警器实现"""

import asyncio
import json
from typing import Dict, Any
from urllib.parse import urlparse

import aiohttp

from .base import BaseAlerter
from ..models.health_check import AlertMessage
from ..utils.exceptions import AlertConfigError, AlertSendError
from ..utils.log_manager import get_logger


class HTTPAlerter(BaseAlerter):
    """HTTP告警器，通过HTTP请求发送告警消息"""

    def __init__(self, name: str, config: Dict[str, Any]):
        """
        初始化HTTP告警器
        
        Args:
            name: 告警器名称
            config: 告警器配置
        """
        super().__init__(name, config)
        self.logger = get_logger(f'alerter.http.{self.name}')

        # 重试配置
        self.max_retries = config.get('max_retries', 3)
        self.retry_delay = config.get('retry_delay', 1.0)  # 秒
        self.retry_backoff = config.get('retry_backoff', 2.0)  # 指数退避倍数

        # HTTP配置
        self.url = config.get('url', '')
        self.method = config.get('method', 'POST').upper()
        self.headers = config.get('headers', {})
        self.template = config.get('template', '')

        # 验证配置
        if not self.validate_config():
            raise AlertConfigError(f"HTTP告警器配置无效: {name}")

    def validate_config(self) -> bool:
        """
        验证配置参数是否有效
        
        Returns:
            bool: 配置是否有效
        """
        # 检查必需参数
        if not self.url:
            self.logger.error(f"HTTP告警器 {self.name} 缺少URL配置")
            return False

        # 验证URL格式
        try:
            parsed_url = urlparse(self.url)
            if not parsed_url.scheme or not parsed_url.netloc:
                self.logger.error(f"HTTP告警器 {self.name} URL格式无效: {self.url}")
                return False
        except Exception as e:
            self.logger.error(f"HTTP告警器 {self.name} URL解析失败: {e}")
            return False

        # 验证HTTP方法
        valid_methods = ['GET', 'POST', 'PUT', 'PATCH']
        if self.method not in valid_methods:
            self.logger.error(
                f"HTTP告警器 {self.name} 不支持的HTTP方法: {self.method}, "
                f"支持的方法: {valid_methods}"
            )
            return False

        # 验证重试配置
        if self.max_retries < 0:
            self.logger.error(f"HTTP告警器 {self.name} 最大重试次数不能为负数")
            return False

        if self.retry_delay < 0:
            self.logger.error(f"HTTP告警器 {self.name} 重试延迟不能为负数")
            return False

        # 验证模板（如果提供）
        if self.template:
            try:
                # 简单的模板语法检查，确保包含必要的变量
                required_vars = ['{{service_name}}', '{{status}}']
                for var in required_vars:
                    if var not in self.template:
                        self.logger.warning(f"HTTP告警器 {self.name} 模板缺少变量: {var}")

                # 检查模板是否为空
                if not self.template.strip():
                    self.logger.error(f"HTTP告警器 {self.name} 模板不能为空")
                    return False

                self.logger.debug(f"HTTP告警器 {self.name} 模板验证通过")
            except Exception as e:
                self.logger.error(f"HTTP告警器 {self.name} 模板验证失败: {e}")
                return False

        return True

    async def send_alert(self, message: AlertMessage) -> bool:
        """
        发送告警消息
        
        Args:
            message: 告警消息对象
            
        Returns:
            bool: 发送是否成功
        """
        self.logger.info(
            f"开始发送告警消息: 服务={message.service_name}, 状态={message.status}")
        self.logger.debug(f"告警消息详情: {message}")

        for attempt in range(self.max_retries + 1):
            try:
                self.logger.debug(f"尝试发送告警 (第 {attempt + 1} 次)")
                success = await self._send_request(message)
                if success:
                    if attempt > 0:
                        self.logger.info(
                            f"HTTP告警器 {self.name} 重试第 {attempt} 次后发送成功"
                        )
                    else:
                        self.logger.info(f"HTTP告警器 {self.name} 首次尝试发送成功")
                    return True

            except Exception as e:
                self.logger.warning(
                    f"HTTP告警器 {self.name} 发送失败 (尝试 {attempt + 1}/{self.max_retries + 1}): {e}"
                )

                # 如果不是最后一次尝试，等待后重试
                if attempt < self.max_retries:
                    delay = self.retry_delay * (self.retry_backoff ** attempt)
                    self.logger.debug(f"等待 {delay:.2f} 秒后重试")
                    await asyncio.sleep(delay)
                else:
                    # 最后一次尝试失败
                    self.logger.error(
                        f"HTTP告警器 {self.name} 所有重试均失败，放弃发送告警"
                    )
                    raise AlertSendError(f"HTTP告警发送失败: {e}")

        return False

    async def _send_request(self, message: AlertMessage) -> bool:
        """
        发送HTTP请求
        
        Args:
            message: 告警消息
            
        Returns:
            bool: 请求是否成功
        """
        # 准备请求数据
        request_data = self._prepare_request_data(message)

        timeout = aiohttp.ClientTimeout(total=self.get_timeout())

        # SSL配置
        ssl_verify = self.config.get('ssl_verify', True)
        connector = None

        if not ssl_verify:
            self.logger.warning(f"HTTP告警器 {self.name} 已禁用SSL验证")
            connector = aiohttp.TCPConnector(ssl=False)
        else:
            # 可以在这里添加自定义SSL上下文配置
            connector = aiohttp.TCPConnector(ssl=True)

        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            try:
                print(self.url)
                print(request_data)
                async with session.request(
                        method=self.method,
                        url=self.url,
                        headers=self.headers,
                        **request_data
                ) as response:
                    # 检查响应状态
                    if response.status >= 200 and response.status < 300:
                        # 尝试解析响应体
                        try:
                            response_body = await response.json()
                            self.logger.debug(
                                f"HTTP告警器 {self.name} 发送成功 "
                                f"(状态码: {response.status}, 响应: {response_body})"
                            )

                            # 检查钉钉机器人的特殊响应格式
                            if isinstance(response_body,
                                          dict) and 'errcode' in response_body:
                                if response_body['errcode'] == 0:
                                    return True
                                else:
                                    self.logger.error(
                                        f"HTTP告警器 {self.name} 钉钉机器人返回错误: "
                                        f"errcode={response_body.get('errcode')}, "
                                        f"errmsg={response_body.get('errmsg')}"
                                    )
                                    return False

                            return True
                        except (json.JSONDecodeError, aiohttp.ContentTypeError):
                            # 如果响应不是JSON，只要状态码正确就认为成功
                            response_text = await response.text()
                            self.logger.debug(
                                f"HTTP告警器 {self.name} 发送成功 "
                                f"(状态码: {response.status}, 响应: {response_text[:200]})"
                            )
                            return True
                    else:
                        response_text = await response.text()
                        self.logger.warning(
                            f"HTTP告警器 {self.name} 收到错误响应 "
                            f"(状态码: {response.status}, 响应: {response_text[:200]})"
                        )
                        return False

            except aiohttp.ClientError as e:
                error_msg = str(e)
                if "SSL" in error_msg or "certificate" in error_msg.lower():
                    self.logger.error(
                        f"HTTP告警器 {self.name} SSL证书验证失败: {e}\n"
                        f"建议解决方案:\n"
                        f"1. 在配置中添加 'ssl_verify: false' 临时禁用SSL验证\n"
                        f"2. 更新系统的CA证书包\n"
                        f"3. 检查网络环境是否有SSL拦截"
                    )
                else:
                    self.logger.error(f"HTTP告警器 {self.name} 网络请求失败: {e}")
                raise AlertSendError(f"HTTP请求失败: {e}")

            except asyncio.TimeoutError:
                self.logger.error(f"HTTP告警器 {self.name} 请求超时")
                raise AlertSendError("HTTP请求超时")

    def _prepare_request_data(self, message: AlertMessage) -> Dict[str, Any]:
        """
        准备HTTP请求数据
        
        Args:
            message: 告警消息
            
        Returns:
            Dict[str, Any]: 请求参数
        """
        request_data = {}

        if self.method in ['POST', 'PUT', 'PATCH']:
            if self.template:
                # 使用模板渲染消息
                rendered_content = self._render_template(self.template, message)

                # 尝试解析为JSON
                try:
                    json_data = json.loads(rendered_content)
                    request_data['json'] = json_data
                    self.logger.debug(f"使用JSON模板发送数据: {json_data}")
                except json.JSONDecodeError as e:
                    # 如果不是JSON，作为文本发送
                    request_data['data'] = rendered_content
                    self.logger.debug(f"使用文本模板发送数据: {rendered_content}")
            else:
                # 默认JSON格式
                request_data['json'] = self._create_default_payload(message)
                self.logger.debug(f"使用默认JSON格式发送数据")

        elif self.method == 'GET':
            # GET请求使用查询参数
            request_data['params'] = self._create_query_params(message)

        return request_data

    def _render_template(self, template_str: str, message: AlertMessage) -> str:
        """
        渲染消息模板
        
        Args:
            template_str: 模板字符串
            message: 告警消息
            
        Returns:
            str: 渲染后的消息
        """
        # 准备模板变量
        template_vars = {
            'service_name': message.service_name,
            'service_type': message.service_type,
            'status': message.status,
            'timestamp': message.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'error_message': message.error_message or '无',
            'response_time': f"{message.response_time:.2f}" if message.response_time else '未知'
        }

        # 添加元数据变量
        if message.metadata:
            for key, value in message.metadata.items():
                template_vars[f'metadata_{key}'] = str(value)

        try:
            # 使用 {{variable}} 语法进行字符串替换
            rendered = template_str

            # 检测模板是否为JSON格式
            is_json_template = template_str.strip().startswith(
                '{') and template_str.strip().endswith('}')

            for key, value in template_vars.items():
                safe_value = str(value)
                if is_json_template:
                    # JSON模板需要转义特殊字符
                    safe_value = safe_value.replace('\\', '\\\\')  # 反斜杠
                    safe_value = safe_value.replace('"', '\\"')  # 双引号
                    safe_value = safe_value.replace('\n', '\\n')  # 换行符
                    safe_value = safe_value.replace('\r', '\\r')  # 回车符
                    safe_value = safe_value.replace('\t', '\\t')  # 制表符
                    safe_value = safe_value.replace('\b', '\\b')  # 退格符
                    safe_value = safe_value.replace('\f', '\\f')  # 换页符

                rendered = rendered.replace(f'{{{{{key}}}}}', safe_value)

            # 如果是JSON模板，验证生成的JSON是否有效
            if is_json_template:
                try:
                    json.loads(rendered)
                    self.logger.debug(f"JSON模板渲染并验证成功")
                except json.JSONDecodeError as e:
                    self.logger.error(f"渲染后的JSON格式无效: {e}")
                    self.logger.error(f"渲染内容: {repr(rendered[:200])}")
                    raise AlertSendError(f"渲染后的JSON格式无效: {e}")

            return rendered
        except AlertSendError:
            raise
        except Exception as e:
            self.logger.error(f"模板渲染失败: {e}")
            raise AlertSendError(f"模板渲染失败: {e}")

    def _create_default_payload(self, message: AlertMessage) -> Dict[str, Any]:
        """
        创建默认的JSON负载
        
        Args:
            message: 告警消息
            
        Returns:
            Dict[str, Any]: JSON负载
        """
        return {
            'service_name': message.service_name,
            'service_type': message.service_type,
            'status': message.status,
            'timestamp': message.timestamp.isoformat(),
            'error_message': message.error_message,
            'response_time': message.response_time,
            'metadata': message.metadata
        }

    def _create_query_params(self, message: AlertMessage) -> Dict[str, str]:
        """
        创建查询参数
        
        Args:
            message: 告警消息
            
        Returns:
            Dict[str, str]: 查询参数
        """
        params = {
            'service_name': message.service_name,
            'service_type': message.service_type,
            'status': message.status,
            'timestamp': message.timestamp.isoformat()
        }

        if message.error_message:
            params['error_message'] = message.error_message

        if message.response_time is not None:
            params['response_time'] = str(message.response_time)

        return params

    def get_config_summary(self) -> Dict[str, Any]:
        """
        获取配置摘要（用于调试和监控）
        
        Returns:
            Dict[str, Any]: 配置摘要
        """
        return {
            'name': self.name,
            'type': 'http',
            'url': self.url,
            'method': self.method,
            'timeout': self.get_timeout(),
            'max_retries': self.max_retries,
            'retry_delay': self.retry_delay,
            'has_template': bool(self.template),
            'headers_count': len(self.headers)
        }
