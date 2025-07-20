"""邮件告警器实现"""

import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from typing import Dict, Any, List
import aiosmtplib

from .base import BaseAlerter
from ..models.health_check import AlertMessage
from ..utils.exceptions import AlertConfigError, AlertSendError
from ..utils.log_manager import get_logger


class EmailAlerter(BaseAlerter):
    """邮件告警器，通过SMTP协议发送邮件告警"""

    def __init__(self, name: str, config: Dict[str, Any]):
        """
        初始化邮件告警器
        
        Args:
            name: 告警器名称
            config: 告警器配置
        """
        super().__init__(name, config)
        self.logger = get_logger(f'alerter.email.{self.name}')

        # SMTP配置
        self.smtp_server = config.get('smtp_server', '')
        self.smtp_port = config.get('smtp_port', 587)
        self.username = config.get('username', '')
        self.password = config.get('password', '')
        self.use_tls = config.get('use_tls', True)
        self.use_ssl = config.get('use_ssl', False)

        # 邮件配置
        self.from_email = config.get('from_email', self.username)
        self.from_name = config.get('from_name', '服务健康监控系统')
        self.to_emails = config.get('to_emails', [])
        self.cc_emails = config.get('cc_emails', [])
        self.bcc_emails = config.get('bcc_emails', [])

        # 模板配置
        self.subject_template = config.get('subject_template', '🚨 服务告警: {{service_name}} - {{status}}')
        self.body_template = config.get('body_template', self._get_default_body_template())

        # 重试配置
        self.max_retries = config.get('max_retries', 3)
        self.retry_delay = config.get('retry_delay', 2.0)

        # 验证配置
        if not self.validate_config():
            raise AlertConfigError(f"邮件告警器配置无效: {name}")

    def validate_config(self) -> bool:
        """
        验证配置参数是否有效
        
        Returns:
            bool: 配置是否有效
        """
        # 检查必需参数
        if not self.smtp_server:
            self.logger.error(f"邮件告警器 {self.name} 缺少SMTP服务器配置")
            return False

        if not self.username:
            self.logger.error(f"邮件告警器 {self.name} 缺少用户名配置")
            return False

        if not self.password:
            self.logger.error(f"邮件告警器 {self.name} 缺少密码配置")
            return False

        if not self.from_email:
            self.logger.error(f"邮件告警器 {self.name} 缺少发件人邮箱配置")
            return False

        if not self.to_emails:
            self.logger.error(f"邮件告警器 {self.name} 缺少收件人邮箱配置")
            return False

        # 验证邮箱格式
        all_emails = self.to_emails + self.cc_emails + self.bcc_emails + [self.from_email]
        for email in all_emails:
            if not self._is_valid_email(email):
                self.logger.error(f"邮件告警器 {self.name} 邮箱格式无效: {email}")
                return False

        # 验证端口
        if not isinstance(self.smtp_port, int) or self.smtp_port <= 0:
            self.logger.error(f"邮件告警器 {self.name} SMTP端口无效: {self.smtp_port}")
            return False

        # 验证SSL/TLS配置
        if self.use_ssl and self.use_tls:
            self.logger.error(f"邮件告警器 {self.name} 不能同时启用SSL和TLS")
            return False

        return True

    def _is_valid_email(self, email: str) -> bool:
        """
        验证邮箱格式
        
        Args:
            email: 邮箱地址
            
        Returns:
            bool: 邮箱格式是否有效
        """
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None

    async def send_alert(self, message: AlertMessage) -> bool:
        """
        发送告警邮件
        
        Args:
            message: 告警消息对象
            
        Returns:
            bool: 发送是否成功
        """
        self.logger.info(
            f"开始发送邮件告警: 服务={message.service_name}, 状态={message.status}")

        for attempt in range(self.max_retries + 1):
            try:
                self.logger.debug(f"尝试发送邮件 (第 {attempt + 1} 次)")
                success = await self._send_email(message)
                if success:
                    if attempt > 0:
                        self.logger.info(
                            f"邮件告警器 {self.name} 重试第 {attempt} 次后发送成功"
                        )
                    else:
                        self.logger.info(f"邮件告警器 {self.name} 首次尝试发送成功")
                    return True

            except Exception as e:
                self.logger.warning(
                    f"邮件告警器 {self.name} 发送失败 (尝试 {attempt + 1}/{self.max_retries + 1}): {e}"
                )

                # 如果不是最后一次尝试，等待后重试
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)  # 指数退避
                    self.logger.debug(f"等待 {delay:.2f} 秒后重试")
                    await asyncio.sleep(delay)
                else:
                    # 最后一次尝试失败
                    self.logger.error(
                        f"邮件告警器 {self.name} 所有重试均失败，放弃发送告警"
                    )
                    raise AlertSendError(f"邮件告警发送失败: {e}")

        return False

    async def _send_email(self, message: AlertMessage) -> bool:
        """
        发送邮件
        
        Args:
            message: 告警消息
            
        Returns:
            bool: 发送是否成功
        """
        # 创建邮件消息
        email_msg = self._create_email_message(message)

        # 配置SMTP连接
        smtp_kwargs = {
            'hostname': self.smtp_server,
            'port': self.smtp_port,
            'timeout': self.get_timeout()
        }

        if self.use_ssl:
            smtp_kwargs['use_tls'] = False
            smtp_kwargs['start_tls'] = False
        elif self.use_tls:
            smtp_kwargs['use_tls'] = True
            smtp_kwargs['start_tls'] = True

        try:
            # 使用aiosmtplib发送邮件
            await aiosmtplib.send(
                email_msg,
                username=self.username,
                password=self.password,
                **smtp_kwargs
            )

            self.logger.info(
                f"邮件告警发送成功: {self.from_email} -> {', '.join(self.to_emails)}"
            )
            return True

        except Exception as e:
            self.logger.error(f"SMTP发送失败: {e}")
            raise AlertSendError(f"SMTP发送失败: {e}")

    def _create_email_message(self, message: AlertMessage) -> MIMEMultipart:
        """
        创建邮件消息
        
        Args:
            message: 告警消息
            
        Returns:
            MIMEMultipart: 邮件消息对象
        """
        # 渲染主题和正文
        subject = self._render_template(self.subject_template, message)
        body = self._render_template(self.body_template, message)

        # 创建邮件消息
        email_msg = MIMEMultipart()
        email_msg['From'] = formataddr((self.from_name, self.from_email))
        email_msg['To'] = ', '.join(self.to_emails)
        
        if self.cc_emails:
            email_msg['Cc'] = ', '.join(self.cc_emails)
            
        email_msg['Subject'] = subject

        # 添加邮件正文
        email_msg.attach(MIMEText(body, 'plain', 'utf-8'))

        return email_msg

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
            for key, value in template_vars.items():
                rendered = rendered.replace(f'{{{{{key}}}}}', str(value))

            return rendered
        except Exception as e:
            self.logger.error(f"模板渲染失败: {e}")
            raise AlertSendError(f"模板渲染失败: {e}")

    def _get_default_body_template(self) -> str:
        """
        获取默认的邮件正文模板
        
        Returns:
            str: 默认模板
        """
        return """服务健康监控告警通知

服务名称: {{service_name}}
服务类型: {{service_type}}
当前状态: {{status}}
发生时间: {{timestamp}}
响应时间: {{response_time}}ms
错误信息: {{error_message}}

请及时处理相关问题！

---
此邮件由服务健康监控系统自动发送，请勿回复。
"""

    def get_config_summary(self) -> Dict[str, Any]:
        """
        获取配置摘要（用于调试和监控）
        
        Returns:
            Dict[str, Any]: 配置摘要
        """
        return {
            'name': self.name,
            'type': 'email',
            'smtp_server': self.smtp_server,
            'smtp_port': self.smtp_port,
            'from_email': self.from_email,
            'to_emails_count': len(self.to_emails),
            'cc_emails_count': len(self.cc_emails),
            'bcc_emails_count': len(self.bcc_emails),
            'use_tls': self.use_tls,
            'use_ssl': self.use_ssl,
            'timeout': self.get_timeout(),
            'max_retries': self.max_retries
        }