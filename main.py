#!/usr/bin/env python3
"""
健康监控系统主应用程序入口

集成所有组件，实现应用程序启动和优雅关闭，
添加信号处理和异常捕获。
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Optional, Dict, Any

from health_monitor.alerts.integrator import AlertIntegrator
from health_monitor.services.config_manager import ConfigManager
from health_monitor.services.config_watcher import ConfigWatcher
from health_monitor.services.monitor_scheduler import MonitorScheduler
from health_monitor.services.state_manager import StateManager
from health_monitor.utils.exceptions import HealthMonitorError, ConfigError
from health_monitor.utils.log_manager import log_manager, get_logger

# 版本信息
__version__ = "1.0.0"


class HealthMonitorApp:
    """健康监控系统主应用程序类"""

    def __init__(self, config_path: str):
        """初始化应用程序
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self.logger: Optional[logging.Logger] = None
        self.is_running = False
        self.shutdown_event = asyncio.Event()

        # 核心组件
        self.config_manager: Optional[ConfigManager] = None
        self.config_watcher: Optional[ConfigWatcher] = None
        self.state_manager: Optional[StateManager] = None
        self.monitor_scheduler: Optional[MonitorScheduler] = None
        self.alert_integrator: Optional[AlertIntegrator] = None

        # 任务管理
        self.background_tasks = set()

    async def initialize(self):
        """初始化应用程序组件"""
        try:
            # 初始化配置管理器
            self.config_manager = ConfigManager(self.config_path)
            config = self.config_manager.load_config()

            # 配置日志系统
            self._configure_logging(config.get('global', {}))
            self.logger = get_logger('main')
            self.logger.info("开始初始化健康监控系统")

            # 初始化状态管理器
            state_file = self._get_state_file_path(config.get('global', {}))
            self.state_manager = StateManager(state_file)

            # 初始化监控调度器
            max_concurrent = config.get('global', {}).get('max_concurrent_checks', 10)
            enable_performance_monitoring = config.get('global', {}).get(
                'enable_performance_monitoring', True)
            self.monitor_scheduler = MonitorScheduler(max_concurrent,
                                                      enable_performance_monitoring)

            # 配置监控服务
            services_config = self.config_manager.get_services_config()
            global_config = self.config_manager.get_global_config()
            self.monitor_scheduler.configure_services(services_config, global_config)

            # 初始化告警集成器
            alerts_config = self.config_manager.get_alerts_config()
            self.alert_integrator = AlertIntegrator(self.state_manager, alerts_config)

            # 设置监控调度器回调
            self.monitor_scheduler.set_check_result_callback(
                self.alert_integrator.process_health_check_result
            )
            self.monitor_scheduler.set_check_error_callback(
                self._handle_check_error
            )
            self.monitor_scheduler.set_performance_alert_callback(
                self._handle_performance_alert
            )

            # 初始化配置监控器
            self.config_watcher = ConfigWatcher(self.config_manager)
            self.config_watcher.add_change_callback(self._on_config_changed_callback)

            self.logger.info("应用程序组件初始化完成")

        except Exception as e:
            if self.logger:
                self.logger.error(f"应用程序初始化失败: {e}", exc_info=True)
            else:
                print(f"应用程序初始化失败: {e}", file=sys.stderr)
            raise

    def _configure_logging(self, global_config: Dict[str, Any]):
        """配置日志系统
        
        Args:
            global_config: 全局配置
        """
        log_config = {
            'log_level': global_config.get('log_level', 'INFO'),
            'enable_console': True,
            'enable_file': 'log_file' in global_config
        }

        if 'log_file' in global_config:
            log_config['log_file'] = global_config['log_file']
            log_config['max_file_size'] = global_config.get('max_log_size',
                                                            10 * 1024 * 1024)
            log_config['backup_count'] = global_config.get('log_backup_count', 5)

        log_manager.configure(log_config)

    def _get_state_file_path(self, global_config: Dict[str, Any]) -> Optional[str]:
        """获取状态文件路径
        
        Args:
            global_config: 全局配置
            
        Returns:
            状态文件路径，如果不需要持久化返回None
        """
        state_file = global_config.get('state_file')
        if state_file:
            # 确保状态文件目录存在
            Path(state_file).parent.mkdir(parents=True, exist_ok=True)
        return state_file

    async def _handle_check_error(self, service_name: str, error: Exception):
        """处理健康检查错误
        
        Args:
            service_name: 服务名称
            error: 错误信息
        """
        self.logger.error(f"服务 {service_name} 健康检查错误: {error}")

    async def _handle_performance_alert(self, metric_name: str, current_value: float,
                                        threshold: float):
        """处理性能告警
        
        Args:
            metric_name: 指标名称
            current_value: 当前值
            threshold: 阈值
        """
        self.logger.warning(
            f"性能告警: {metric_name} = {current_value:.1f} (阈值: {threshold:.1f})")

        # 可以在这里发送性能告警通知
        # 例如通过告警系统发送性能相关的告警

    def _on_config_changed_callback(self, old_config: Dict[str, Any],
                                    new_config: Dict[str, Any]):
        """配置文件变更回调"""
        try:
            self.logger.info("检测到配置文件变更，重新加载配置")

            # 重新配置日志系统
            self._configure_logging(new_config.get('global', {}))

            # 重新配置监控服务
            services_config = new_config.get('services', {})
            global_config = new_config.get('global', {})
            self.monitor_scheduler.configure_services(services_config, global_config)

            # 重新加载告警配置
            alerts_config = new_config.get('alerts', [])
            self.alert_integrator.reload_alert_config(alerts_config)

            self.logger.info("配置重新加载完成")

        except Exception as e:
            self.logger.error(f"重新加载配置失败: {e}", exc_info=True)

    async def start(self):
        """启动应用程序"""
        if self.is_running:
            self.logger.warning("应用程序已经在运行")
            return

        try:
            self.is_running = True
            self.logger.info("启动健康监控系统")

            # 启动配置监控器
            self.config_watcher.start_watching()

            # 启动异步配置监控任务
            config_watcher_task = asyncio.create_task(
                self.config_watcher.watch_config_changes_async()
            )
            self.background_tasks.add(config_watcher_task)
            config_watcher_task.add_done_callback(self.background_tasks.discard)

            # 启动监控调度器
            scheduler_task = asyncio.create_task(self.monitor_scheduler.start())
            self.background_tasks.add(scheduler_task)
            scheduler_task.add_done_callback(self.background_tasks.discard)

            self.logger.info("健康监控系统启动完成")

            # 等待关闭信号
            await self.shutdown_event.wait()

        except Exception as e:
            self.logger.error(f"应用程序运行异常: {e}", exc_info=True)
            raise
        finally:
            await self.stop()

    async def stop(self):
        """停止应用程序"""
        if not self.is_running:
            return

        self.logger.info("正在停止健康监控系统...")
        self.is_running = False

        try:
            # 停止监控调度器
            if self.monitor_scheduler:
                await self.monitor_scheduler.stop()

            # 停止配置监控器
            if self.config_watcher:
                self.config_watcher.stop_watching()

            # 取消所有后台任务
            for task in self.background_tasks:
                if not task.done():
                    task.cancel()

            # 等待所有任务完成
            if self.background_tasks:
                await asyncio.gather(*self.background_tasks, return_exceptions=True)

            self.background_tasks.clear()

            # 清理状态管理器
            if self.state_manager:
                self.state_manager.cleanup_history()

            # 清理日志管理器
            log_manager.cleanup()

            self.logger.info("健康监控系统已停止")

        except Exception as e:
            if self.logger:
                self.logger.error(f"停止应用程序时发生异常: {e}", exc_info=True)
            else:
                print(f"停止应用程序时发生异常: {e}", file=sys.stderr)

    def shutdown(self):
        """触发应用程序关闭"""
        if self.logger:
            self.logger.info("收到关闭信号")
        self.shutdown_event.set()

    def get_status(self) -> Dict[str, Any]:
        """获取应用程序状态
        
        Returns:
            应用程序状态信息
        """
        status = {
            'is_running': self.is_running,
            'config_path': self.config_path,
            'background_tasks_count': len(self.background_tasks)
        }

        if self.monitor_scheduler:
            status['scheduler_stats'] = self.monitor_scheduler.get_scheduler_stats()
            status['service_status'] = self.monitor_scheduler.get_service_status()

        if self.state_manager:
            status['current_states'] = self.state_manager.get_all_states()

        if self.alert_integrator:
            status['alert_stats'] = self.alert_integrator.get_alert_stats()

        # 添加性能监控信息
        if self.monitor_scheduler:
            performance_metrics = self.monitor_scheduler.get_performance_metrics(10)
            if performance_metrics:
                status['performance_metrics'] = performance_metrics

        return status


