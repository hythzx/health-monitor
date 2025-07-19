"""状态管理器模块

负责管理服务状态、状态历史记录和状态变化检测
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from ..models.health_check import HealthCheckResult, StateChange


class StateManager:
    """状态管理器
    
    管理服务状态和状态历史，检测状态变化并生成StateChange事件
    """

    def __init__(self, persistence_file: Optional[str] = None):
        """初始化状态管理器
        
        Args:
            persistence_file: 状态持久化文件路径，如果为None则不持久化
        """
        self.current_states: Dict[str, bool] = {}  # 当前服务状态
        self.state_history: List[HealthCheckResult] = []  # 状态历史记录
        self.state_changes: List[StateChange] = []  # 状态变化事件
        self.persistence_file = persistence_file
        self.logger = logging.getLogger(__name__)

        # 加载持久化状态
        if self.persistence_file:
            self._load_state()

    def update_state(self, result: HealthCheckResult) -> Optional[StateChange]:
        """更新服务状态
        
        Args:
            result: 健康检查结果
            
        Returns:
            如果状态发生变化，返回StateChange事件，否则返回None
        """
        service_name = result.service_name
        new_state = result.is_healthy
        old_state = self.current_states.get(service_name)

        # 添加到历史记录
        self.state_history.append(result)

        # 检查状态是否发生变化
        state_change = None
        if old_state is None:
            # 首次检查
            self.current_states[service_name] = new_state
            self.logger.info(
                f"服务 {service_name} 初始状态: {'健康' if new_state else '不健康'}")
        elif old_state != new_state:
            # 状态发生变化
            self.current_states[service_name] = new_state
            state_change = StateChange(
                service_name=service_name,
                service_type=result.service_type,
                old_state=old_state,
                new_state=new_state,
                timestamp=result.timestamp,
                error_message=result.error_message,
                response_time=result.response_time
            )
            self.state_changes.append(state_change)

            status_text = "健康" if new_state else "不健康"
            old_status_text = "健康" if old_state else "不健康"
            self.logger.warning(
                f"服务 {service_name} 状态变化: {old_status_text} -> {status_text}"
            )
        else:
            # 状态未变化，更新当前状态（保持一致性）
            self.current_states[service_name] = new_state

        # 持久化状态
        if self.persistence_file:
            self._save_state()

        return state_change

    def get_current_state(self, service_name: str) -> Optional[bool]:
        """获取服务当前状态
        
        Args:
            service_name: 服务名称
            
        Returns:
            服务状态，True表示健康，False表示不健康，None表示未知
        """
        return self.current_states.get(service_name)

    def get_all_states(self) -> Dict[str, bool]:
        """获取所有服务的当前状态
        
        Returns:
            所有服务的状态字典
        """
        return self.current_states.copy()

    def get_state_changes(self, since: Optional[datetime] = None) -> List[StateChange]:
        """获取状态变化事件
        
        Args:
            since: 获取此时间之后的状态变化，如果为None则获取所有
            
        Returns:
            状态变化事件列表
        """
        if since is None:
            return self.state_changes.copy()

        return [
            change for change in self.state_changes
            if change.timestamp >= since
        ]

    def get_history(self, service_name: Optional[str] = None,
                    since: Optional[datetime] = None,
                    limit: Optional[int] = None) -> List[HealthCheckResult]:
        """获取状态历史记录
        
        Args:
            service_name: 服务名称，如果为None则获取所有服务
            since: 获取此时间之后的记录，如果为None则获取所有
            limit: 限制返回记录数量
            
        Returns:
            历史记录列表
        """
        history = self.state_history

        # 按服务名称过滤
        if service_name:
            history = [h for h in history if h.service_name == service_name]

        # 按时间过滤
        if since:
            history = [h for h in history if h.timestamp >= since]

        # 按时间倒序排序
        history = sorted(history, key=lambda x: x.timestamp, reverse=True)

        # 限制数量
        if limit:
            history = history[:limit]

        return history

    def is_state_changed(self, service_name: str) -> bool:
        """检查服务状态是否发生过变化
        
        Args:
            service_name: 服务名称
            
        Returns:
            如果服务状态发生过变化返回True，否则返回False
        """
        return any(
            change.service_name == service_name
            for change in self.state_changes
        )

    def clear_state_changes(self):
        """清空状态变化事件列表"""
        self.state_changes.clear()
        self.logger.debug("已清空状态变化事件列表")

    def cleanup_history(self, keep_days: int = 7):
        """清理历史记录
        
        Args:
            keep_days: 保留天数，默认7天
        """
        cutoff_time = datetime.now() - timedelta(days=keep_days)
        original_count = len(self.state_history)

        self.state_history = [
            h for h in self.state_history
            if h.timestamp >= cutoff_time
        ]

        # 同样清理状态变化记录
        self.state_changes = [
            c for c in self.state_changes
            if c.timestamp >= cutoff_time
        ]

        cleaned_count = original_count - len(self.state_history)
        if cleaned_count > 0:
            self.logger.info(f"清理了 {cleaned_count} 条历史记录")

    def _save_state(self):
        """保存状态到文件"""
        if not self.persistence_file:
            return

        try:
            # 确保目录存在
            Path(self.persistence_file).parent.mkdir(parents=True, exist_ok=True)

            state_data = {
                'current_states': self.current_states,
                'last_updated': datetime.now().isoformat(),
                'state_changes': [
                    {
                        'service_name': change.service_name,
                        'service_type': change.service_type,
                        'old_state': change.old_state,
                        'new_state': change.new_state,
                        'timestamp': change.timestamp.isoformat(),
                        'error_message': change.error_message,
                        'response_time': change.response_time
                    }
                    for change in self.state_changes[-100:]  # 只保存最近100个变化
                ]
            }

            with open(self.persistence_file, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            self.logger.error(f"保存状态失败: {e}")

    def _load_state(self):
        """从文件加载状态"""
        if not self.persistence_file or not os.path.exists(self.persistence_file):
            return

        try:
            with open(self.persistence_file, 'r', encoding='utf-8') as f:
                state_data = json.load(f)

            # 加载当前状态
            self.current_states = state_data.get('current_states', {})

            # 加载状态变化记录
            state_changes_data = state_data.get('state_changes', [])
            self.state_changes = []

            for change_data in state_changes_data:
                state_change = StateChange(
                    service_name=change_data['service_name'],
                    service_type=change_data['service_type'],
                    old_state=change_data['old_state'],
                    new_state=change_data['new_state'],
                    timestamp=datetime.fromisoformat(change_data['timestamp']),
                    error_message=change_data.get('error_message'),
                    response_time=change_data.get('response_time')
                )
                self.state_changes.append(state_change)

            self.logger.info(f"从 {self.persistence_file} 加载了状态数据")

        except Exception as e:
            self.logger.error(f"加载状态失败: {e}")

    def get_service_stats(self, service_name: str) -> Dict[str, Any]:
        """获取服务统计信息
        
        Args:
            service_name: 服务名称
            
        Returns:
            服务统计信息字典
        """
        service_history = [
            h for h in self.state_history
            if h.service_name == service_name
        ]

        if not service_history:
            return {}

        # 计算统计信息
        total_checks = len(service_history)
        healthy_checks = sum(1 for h in service_history if h.is_healthy)
        unhealthy_checks = total_checks - healthy_checks

        response_times = [h.response_time for h in service_history if
                          h.response_time is not None]
        avg_response_time = sum(response_times) / len(
            response_times) if response_times else 0

        # 最近的检查结果
        latest_check = max(service_history, key=lambda x: x.timestamp)

        return {
            'service_name': service_name,
            'current_state': self.current_states.get(service_name),
            'total_checks': total_checks,
            'healthy_checks': healthy_checks,
            'unhealthy_checks': unhealthy_checks,
            'health_rate': healthy_checks / total_checks if total_checks > 0 else 0,
            'avg_response_time': avg_response_time,
            'latest_check': latest_check,
            'state_changes_count': len([
                c for c in self.state_changes
                if c.service_name == service_name
            ])
        }
