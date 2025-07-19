"""告警管理器"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
from string import Template

from .base import BaseAlerter
from ..models.health_check import AlertMessage, StateChange
from ..utils.exceptions import AlertConfigError, AlertSendError


class AlertManager:
    """告警管理器，负责管理告警器和发送告警消息"""
    
    def __init__(self, alert_configs: List[Dict[str, Any]]):
        """
        初始化告警管理器
        
        Args:
            alert_configs: 告警配置列表
        """
        self.alert_configs = alert_configs
        self.alerters: List[BaseAlerter] = []
        self.logger = logging.getLogger(__name__)
        
        # 告警去重相关
        self._alert_history: Dict[str, datetime] = {}
        self._duplicate_threshold = timedelta(minutes=5)  # 5分钟内相同告警去重
        
        # 消息模板缓存
        self._template_cache: Dict[str, Template] = {}
        
    def add_alerter(self, alerter: BaseAlerter):
        """
        添加告警器
        
        Args:
            alerter: 告警器实例
        """
        if not isinstance(alerter, BaseAlerter):
            raise AlertConfigError(f"告警器必须继承自BaseAlerter: {type(alerter)}")
        
        self.alerters.append(alerter)
        self.logger.info(f"已添加告警器: {alerter.name} ({alerter.alerter_type})")
    
    def remove_alerter(self, name: str) -> bool:
        """
        移除告警器
        
        Args:
            name: 告警器名称
            
        Returns:
            bool: 是否成功移除
        """
        for i, alerter in enumerate(self.alerters):
            if alerter.name == name:
                removed_alerter = self.alerters.pop(i)
                self.logger.info(f"已移除告警器: {removed_alerter.name}")
                return True
        return False
    
    async def send_alert(self, state_change: StateChange):
        """
        发送告警通知
        
        Args:
            state_change: 状态变化事件
        """
        if not self.alerters:
            self.logger.warning("没有配置告警器，跳过告警发送")
            return
        
        # 创建告警消息
        alert_message = self._create_alert_message(state_change)
        
        # 检查是否需要去重
        if self._should_deduplicate(alert_message):
            self.logger.debug(f"告警去重，跳过发送: {alert_message.service_name}")
            return
        
        # 记录告警历史
        self._record_alert(alert_message)
        
        # 并发发送到所有告警器
        tasks = []
        for alerter in self.alerters:
            task = self._send_to_alerter(alerter, alert_message)
            tasks.append(task)
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            self._log_send_results(results, alert_message)
    
    async def _send_to_alerter(self, alerter: BaseAlerter, message: AlertMessage) -> Dict[str, Any]:
        """
        向单个告警器发送消息
        
        Args:
            alerter: 告警器实例
            message: 告警消息
            
        Returns:
            Dict[str, Any]: 发送结果
        """
        try:
            success = await alerter.send_alert(message)
            return {
                'alerter': alerter.name,
                'success': success,
                'error': None
            }
        except Exception as e:
            self.logger.error(f"告警器 {alerter.name} 发送失败: {e}")
            return {
                'alerter': alerter.name,
                'success': False,
                'error': str(e)
            }
    
    def _create_alert_message(self, state_change: StateChange) -> AlertMessage:
        """
        根据状态变化创建告警消息
        
        Args:
            state_change: 状态变化事件
            
        Returns:
            AlertMessage: 告警消息
        """
        # 确定告警状态
        if state_change.new_state:
            status = "UP"
        else:
            status = "DOWN"
        
        return AlertMessage(
            service_name=state_change.service_name,
            service_type=state_change.service_type,
            status=status,
            timestamp=state_change.timestamp,
            error_message=state_change.error_message,
            response_time=state_change.response_time,
            metadata={
                'old_state': state_change.old_state,
                'new_state': state_change.new_state
            }
        )
    
    def _should_deduplicate(self, message: AlertMessage) -> bool:
        """
        检查是否应该对告警进行去重
        
        Args:
            message: 告警消息
            
        Returns:
            bool: 是否应该去重
        """
        alert_key = f"{message.service_name}:{message.status}"
        
        if alert_key in self._alert_history:
            last_alert_time = self._alert_history[alert_key]
            time_diff = message.timestamp - last_alert_time
            
            if time_diff < self._duplicate_threshold:
                return True
        
        return False
    
    def _record_alert(self, message: AlertMessage):
        """
        记录告警历史
        
        Args:
            message: 告警消息
        """
        alert_key = f"{message.service_name}:{message.status}"
        self._alert_history[alert_key] = message.timestamp
        
        # 清理过期的告警历史
        self._cleanup_alert_history()
    
    def _cleanup_alert_history(self):
        """清理过期的告警历史记录"""
        current_time = datetime.now()
        expired_keys = []
        
        for key, timestamp in self._alert_history.items():
            if current_time - timestamp > self._duplicate_threshold * 2:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._alert_history[key]
    
    def _log_send_results(self, results: List[Any], message: AlertMessage):
        """
        记录发送结果
        
        Args:
            results: 发送结果列表
            message: 告警消息
        """
        success_count = 0
        failed_alerters = []
        
        for result in results:
            if isinstance(result, Exception):
                self.logger.error(f"告警发送异常: {result}")
                continue
            
            if result['success']:
                success_count += 1
            else:
                failed_alerters.append(result['alerter'])
        
        if success_count > 0:
            self.logger.info(
                f"告警发送成功 {success_count}/{len(self.alerters)} 个告警器 "
                f"(服务: {message.service_name}, 状态: {message.status})"
            )
        
        if failed_alerters:
            self.logger.warning(
                f"以下告警器发送失败: {', '.join(failed_alerters)} "
                f"(服务: {message.service_name})"
            )
    
    def render_template(self, template_str: str, message: AlertMessage) -> str:
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
            raise AlertConfigError(f"模板渲染失败: {e}")
    
    def get_alerter_count(self) -> int:
        """
        获取告警器数量
        
        Returns:
            int: 告警器数量
        """
        return len(self.alerters)
    
    def get_alerter_names(self) -> List[str]:
        """
        获取所有告警器名称
        
        Returns:
            List[str]: 告警器名称列表
        """
        return [alerter.name for alerter in self.alerters]
    
    def clear_alert_history(self):
        """清空告警历史记录"""
        self._alert_history.clear()
        self.logger.info("已清空告警历史记录")