# 全局应用程序实例
app: Optional[HealthMonitorApp] = None


def signal_handler(signum, frame):
    """信号处理器"""
    signal_name = signal.Signals(signum).name
    print(f"\n收到信号 {signal_name} ({signum})")

    if app:
        app.shutdown()
    else:
        print("应用程序未初始化，直接退出")
        sys.exit(0)


def create_argument_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        prog='health-monitor',
        description='健康监控系统 - 监控多种服务的健康状态并发送告警通知',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  %(prog)s config.yaml                    # 使用指定配置文件启动监控
  %(prog)s --validate config.yaml        # 验证配置文件格式
  %(prog)s --test-alerts config.yaml     # 测试告警系统
  %(prog)s --version                      # 显示版本信息
  %(prog)s --help                         # 显示帮助信息

支持的服务类型:
  - Redis
  - MongoDB  
  - MySQL
  - EMQX (MQTT)
  - RESTful API

配置文件格式请参考 config/example.yaml
        """
    )

    # 位置参数：配置文件路径
    parser.add_argument(
        'config_file',
        nargs='?',
        help='YAML配置文件路径'
    )

    # 可选参数
    parser.add_argument(
        '--version', '-v',
        action='version',
        version=f'%(prog)s {__version__}'
    )

    parser.add_argument(
        '--validate',
        action='store_true',
        help='验证配置文件格式并退出'
    )

    parser.add_argument(
        '--test-alerts',
        action='store_true',
        help='测试告警系统并退出'
    )

    parser.add_argument(
        '--check-once',
        action='store_true',
        help='执行一次健康检查后退出'
    )

    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='设置日志级别（覆盖配置文件设置）'
    )

    parser.add_argument(
        '--log-file',
        help='日志文件路径（覆盖配置文件设置）'
    )

    parser.add_argument(
        '--daemon', '-d',
        action='store_true',
        help='以守护进程模式运行'
    )

    parser.add_argument(
        '--pid-file',
        help='PID文件路径（守护进程模式）'
    )

    return parser


def validate_config_file(config_path: str) -> bool:
    """验证配置文件
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        验证是否成功
    """
    try:
        print(f"正在验证配置文件: {config_path}")

        # 检查文件是否存在
        if not os.path.exists(config_path):
            print(f"❌ 配置文件不存在: {config_path}")
            return False

        # 尝试加载配置
        config_manager = ConfigManager(config_path)
        config = config_manager.load_config()

        # 验证配置内容
        services_count = len(config.get('services', {}))
        alerts_count = len(config.get('alerts', []))

        print(f"✅ 配置文件验证成功!")
        print(f"   - 服务数量: {services_count}")
        print(f"   - 告警配置数量: {alerts_count}")

        # 显示服务详情
        if services_count > 0:
            print("   - 配置的服务:")
            for service_name, service_config in config.get('services', {}).items():
                service_type = service_config.get('type', 'unknown')
                print(f"     * {service_name} ({service_type})")

        # 显示告警详情
        if alerts_count > 0:
            print("   - 配置的告警:")
            for alert_config in config.get('alerts', []):
                alert_name = alert_config.get('name', 'unnamed')
                alert_type = alert_config.get('type', 'unknown')
                print(f"     * {alert_name} ({alert_type})")

        return True

    except Exception as e:
        print(f"❌ 配置文件验证失败: {e}")
        return False


async def run_alert_test(config_path: str) -> bool:
    """测试告警系统
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        测试是否成功
    """
    try:
        print(f"正在测试告警系统: {config_path}")

        # 初始化应用程序组件
        app = HealthMonitorApp(config_path)
        await app.initialize()

        # 测试告警系统
        success = await app.alert_integrator.test_alert_system()

        if success:
            print("✅ 告警系统测试成功!")
        else:
            print("❌ 告警系统测试失败!")

        return success

    except Exception as e:
        print(f"❌ 告警系统测试失败: {e}")
        return False


async def check_once(config_path: str) -> bool:
    """执行一次健康检查
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        检查是否成功
    """
    try:
        print(f"正在执行健康检查: {config_path}")

        # 初始化应用程序组件
        app = HealthMonitorApp(config_path)
        await app.initialize()

        # 执行一次健康检查
        results = await app.monitor_scheduler.check_all_services_now()

        print(f"✅ 健康检查完成，共检查 {len(results)} 个服务:")

        all_healthy = True
        for service_name, result in results.items():
            if result is None:
                print(f"   ❌ {service_name}: 检查失败")
                all_healthy = False
            elif result.is_healthy:
                print(
                    f"   ✅ {service_name}: 健康 (响应时间: {result.response_time:.3f}s)")
            else:
                print(f"   ❌ {service_name}: 不健康 - {result.error_message}")
                all_healthy = False

        return all_healthy

    except Exception as e:
        print(f"❌ 健康检查失败: {e}")
        return False


def setup_daemon_mode(pid_file: Optional[str] = None):
    """设置守护进程模式
    
    Args:
        pid_file: PID文件路径
    """
    try:
        # 第一次fork
        pid = os.fork()
        if pid > 0:
            sys.exit(0)  # 父进程退出
    except OSError as e:
        print(f"第一次fork失败: {e}", file=sys.stderr)
        sys.exit(1)

    # 脱离父进程环境
    os.chdir("/")
    os.setsid()
    os.umask(0)

    try:
        # 第二次fork
        pid = os.fork()
        if pid > 0:
            sys.exit(0)  # 父进程退出
    except OSError as e:
        print(f"第二次fork失败: {e}", file=sys.stderr)
        sys.exit(1)

    # 重定向标准输入输出
    sys.stdout.flush()
    sys.stderr.flush()

    # 写入PID文件
    if pid_file:
        try:
            with open(pid_file, 'w') as f:
                f.write(str(os.getpid()))
        except Exception as e:
            print(f"写入PID文件失败: {e}", file=sys.stderr)


async def main():
    """主函数"""
    global app

    # 解析命令行参数
    parser = create_argument_parser()
    args = parser.parse_args()

    # 检查配置文件参数
    if not args.config_file:
        parser.print_help()
        sys.exit(1)

    config_path = args.config_file

    # 检查配置文件是否存在
    if not os.path.exists(config_path):
        print(f"配置文件不存在: {config_path}", file=sys.stderr)
        sys.exit(1)

    # 处理特殊模式
    if args.validate:
        success = validate_config_file(config_path)
        sys.exit(0 if success else 1)

    if args.test_alerts:
        success = await run_alert_test(config_path)
        sys.exit(0 if success else 1)

    if args.check_once:
        success = await check_once(config_path)
        sys.exit(0 if success else 1)

    # 守护进程模式
    if args.daemon:
        setup_daemon_mode(args.pid_file)

    try:
        # 创建应用程序实例
        app = HealthMonitorApp(config_path)

        # 应用命令行参数覆盖
        if args.log_level or args.log_file:
            # 预先加载配置以应用命令行参数
            config_manager = ConfigManager(config_path)
            config = config_manager.load_config()

            # 覆盖日志配置
            global_config = config.get('global', {})
            if args.log_level:
                global_config['log_level'] = args.log_level
            if args.log_file:
                global_config['log_file'] = args.log_file

            # 重新配置日志
            app._configure_logging(global_config)

        # 注册信号处理器
        signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
        signal.signal(signal.SIGTERM, signal_handler)  # 终止信号

        # 初始化并启动应用程序
        await app.initialize()

        # 显示启动信息
        if not args.daemon:
            print(f"健康监控系统 v{__version__} 已启动")
            print(f"配置文件: {config_path}")
            print("按 Ctrl+C 停止程序")

        await app.start()

    except KeyboardInterrupt:
        if not args.daemon:
            print("\n用户中断程序")
    except ConfigError as e:
        print(f"配置错误: {e}", file=sys.stderr)
        sys.exit(1)
    except HealthMonitorError as e:
        print(f"健康监控系统错误: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"未预期的错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if app:
            await app.stop()

        # 清理PID文件
        if args.daemon and args.pid_file and os.path.exists(args.pid_file):
            try:
                os.unlink(args.pid_file)
            except Exception:
                pass


if __name__ == "__main__":
    # 设置事件循环策略（Windows兼容性）
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    # 运行主程序
    asyncio.run(main())
