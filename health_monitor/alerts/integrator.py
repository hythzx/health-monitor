"""告警系统集成器

负责连接状态管理器和告警管理器，实现状态变化事件的告警触发
"""

import logging
from typing import Dict, List, Any, Callable

from .http_alerter import HTTPAlerter
from .manager import AlertManager
from ..models.health_check import HealthCheckResult, StateChange
from ..services.state_manager import StateManager
from ..utils.exceptions import AlertConfigError


class AlertIntegrator:
    """告警系统集成器
    
    负责将状态管理器的状态变化事件转换为告警通知
    """

    def __init__(self, state_manager: StateManager, alert_configs: List[Dict[str, Any]]):
        """初始化告警集成器
        
        Args:
            state_manager: 状态管理器实例
            alert_configs: 告警配置列表
        """
        self.state_manager = state_manager
        self.alert_manager = AlertManager(alert_configs)
        self.logger = logging.getLogger(__name__)

        # 告警过滤器和回调
        self.alert_filters: List[Callable[[StateChange], bool]] = []
        self.pre_alert_callbacks: List[Callable[[StateChange], None]] = []
        self.post_alert_callbacks: List[Callable[[StateChange, bool], None]] = []

        # 初始化告警器
        self._initialize_alerters(alert_configs)

    def _initialize_alerters(self, alert_configs: List[Dict[str, Any]]):
        """初始化告警器
        
        Args:
            alert_configs: 告警配置列表
        """
        for config in alert_configs:
            try:
                alerter_type = config.get('type', '').lower()
                alerter_name = config.get('name',
                                          f'alerter_{len(self.alert_manager.alerters)}')

                if alerter_type == 'http':
                    alerter = HTTPAlerter(alerter_name, config)
                    self.alert_manager.add_alerter(alerter)
                    self.logger.info(f"已初始化HTTP告警器: {alerter_name}")
                else:
                    self.logger.warning(f"不支持的告警器类型: {alerter_type}")

            except Exception as e:
                self.logger.error(
                    f"初始化告警器失败 {config.get('name', 'unknown')}: {e}")

    async def process_health_check_result(self, result: HealthCheckResult):
        """处理健康检查结果
        
        Args:
            result: 健康检查结果
        """
        # 更新状态并获取状态变化事件
        state_change = self.state_manager.update_state(result)

        # 如果有状态变化，触发告警
        if state_change:
            await self.trigger_alert(state_change)

    async def trigger_alert(self, state_change: StateChange):
        """触发告警
        
        Args:
            state_change: 状态变化事件
        """
        try:
            # 应用告警过滤器
            if not self._should_alert(state_change):
                self.logger.debug(f"告警被过滤器阻止: {state_change.service_name}")
                return

            # 执行预告警回调
            for callback in self.pre_alert_callbacks:
                try:
                    callback(state_change)
                except Exception as e:
                    self.logger.error(f"预告警回调执行失败: {e}")

            # 发送告警
            await self.alert_manager.send_alert(state_change)

            # 执行后告警回调
            for callback in self.post_alert_callbacks:
                try:
                    callback(state_change, True)
                except Exception as e:
                    self.logger.error(f"后告警回调执行失败: {e}")

        except Exception as e:
            self.logger.error(f"触发告警失败: {e}")

            # 执行失败回调
            for callback in self.post_alert_callbacks:
                try:
                    callback(state_change, False)
                except Exception as e:
                    self.logger.error(f"失败回调执行失败: {e}")

    def _should_alert(self, state_change: StateChange) -> bool:
        """检查是否应该发送告警
        
        Args:
            state_change: 状态变化事件
            
        Returns:
            是否应该发送告警
        """
        for filter_func in self.alert_filters:
            try:
                if not filter_func(state_change):
                    return False
            except Exception as e:
                self.logger.error(f"告警过滤器执行失败: {e}")
                # 过滤器失败时默认允许告警
                continue

        return True

    def add_alert_filter(self, filter_func: Callable[[StateChange], bool]):
        """添加告警过滤器
        
        Args:
            filter_func: 过滤器函数，返回True表示允许告警，False表示阻止告警
        """
        self.alert_filters.append(filter_func)
        self.logger.info("已添加告警过滤器")

    def add_pre_alert_callback(self, callback: Callable[[StateChange], None]):
        """添加预告警回调
        
        Args:
            callback: 回调函数，在发送告警前执行
        """
        self.pre_alert_callbacks.append(callback)
        self.logger.info("已添加预告警回调")

    def add_post_alert_callback(self, callback: Callable[[StateChange, bool], None]):
        """添加后告警回调
        
        Args:
            callback: 回调函数，在发送告警后执行，参数为(state_change, success)
        """
        self.post_alert_callbacks.append(callback)
        self.logger.info("已添加后告警回调")

    def remove_alert_filter(self, filter_func: Callable[[StateChange], bool]) -> bool:
        """移除告警过滤器
        
        Args:
            filter_func: 要移除的过滤器函数
            
        Returns:
            是否成功移除
        """
        try:
            self.alert_filters.remove(filter_func)
            self.logger.info("已移除告警过滤器")
            return True
        except ValueError:
            return False

    def get_alert_stats(self) -> Dict[str, Any]:
        """获取告警统计信息
        
        Returns:
            告警统计信息
        """
        return {
            'alerter_count': self.alert_manager.get_alerter_count(),
            'alerter_names': self.alert_manager.get_alerter_names(),
            'filter_count': len(self.alert_filters),
            'pre_callback_count': len(self.pre_alert_callbacks),
            'post_callback_count': len(self.post_alert_callbacks),
            'state_changes_count': len(self.state_manager.state_changes)
        }

    def create_service_filter(self, allowed_services: List[str]) -> Callable[
        [StateChange], bool]:
        """创建服务过滤器
        
        Args:
            allowed_services: 允许告警的服务名称列表
            
        Returns:
            过滤器函数
        """

        def service_filter(state_change: StateChange) -> bool:
            return state_change.service_name in allowed_services

        return service_filter

    def create_status_filter(self, alert_on_down: bool = True,
                             alert_on_up: bool = True) -> Callable[[StateChange], bool]:
        """创建状态过滤器
        
        Args:
            alert_on_down: 是否在服务DOWN时告警
            alert_on_up: 是否在服务UP时告警
            
        Returns:
            过滤器函数
        """

        def status_filter(state_change: StateChange) -> bool:
            if not state_change.new_state and alert_on_down:
                return True  # 服务DOWN且允许DOWN告警
            if state_change.new_state and alert_on_up:
                return True  # 服务UP且允许UP告警
            return False

        return status_filter

    def create_time_filter(self, quiet_hours: List[tuple]) -> Callable[
        [StateChange], bool]:
        """创建时间过滤器
        
        Args:
            quiet_hours: 静默时间段列表，格式为[(start_hour, end_hour), ...]
            
        Returns:
            过滤器函数
        """

        def time_filter(state_change: StateChange) -> bool:
            current_hour = state_change.timestamp.hour

            for start_hour, end_hour in quiet_hours:
                if start_hour <= end_hour:
                    # 同一天内的时间段
                    if start_hour <= current_hour < end_hour:
                        return False
                else:
                    # 跨天的时间段
                    if current_hour >= start_hour or current_hour < end_hour:
                        return False

            return True

        return time_filter

    async def test_alert_system(self, service_name: str = "test-service") -> bool:
        """测试告警系统
        
        Args:
            service_name: 测试服务名称
            
        Returns:
            测试是否成功
        """
        try:
            # 创建测试状态变化事件
            test_state_change = StateChange(
                service_name=service_name,
                service_type="test",
                old_state=True,
                new_state=False,
                error_message="告警系统测试"
            )

            # 触发告警
            await self.trigger_alert(test_state_change)

            self.logger.info("告警系统测试完成")
            return True

        except Exception as e:
            self.logger.error(f"告警系统测试失败: {e}")
            return False

    def reload_alert_config(self, alert_configs: List[Dict[str, Any]]):
        """重新加载告警配置
        
        Args:
            alert_configs: 新的告警配置列表
        """
        try:
            # 清空现有告警器
            old_alerter_count = self.alert_manager.get_alerter_count()
            self.alert_manager.alerters.clear()

            # 重新初始化告警器
            self._initialize_alerters(alert_configs)

            new_alerter_count = self.alert_manager.get_alerter_count()
            self.logger.info(
                f"告警配置已重新加载: {old_alerter_count} -> {new_alerter_count} 个告警器"
            )

        except Exception as e:
            self.logger.error(f"重新加载告警配置失败: {e}")
            raise AlertConfigError(f"重新加载告警配置失败: {e}")

    def get_recent_alerts(self, hours: int = 24) -> List[StateChange]:
        """获取最近的告警记录
        
        Args:
            hours: 获取最近多少小时的记录
            
        Returns:
            最近的状态变化记录列表
        """
        from datetime import datetime, timedelta

        since = datetime.now() - timedelta(hours=hours)
        return self.state_manager.get_state_changes(since=since)
