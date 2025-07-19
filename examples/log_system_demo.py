#!/usr/bin/env python3
"""
日志系统演示

展示如何使用健康监控系统的日志功能
"""

import asyncio
import tempfile
import os
from datetime import datetime

# 导入日志管理器和相关组件
from health_monitor.utils.log_manager import configure_logging, get_logger
from health_monitor.checkers.redis_checker import RedisHealthChecker
from health_monitor.alerts.http_alerter import HTTPAlerter
from health_monitor.services.config_manager import ConfigManager
from health_monitor.models.health_check import AlertMessage


async def main():
    """主演示函数"""
    
    # 创建临时日志文件
    temp_dir = tempfile.mkdtemp()
    log_file = os.path.join(temp_dir, 'health_monitor.log')
    
    print(f"日志文件位置: {log_file}")
    
    # 配置日志系统
    configure_logging({
        'log_level': 'INFO',
        'log_file': log_file,
        'enable_console': True,
        'enable_file': True,
        'max_file_size': 1024 * 1024,  # 1MB
        'backup_count': 3
    })
    
    print("=== 日志系统演示 ===\n")
    
    # 1. 演示基本日志记录
    print("1. 基本日志记录演示")
    logger = get_logger('demo')
    logger.info("这是一条信息日志")
    logger.warning("这是一条警告日志")
    logger.error("这是一条错误日志")
    logger.debug("这是一条调试日志（可能不会显示，取决于日志级别）")
    
    # 2. 演示健康检查器的日志记录
    print("\n2. 健康检查器日志演示")
    redis_config = {
        'host': 'localhost',
        'port': 6379,
        'timeout': 5
    }
    
    redis_checker = RedisHealthChecker('demo-redis', redis_config)
    redis_checker.logger.info("Redis检查器已创建")
    redis_checker.logger.debug(f"Redis配置: {redis_config}")
    
    # 注意：这里不会真正连接Redis，只是演示日志记录
    redis_checker.logger.warning("演示模式：跳过实际的Redis连接测试")
    
    # 3. 演示告警器的日志记录
    print("\n3. 告警器日志演示")
    alerter_config = {
        'url': 'https://example.com/webhook',
        'method': 'POST',
        'timeout': 10
    }
    
    try:
        http_alerter = HTTPAlerter('demo-alerter', alerter_config)
        http_alerter.logger.info("HTTP告警器已创建")
        http_alerter.logger.debug(f"告警器配置: {alerter_config}")
        
        # 创建示例告警消息
        alert_message = AlertMessage(
            service_name='demo-service',
            service_type='redis',
            status='DOWN',
            timestamp=datetime.now(),
            error_message='演示错误消息',
            response_time=1.5
        )
        
        http_alerter.logger.info(f"准备发送告警: {alert_message.service_name} - {alert_message.status}")
        # 注意：这里不会真正发送HTTP请求
        http_alerter.logger.warning("演示模式：跳过实际的HTTP请求发送")
        
    except Exception as e:
        logger.error(f"创建告警器时出错: {e}")
    
    # 4. 演示配置管理器的日志记录
    print("\n4. 配置管理器日志演示")
    
    # 创建临时配置文件
    config_file = os.path.join(temp_dir, 'demo_config.yaml')
    config_content = """
global:
  log_level: INFO
  check_interval: 30

services:
  demo-redis:
    type: redis
    host: localhost
    port: 6379
    timeout: 5

alerts:
  - name: demo-webhook
    type: http
    url: https://example.com/webhook
    method: POST
"""
    
    with open(config_file, 'w', encoding='utf-8') as f:
        f.write(config_content)
    
    config_manager = ConfigManager(config_file)
    config_manager.logger.info("配置管理器已创建")
    
    try:
        config = config_manager.load_config()
        config_manager.logger.info("配置加载成功")
        
        services_count = len(config.get('services', {}))
        alerts_count = len(config.get('alerts', []))
        config_manager.logger.info(f"配置包含 {services_count} 个服务和 {alerts_count} 个告警")
        
    except Exception as e:
        config_manager.logger.error(f"配置加载失败: {e}")
    
    # 5. 演示不同日志级别
    print("\n5. 不同日志级别演示")
    demo_logger = get_logger('level_demo')
    
    demo_logger.debug("调试信息：详细的执行步骤")
    demo_logger.info("信息：正常的操作状态")
    demo_logger.warning("警告：可能的问题，但不影响运行")
    demo_logger.error("错误：发生了错误，需要注意")
    demo_logger.critical("严重：系统可能无法继续运行")
    
    # 6. 演示异常日志记录
    print("\n6. 异常日志记录演示")
    exception_logger = get_logger('exception_demo')
    
    try:
        # 故意引发异常
        result = 1 / 0
    except ZeroDivisionError as e:
        exception_logger.error("捕获到除零异常", exc_info=True)
    
    # 强制刷新所有日志处理器
    from health_monitor.utils.log_manager import log_manager
    for logger_name, logger_instance in log_manager._loggers.items():
        for handler in logger_instance.handlers:
            handler.flush()
    
    print(f"\n=== 演示完成 ===")
    print(f"请查看日志文件: {log_file}")
    print("日志文件内容:")
    print("-" * 50)
    
    # 显示日志文件内容
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            print(f.read())
    else:
        print("日志文件未创建")
    
    # 清理临时文件
    try:
        if os.path.exists(config_file):
            os.remove(config_file)
        if os.path.exists(log_file):
            os.remove(log_file)
        os.rmdir(temp_dir)
        print(f"\n临时文件已清理")
    except Exception as e:
        print(f"清理临时文件时出错: {e}")


if __name__ == '__main__':
    asyncio.run(main())