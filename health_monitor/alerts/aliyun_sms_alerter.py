"""阿里云短信告警器实现"""

import asyncio
import json
from typing import Dict, Any, List
from alibabacloud_dysmsapi20170525.client import Client as DysmsapiClient
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_dysmsapi20170525 import models as dysmsapi_models
from alibabacloud_tea_util import models as util_models

from .base import BaseAlerter
from ..models.health_check import AlertMessage
from ..utils.exceptions import AlertConfigError, AlertSendError
from ..utils.log_manager import get_logger


class AliyunSMSAlerter(BaseAlerter):
    """阿里云短信告警器，通过阿里云短信服务发送告警短信"""

    def __init__(self, name: str, config: Dict[str, Any]):
        """
        初始化阿里云短信告警器
        
        Args:
            name: 告警器名称
            config: 告警器配置
        """
        super().__init__(name, config)
        self.logger = get_logger(f'alerter.aliyun_sms.{self.name}')

        # 阿里云配置
        self.access_key_id = config.get('access_key_id', '')
        self.access_key_secret = config.get('access_key_secret', '')
        self.region = config.get('region', 'cn-hangzhou')
        self.endpoint = config.get('endpoint', f'dysmsapi.{self.region}.aliyuncs.com')

        # 短信配置
        self.sign_name = config.get('sign_name', '')
        self.template_code = config.get('template_code', '')
        self.phone_numbers = config.get('phone_numbers', [])
        self.template_params = config.get('template_params', {})

        # 重试配置
        self.max_retries = config.get('max_retries', 3)
        self.retry_delay = config.get('retry_delay', 1.0)

        # 批量发送配置
        self.batch_size = config.get('batch_size', 100)  # 阿里云单次最多支持1000个号码

        # 初始化客户端
        self.client = None
        self._init_client()

        # 验证配置
        if not self.validate_config():
            raise AlertConfigError(f"阿里云短信告警器配置无效: {name}")

    def _init_client(self):
        """初始化阿里云短信客户端"""
        try:
            config = open_api_models.Config(
                access_key_id=self.access_key_id,
                access_key_secret=self.access_key_secret
            )
            config.endpoint = self.endpoint
            self.client = DysmsapiClient(config)
            self.logger.debug(f"阿里云短信客户端初始化成功: {self.endpoint}")
        except Exception as e:
            self.logger.error(f"阿里云短信客户端初始化失败: {e}")
            raise AlertConfigError(f"阿里云短信客户端初始化失败: {e}")

    def validate_config(self) -> bool:
        """
        验证配置参数是否有效
        
        Returns:
            bool: 配置是否有效
        """
        # 检查必需参数
        if not self.access_key_id:
            self.logger.error(f"阿里云短信告警器 {self.name} 缺少access_key_id配置")
            return False

        if not self.access_key_secret:
            self.logger.error(f"阿里云短信告警器 {self.name} 缺少access_key_secret配置")
            return False

        if not self.sign_name:
            self.logger.error(f"阿里云短信告警器 {self.name} 缺少sign_name配置")
            return False

        if not self.template_code:
            self.logger.error(f"阿里云短信告警器 {self.name} 缺少template_code配置")
            return False

        if not self.phone_numbers:
            self.logger.error(f"阿里云短信告警器 {self.name} 缺少phone_numbers配置")
            return False

        # 验证手机号格式
        for phone in self.phone_numbers:
            if not self._is_valid_phone(phone):
                self.logger.error(f"阿里云短信告警器 {self.name} 手机号格式无效: {phone}")
                return False

        # 验证区域
        valid_regions = [
            'cn-hangzhou', 'cn-shanghai', 'cn-qingdao', 'cn-beijing',
            'cn-zhangjiakou', 'cn-huhehaote', 'cn-shenzhen', 'cn-chengdu',
            'cn-hongkong', 'ap-southeast-1', 'ap-southeast-2', 'ap-southeast-3',
            'ap-southeast-5', 'ap-northeast-1', 'us-west-1', 'us-east-1',
            'eu-central-1', 'eu-west-1', 'ap-south-1'
        ]
        if self.region not in valid_regions:
            self.logger.warning(f"阿里云短信告警器 {self.name} 区域可能无效: {self.region}")

        # 验证批量大小
        if self.batch_size <= 0 or self.batch_size > 1000:
            self.logger.error(f"阿里云短信告警器 {self.name} 批量大小无效: {self.batch_size}")
            return False

        return True

    def _is_valid_phone(self, phone: str) -> bool:
        """
        验证手机号格式
        
        Args:
            phone: 手机号
            
        Returns:
            bool: 手机号格式是否有效
        """
        import re
        # 支持中国大陆手机号格式
        pattern = r'^1[3-9]\d{9}$'
        return re.match(pattern, phone) is not None

    async def send_alert(self, message: AlertMessage) -> bool:
        """
        发送告警短信
        
        Args:
            message: 告警消息对象
            
        Returns:
            bool: 发送是否成功
        """
        self.logger.info(
            f"开始发送短信告警: 服务={message.service_name}, 状态={message.status}")

        for attempt in range(self.max_retries + 1):
            try:
                self.logger.debug(f"尝试发送短信 (第 {attempt + 1} 次)")
                success = await self._send_sms(message)
                if success:
                    if attempt > 0:
                        self.logger.info(
                            f"阿里云短信告警器 {self.name} 重试第 {attempt} 次后发送成功"
                        )
                    else:
                        self.logger.info(f"阿里云短信告警器 {self.name} 首次尝试发送成功")
                    return True

            except Exception as e:
                self.logger.warning(
                    f"阿里云短信告警器 {self.name} 发送失败 (尝试 {attempt + 1}/{self.max_retries + 1}): {e}"
                )

                # 如果不是最后一次尝试，等待后重试
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)  # 指数退避
                    self.logger.debug(f"等待 {delay:.2f} 秒后重试")
                    await asyncio.sleep(delay)
                else:
                    # 最后一次尝试失败
                    self.logger.error(
                        f"阿里云短信告警器 {self.name} 所有重试均失败，放弃发送告警"
                    )
                    raise AlertSendError(f"阿里云短信告警发送失败: {e}")

        return False

    async def _send_sms(self, message: AlertMessage) -> bool:
        """
        发送短信
        
        Args:
            message: 告警消息
            
        Returns:
            bool: 发送是否成功
        """
        # 准备模板参数
        template_params = self._prepare_template_params(message)

        # 分批发送短信
        success_count = 0
        total_batches = 0

        for i in range(0, len(self.phone_numbers), self.batch_size):
            batch_phones = self.phone_numbers[i:i + self.batch_size]
            total_batches += 1

            try:
                success = await self._send_batch_sms(batch_phones, template_params)
                if success:
                    success_count += 1
                    self.logger.debug(f"批次 {total_batches} 发送成功: {len(batch_phones)} 个号码")
                else:
                    self.logger.warning(f"批次 {total_batches} 发送失败: {len(batch_phones)} 个号码")

            except Exception as e:
                self.logger.error(f"批次 {total_batches} 发送异常: {e}")

        # 判断整体发送是否成功
        if success_count > 0:
            self.logger.info(
                f"短信告警发送完成: {success_count}/{total_batches} 个批次成功, "
                f"总计 {len(self.phone_numbers)} 个号码"
            )
            return True
        else:
            self.logger.error("所有批次短信发送均失败")
            raise AlertSendError("所有批次短信发送均失败")

    async def _send_batch_sms(self, phone_numbers: List[str], template_params: str) -> bool:
        """
        批量发送短信
        
        Args:
            phone_numbers: 手机号列表
            template_params: 模板参数JSON字符串
            
        Returns:
            bool: 发送是否成功
        """
        try:
            # 创建发送请求
            send_sms_request = dysmsapi_models.SendBatchSmsRequest(
                phone_number_json=json.dumps(phone_numbers),
                sign_name_json=json.dumps([self.sign_name] * len(phone_numbers)),
                template_code=self.template_code,
                template_param_json=json.dumps([template_params] * len(phone_numbers))
            )

            # 创建运行时配置
            runtime = util_models.RuntimeOptions()

            # 发送短信
            response = await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: self.client.send_batch_sms_with_options(send_sms_request, runtime)
            )

            # 检查响应
            if response.status_code == 200:
                body = response.body
                if body.code == 'OK':
                    self.logger.debug(f"短信发送成功: {body.message}")
                    return True
                else:
                    self.logger.error(f"短信发送失败: {body.code} - {body.message}")
                    return False
            else:
                self.logger.error(f"短信API调用失败: HTTP {response.status_code}")
                return False

        except Exception as e:
            self.logger.error(f"短信发送异常: {e}")
            raise AlertSendError(f"短信发送异常: {e}")

    def _prepare_template_params(self, message: AlertMessage) -> str:
        """
        准备短信模板参数
        
        Args:
            message: 告警消息
            
        Returns:
            str: 模板参数JSON字符串
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

        # 渲染模板参数
        rendered_params = {}
        for key, template_value in self.template_params.items():
            if isinstance(template_value, str):
                # 渲染模板字符串
                rendered_value = template_value
                for var_key, var_value in template_vars.items():
                    rendered_value = rendered_value.replace(f'{{{{{var_key}}}}}', str(var_value))
                rendered_params[key] = rendered_value
            else:
                # 直接使用非字符串值
                rendered_params[key] = template_value

        try:
            return json.dumps(rendered_params, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"模板参数序列化失败: {e}")
            raise AlertSendError(f"模板参数序列化失败: {e}")

    def get_config_summary(self) -> Dict[str, Any]:
        """
        获取配置摘要（用于调试和监控）
        
        Returns:
            Dict[str, Any]: 配置摘要
        """
        return {
            'name': self.name,
            'type': 'aliyun_sms',
            'region': self.region,
            'endpoint': self.endpoint,
            'sign_name': self.sign_name,
            'template_code': self.template_code,
            'phone_numbers_count': len(self.phone_numbers),
            'batch_size': self.batch_size,
            'timeout': self.get_timeout(),
            'max_retries': self.max_retries
        }