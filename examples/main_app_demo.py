#!/usr/bin/env python3
"""
主应用程序演示

展示健康监控系统的主要功能，包括：
1. 应用程序初始化
2. 配置加载和验证
3. 组件集成
4. 优雅关闭
"""

import asyncio
import os
# 添加项目根目录到Python路径
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import HealthMonitorApp, validate_config_file, check_once


async def demo_main_app():
    """演示主应用程序功能"""
    print("🚀 健康监控系统主应用程序演示")
    print("=" * 50)

    # 创建演示配置文件
    demo_config = {
        'global': {
            'check_interval': 10,
            'log_level': 'INFO',
            'max_concurrent_checks': 3
        },
        'services': {
            'demo-redis': {
                'type': 'redis',
                'host': 'localhost',
                'port': 6379,
                'timeout': 5,
                'check_interval': 15
            },
            'demo-api': {
                'type': 'restful',
                'url': 'https://httpbin.org/status/200',
                'method': 'GET',
                'timeout': 10,
                'expected_status': 200
            }
        },
        'alerts': [
            {
                'name': 'demo-webhook',
                'type': 'http',
                'url': 'https://httpbin.org/post',
                'method': 'POST',
                'headers': {
                    'Content-Type': 'application/json'
                },
                'template': '{"message": "服务 {{service_name}} 状态: {{status}}"}'
            }
        ]
    }

    # 创建临时配置文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(demo_config, f, default_flow_style=False, allow_unicode=True)
        config_file = f.name

    try:
        print("📋 1. 配置文件验证演示")
        print("-" * 30)

        # 验证配置文件
        is_valid = validate_config_file(config_file)
        print(f"配置验证结果: {'✅ 成功' if is_valid else '❌ 失败'}")
        print()

        print("🔧 2. 应用程序初始化演示")
        print("-" * 30)

        # 创建应用程序实例
        app = HealthMonitorApp(config_file)
        print("✅ 应用程序实例创建成功")

        # 初始化应用程序
        await app.initialize()
        print("✅ 应用程序组件初始化完成")

        # 显示应用程序状态
        status = app.get_status()
        print(f"📊 应用程序状态:")
        print(f"   - 运行状态: {status['is_running']}")
        print(f"   - 配置文件: {os.path.basename(status['config_path'])}")
        print(f"   - 后台任务数: {status['background_tasks_count']}")
        print(f"   - 监控服务数: {status['scheduler_stats']['total_services']}")
        print(f"   - 告警器数量: {status['alert_stats']['alerter_count']}")
        print()

        print("🔍 3. 单次健康检查演示")
        print("-" * 30)

        # 执行单次健康检查
        success = await check_once(config_file)
        print(f"健康检查结果: {'✅ 成功' if success else '❌ 失败'}")
        print()

        print("⚡ 4. 短时间运行演示")
        print("-" * 30)
        print("启动监控系统运行5秒...")

        # 启动应用程序（在后台运行）
        app_task = asyncio.create_task(app.start())

        # 等待5秒
        await asyncio.sleep(5)

        # 优雅关闭
        print("正在优雅关闭系统...")
        app.shutdown()

        # 等待应用程序完全停止
        try:
            await asyncio.wait_for(app_task, timeout=10)
        except asyncio.TimeoutError:
            print("⚠️ 应用程序关闭超时")

        print("✅ 应用程序已成功关闭")
        print()

        print("📈 5. 最终状态报告")
        print("-" * 30)

        # 显示最终状态
        final_status = app.get_status()
        print(f"   - 最终运行状态: {final_status['is_running']}")
        print(f"   - 后台任务数: {final_status['background_tasks_count']}")

        # 显示服务状态
        if 'current_states' in final_status:
            print("   - 服务状态:")
            for service_name, is_healthy in final_status['current_states'].items():
                status_text = "健康" if is_healthy else "不健康"
                emoji = "✅" if is_healthy else "❌"
                print(f"     {emoji} {service_name}: {status_text}")

    except Exception as e:
        print(f"❌ 演示过程中发生错误: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # 清理临时文件
        if os.path.exists(config_file):
            os.unlink(config_file)

        print("\n🎉 主应用程序演示完成!")


if __name__ == "__main__":
    # 运行演示
    asyncio.run(demo_main_app())
