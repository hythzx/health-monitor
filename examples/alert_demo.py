#!/usr/bin/env python3
"""
告警系统演示脚本

展示如何使用HTTP、邮件和阿里云短信告警器
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from health_monitor.alerts.http_alerter import HTTPAlerter
from health_monitor.alerts.email_alerter import EmailAlerter
from health_monitor.alerts.aliyun_sms_alerter import AliyunSMSAlerter
from health_monitor.models.health_check import AlertMessage


async def demo_http_alerter():
    """演示HTTP告警器"""
    print("=== HTTP告警器演示 ===")
    
    # 配置HTTP告警器（使用httpbin.org作为测试端点）
    config = {
        'url': 'https://httpbin.org/post',
        'method': 'POST',
        'headers': {
            'Content-Type': 'application/json'
        },
        'template': '''
        {
            "alert_type": "service_health",
            "service": "{{service_name}}",
            "status": "{{status}}",
            "timestamp": "{{timestamp}}",
            "message": "服务 {{service_name}} 状态变为 {{status}}"
        }
        ''',
        'max_retries': 2,
        'timeout': 10
    }
    
    try:
        alerter = HTTPAlerter('demo-http', config)
        
        # 创建测试告警消息
        message = AlertMessage(
            service_name='demo-service',
            service_type='redis',
            status='DOWN',
            timestamp=datetime.now(),
            error_message='连接超时',
            response_time=5.0
        )
        
        # 发送告警
        success = await alerter.send_alert(message)
        print(f"HTTP告警发送结果: {'成功' if success else '失败'}")
        
    except Exception as e:
        print(f"HTTP告警器演示失败: {e}")


async def demo_email_alerter():
    """演示邮件告警器"""
    print("\n=== 邮件告警器演示 ===")
    
    # 注意：这里使用的是示例配置，实际使用时需要替换为真实的SMTP配置
    config = {
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587,
        'username': 'your-email@gmail.com',  # 替换为您的邮箱
        'password': 'your-app-password',     # 替换为您的应用密码
        'use_tls': True,
        'from_email': 'your-email@gmail.com',
        'from_name': '服务监控系统',
        'to_emails': ['admin@example.com'],  # 替换为接收邮箱
        'subject_template': '🚨 服务告警: {{service_name}} - {{status}}',
        'body_template': '''
服务健康监控告警

服务名称: {{service_name}}
服务类型: {{service_type}}
当前状态: {{status}}
发生时间: {{timestamp}}
错误信息: {{error_message}}
响应时间: {{response_time}}ms

请及时处理！
        ''',
        'max_retries': 2,
        'timeout': 30
    }
    
    try:
        alerter = EmailAlerter('demo-email', config)
        
        # 创建测试告警消息
        message = AlertMessage(
            service_name='demo-database',
            service_type='mysql',
            status='DOWN',
            timestamp=datetime.now(),
            error_message='数据库连接失败',
            response_time=10.0
        )
        
        print("注意: 邮件告警器需要真实的SMTP配置才能发送邮件")
        print("请在配置中填入您的邮箱信息后再运行此演示")
        
        # 验证配置（不实际发送）
        is_valid = alerter.validate_config()
        print(f"邮件告警器配置验证: {'通过' if is_valid else '失败'}")
        
        # 如果您已配置真实的SMTP信息，可以取消注释下面的代码
        # success = await alerter.send_alert(message)
        # print(f"邮件告警发送结果: {'成功' if success else '失败'}")
        
    except Exception as e:
        print(f"邮件告警器演示失败: {e}")


async def demo_aliyun_sms_alerter():
    """演示阿里云短信告警器"""
    print("\n=== 阿里云短信告警器演示 ===")
    
    # 注意：这里使用的是示例配置，实际使用时需要替换为真实的阿里云配置
    config = {
        'access_key_id': 'YOUR_ACCESS_KEY_ID',        # 替换为您的AccessKey ID
        'access_key_secret': 'YOUR_ACCESS_KEY_SECRET', # 替换为您的AccessKey Secret
        'region': 'cn-hangzhou',
        'sign_name': '您的签名',                        # 替换为您的短信签名
        'template_code': 'SMS_123456789',              # 替换为您的短信模板代码
        'phone_numbers': ['13800138000'],              # 替换为接收短信的手机号
        'template_params': {
            'service': '{{service_name}}',
            'status': '{{status}}',
            'time': '{{timestamp}}'
        },
        'max_retries': 3,
        'batch_size': 100
    }
    
    try:
        # 由于需要真实的阿里云配置，这里只演示配置验证
        print("注意: 阿里云短信告警器需要真实的阿里云配置才能发送短信")
        print("请在配置中填入您的阿里云信息后再运行此演示")
        
        # 创建测试告警消息
        message = AlertMessage(
            service_name='demo-api',
            service_type='restful',
            status='DOWN',
            timestamp=datetime.now(),
            error_message='API响应超时',
            response_time=30.0
        )
        
        print("短信告警器配置示例:")
        print(f"- 区域: {config['region']}")
        print(f"- 签名: {config['sign_name']}")
        print(f"- 模板代码: {config['template_code']}")
        print(f"- 手机号数量: {len(config['phone_numbers'])}")
        print(f"- 批量大小: {config['batch_size']}")
        
        # 如果您已配置真实的阿里云信息，可以取消注释下面的代码
        # alerter = AliyunSMSAlerter('demo-sms', config)
        # success = await alerter.send_alert(message)
        # print(f"短信告警发送结果: {'成功' if success else '失败'}")
        
    except Exception as e:
        print(f"阿里云短信告警器演示失败: {e}")


async def demo_multiple_alerters():
    """演示多个告警器同时工作"""
    print("\n=== 多告警器协同演示 ===")
    
    # 创建测试告警消息
    message = AlertMessage(
        service_name='critical-service',
        service_type='redis',
        status='DOWN',
        timestamp=datetime.now(),
        error_message='服务完全不可用',
        response_time=None
    )
    
    # HTTP告警器配置
    http_config = {
        'url': 'https://httpbin.org/post',
        'method': 'POST',
        'template': '{"service": "{{service_name}}", "status": "{{status}}"}',
        'timeout': 5
    }
    
    alerters = []
    
    try:
        # 创建HTTP告警器
        http_alerter = HTTPAlerter('multi-http', http_config)
        alerters.append(('HTTP', http_alerter))
        
        print("已创建以下告警器:")
        for name, alerter in alerters:
            print(f"- {name}告警器: {alerter.name}")
        
        # 并发发送告警
        print("\n开始并发发送告警...")
        tasks = []
        for name, alerter in alerters:
            task = asyncio.create_task(alerter.send_alert(message))
            tasks.append((name, task))
        
        # 等待所有任务完成
        results = []
        for name, task in tasks:
            try:
                success = await task
                results.append((name, success))
            except Exception as e:
                results.append((name, f"错误: {e}"))
        
        # 显示结果
        print("\n告警发送结果:")
        for name, result in results:
            if isinstance(result, bool):
                print(f"- {name}: {'成功' if result else '失败'}")
            else:
                print(f"- {name}: {result}")
                
    except Exception as e:
        print(f"多告警器演示失败: {e}")


def print_configuration_guide():
    """打印配置指南"""
    print("\n" + "="*60)
    print("告警器配置指南")
    print("="*60)
    
    print("\n1. HTTP告警器配置:")
    print("   - 支持钉钉机器人、企业微信、Slack等Webhook")
    print("   - 可自定义HTTP方法、请求头和消息模板")
    print("   - 支持重试机制和超时设置")
    
    print("\n2. 邮件告警器配置:")
    print("   - 支持Gmail、企业邮箱等SMTP服务")
    print("   - 支持TLS/SSL加密")
    print("   - 支持多收件人、抄送、密送")
    print("   - 可自定义邮件主题和正文模板")
    
    print("\n3. 阿里云短信告警器配置:")
    print("   - 需要阿里云账号和短信服务")
    print("   - 需要配置AccessKey和短信签名")
    print("   - 支持批量发送和模板参数")
    print("   - 支持多个手机号码")
    
    print("\n4. 配置文件示例:")
    print("   请参考 config/alerts_example.yaml 文件")
    
    print("\n5. 安全提醒:")
    print("   - 不要在代码中硬编码敏感信息")
    print("   - 使用环境变量或配置文件存储密钥")
    print("   - 定期更新访问密钥和密码")


async def main():
    """主函数"""
    print("服务健康监控系统 - 告警器演示")
    print("="*50)
    
    # 运行各个演示
    await demo_http_alerter()
    await demo_email_alerter()
    await demo_aliyun_sms_alerter()
    await demo_multiple_alerters()
    
    # 打印配置指南
    print_configuration_guide()
    
    print("\n演示完成！")


if __name__ == '__main__':
    asyncio.run(main())