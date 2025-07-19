"""CLI接口功能测试"""

import os
import tempfile
import pytest
import yaml
import asyncio
from unittest.mock import patch, MagicMock
from pathlib import Path

from main import (
    create_argument_parser, 
    validate_config_file, 
    run_alert_test, 
    check_once,
    main,
    __version__
)


class TestArgumentParser:
    """命令行参数解析器测试"""
    
    def test_create_argument_parser(self):
        """测试创建参数解析器"""
        parser = create_argument_parser()
        
        # 测试基本属性
        assert parser.prog == 'health-monitor'
        assert '健康监控系统' in parser.description
        
    def test_parse_basic_args(self):
        """测试解析基本参数"""
        parser = create_argument_parser()
        
        # 测试配置文件参数
        args = parser.parse_args(['config.yaml'])
        assert args.config_file == 'config.yaml'
        assert not args.validate
        assert not args.test_alerts
        assert not args.check_once
        assert not args.daemon
    
    def test_parse_validate_flag(self):
        """测试验证标志"""
        parser = create_argument_parser()
        
        args = parser.parse_args(['--validate', 'config.yaml'])
        assert args.config_file == 'config.yaml'
        assert args.validate
    
    def test_parse_test_alerts_flag(self):
        """测试告警测试标志"""
        parser = create_argument_parser()
        
        args = parser.parse_args(['--test-alerts', 'config.yaml'])
        assert args.config_file == 'config.yaml'
        assert args.test_alerts
    
    def test_parse_check_once_flag(self):
        """测试单次检查标志"""
        parser = create_argument_parser()
        
        args = parser.parse_args(['--check-once', 'config.yaml'])
        assert args.config_file == 'config.yaml'
        assert args.check_once
    
    def test_parse_daemon_flag(self):
        """测试守护进程标志"""
        parser = create_argument_parser()
        
        args = parser.parse_args(['--daemon', 'config.yaml'])
        assert args.config_file == 'config.yaml'
        assert args.daemon
    
    def test_parse_log_level(self):
        """测试日志级别参数"""
        parser = create_argument_parser()
        
        args = parser.parse_args(['--log-level', 'DEBUG', 'config.yaml'])
        assert args.config_file == 'config.yaml'
        assert args.log_level == 'DEBUG'
    
    def test_parse_log_file(self):
        """测试日志文件参数"""
        parser = create_argument_parser()
        
        args = parser.parse_args(['--log-file', '/tmp/test.log', 'config.yaml'])
        assert args.config_file == 'config.yaml'
        assert args.log_file == '/tmp/test.log'
    
    def test_parse_pid_file(self):
        """测试PID文件参数"""
        parser = create_argument_parser()
        
        args = parser.parse_args(['--pid-file', '/tmp/test.pid', 'config.yaml'])
        assert args.config_file == 'config.yaml'
        assert args.pid_file == '/tmp/test.pid'
    
    def test_version_argument(self):
        """测试版本参数"""
        parser = create_argument_parser()
        
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(['--version'])
        
        assert exc_info.value.code == 0


class TestConfigValidation:
    """配置验证测试"""
    
    @pytest.fixture
    def valid_config_file(self):
        """创建有效的配置文件"""
        config_data = {
            'global': {
                'check_interval': 30,
                'log_level': 'INFO'
            },
            'services': {
                'test-redis': {
                    'type': 'redis',
                    'host': 'localhost',
                    'port': 6379
                },
                'test-api': {
                    'type': 'restful',
                    'url': 'http://localhost:8080/health'
                }
            },
            'alerts': [
                {
                    'name': 'test-webhook',
                    'type': 'http',
                    'url': 'http://localhost:8080/webhook'
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f, default_flow_style=False)
            temp_file = f.name
        
        yield temp_file
        
        if os.path.exists(temp_file):
            os.unlink(temp_file)
    
    @pytest.fixture
    def invalid_config_file(self):
        """创建无效的配置文件"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("invalid: yaml: content: [")
            temp_file = f.name
        
        yield temp_file
        
        if os.path.exists(temp_file):
            os.unlink(temp_file)
    
    def test_validate_valid_config(self, valid_config_file):
        """测试验证有效配置"""
        with patch('builtins.print') as mock_print:
            result = validate_config_file(valid_config_file)
            
            assert result is True
            
            # 检查输出信息
            print_calls = [call[0][0] for call in mock_print.call_args_list]
            assert any('配置文件验证成功' in call for call in print_calls)
            assert any('服务数量: 2' in call for call in print_calls)
            assert any('告警配置数量: 1' in call for call in print_calls)
    
    def test_validate_invalid_config(self, invalid_config_file):
        """测试验证无效配置"""
        with patch('builtins.print') as mock_print:
            result = validate_config_file(invalid_config_file)
            
            assert result is False
            
            # 检查错误输出
            print_calls = [call[0][0] for call in mock_print.call_args_list]
            assert any('配置文件验证失败' in call for call in print_calls)
    
    def test_validate_nonexistent_config(self):
        """测试验证不存在的配置文件"""
        with patch('builtins.print') as mock_print:
            result = validate_config_file('/nonexistent/config.yaml')
            
            assert result is False
            
            # 检查错误输出
            print_calls = [call[0][0] for call in mock_print.call_args_list]
            assert any('配置文件不存在' in call for call in print_calls)


class TestAlertTesting:
    """告警测试功能测试"""
    
    @pytest.fixture
    def config_file(self):
        """创建配置文件"""
        config_data = {
            'global': {
                'check_interval': 30,
                'log_level': 'INFO'
            },
            'services': {
                'test-service': {
                    'type': 'redis',
                    'host': 'localhost',
                    'port': 6379
                }
            },
            'alerts': [
                {
                    'name': 'test-webhook',
                    'type': 'http',
                    'url': 'http://localhost:8080/webhook'
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f, default_flow_style=False)
            temp_file = f.name
        
        yield temp_file
        
        if os.path.exists(temp_file):
            os.unlink(temp_file)
    
    @pytest.mark.asyncio
    async def test_test_alerts_success(self, config_file):
        """测试告警系统测试成功"""
        with patch('main.HealthMonitorApp') as mock_app_class:
            mock_app = MagicMock()
            mock_app.initialize = AsyncMock()
            mock_app.alert_integrator.test_alert_system = AsyncMock(return_value=True)
            mock_app_class.return_value = mock_app
            
            with patch('builtins.print') as mock_print:
                result = await run_alert_test(config_file)
                
                assert result is True
                
                # 检查输出信息
                print_calls = [call[0][0] for call in mock_print.call_args_list]
                assert any('告警系统测试成功' in call for call in print_calls)
    
    @pytest.mark.asyncio
    async def test_test_alerts_failure(self, config_file):
        """测试告警系统测试失败"""
        with patch('main.HealthMonitorApp') as mock_app_class:
            mock_app = MagicMock()
            mock_app.initialize = AsyncMock()
            mock_app.alert_integrator.test_alert_system = AsyncMock(return_value=False)
            mock_app_class.return_value = mock_app
            
            with patch('builtins.print') as mock_print:
                result = await run_alert_test(config_file)
                
                assert result is False
                
                # 检查输出信息
                print_calls = [call[0][0] for call in mock_print.call_args_list]
                assert any('告警系统测试失败' in call for call in print_calls)


class TestHealthCheck:
    """健康检查功能测试"""
    
    @pytest.fixture
    def config_file(self):
        """创建配置文件"""
        config_data = {
            'global': {
                'check_interval': 30,
                'log_level': 'INFO'
            },
            'services': {
                'test-service-1': {
                    'type': 'redis',
                    'host': 'localhost',
                    'port': 6379
                },
                'test-service-2': {
                    'type': 'restful',
                    'url': 'http://localhost:8080/health'
                }
            },
            'alerts': []
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f, default_flow_style=False)
            temp_file = f.name
        
        yield temp_file
        
        if os.path.exists(temp_file):
            os.unlink(temp_file)
    
    @pytest.mark.asyncio
    async def test_check_once_success(self, config_file):
        """测试单次健康检查成功"""
        from health_monitor.models.health_check import HealthCheckResult
        
        # 模拟健康检查结果
        mock_results = {
            'test-service-1': HealthCheckResult(
                service_name='test-service-1',
                service_type='redis',
                is_healthy=True,
                response_time=0.05
            ),
            'test-service-2': HealthCheckResult(
                service_name='test-service-2',
                service_type='restful',
                is_healthy=True,
                response_time=0.12
            )
        }
        
        with patch('main.HealthMonitorApp') as mock_app_class:
            mock_app = MagicMock()
            mock_app.initialize = MagicMock(return_value=asyncio.coroutine(lambda: None)())
            mock_app.monitor_scheduler.check_all_services_now = MagicMock(
                return_value=asyncio.coroutine(lambda: mock_results)()
            )
            mock_app_class.return_value = mock_app
            
            with patch('builtins.print') as mock_print:
                result = await check_once(config_file)
                
                assert result is True
                
                # 检查输出信息
                print_calls = [call[0][0] for call in mock_print.call_args_list]
                assert any('健康检查完成' in call for call in print_calls)
                assert any('共检查 2 个服务' in call for call in print_calls)
    
    @pytest.mark.asyncio
    async def test_check_once_with_failures(self, config_file):
        """测试单次健康检查有失败"""
        from health_monitor.models.health_check import HealthCheckResult
        
        # 模拟健康检查结果（包含失败）
        mock_results = {
            'test-service-1': HealthCheckResult(
                service_name='test-service-1',
                service_type='redis',
                is_healthy=False,
                response_time=0.0,
                error_message='连接超时'
            ),
            'test-service-2': None  # 检查失败
        }
        
        with patch('main.HealthMonitorApp') as mock_app_class:
            mock_app = MagicMock()
            mock_app.initialize = MagicMock(return_value=asyncio.coroutine(lambda: None)())
            mock_app.monitor_scheduler.check_all_services_now = MagicMock(
                return_value=asyncio.coroutine(lambda: mock_results)()
            )
            mock_app_class.return_value = mock_app
            
            with patch('builtins.print') as mock_print:
                result = await check_once(config_file)
                
                assert result is False
                
                # 检查输出信息
                print_calls = [call[0][0] for call in mock_print.call_args_list]
                assert any('健康检查完成' in call for call in print_calls)
                assert any('不健康 - 连接超时' in call for call in print_calls)
                assert any('检查失败' in call for call in print_calls)


class TestMainFunction:
    """主函数CLI测试"""
    
    @pytest.fixture
    def config_file(self):
        """创建配置文件"""
        config_data = {
            'global': {
                'check_interval': 30,
                'log_level': 'INFO'
            },
            'services': {
                'test-service': {
                    'type': 'redis',
                    'host': 'localhost',
                    'port': 6379
                }
            },
            'alerts': []
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f, default_flow_style=False)
            temp_file = f.name
        
        yield temp_file
        
        if os.path.exists(temp_file):
            os.unlink(temp_file)
    
    @pytest.mark.asyncio
    async def test_main_validate_mode(self, config_file):
        """测试主函数验证模式"""
        with patch('sys.argv', ['health-monitor', '--validate', config_file]):
            with patch('sys.exit') as mock_exit:
                with patch('main.validate_config_file', return_value=True) as mock_validate:
                    mock_exit.side_effect = SystemExit(0)
                    
                    with pytest.raises(SystemExit):
                        await main()
                    
                    mock_validate.assert_called_once_with(config_file)
                    mock_exit.assert_called_with(0)
    
    @pytest.mark.asyncio
    async def test_main_test_alerts_mode(self, config_file):
        """测试主函数告警测试模式"""
        with patch('sys.argv', ['health-monitor', '--test-alerts', config_file]):
            with patch('sys.exit') as mock_exit:
                with patch('main.run_alert_test', return_value=asyncio.coroutine(lambda: True)()) as mock_test:
                    mock_exit.side_effect = SystemExit(0)
                    
                    with pytest.raises(SystemExit):
                        await main()
                    
                    mock_test.assert_called_once_with(config_file)
                    mock_exit.assert_called_with(0)
    
    @pytest.mark.asyncio
    async def test_main_check_once_mode(self, config_file):
        """测试主函数单次检查模式"""
        with patch('sys.argv', ['health-monitor', '--check-once', config_file]):
            with patch('sys.exit') as mock_exit:
                with patch('main.check_once', return_value=asyncio.coroutine(lambda: True)()) as mock_check:
                    mock_exit.side_effect = SystemExit(0)
                    
                    with pytest.raises(SystemExit):
                        await main()
                    
                    mock_check.assert_called_once_with(config_file)
                    mock_exit.assert_called_with(0)
    
    @pytest.mark.asyncio
    async def test_main_no_config_file(self):
        """测试主函数没有配置文件参数"""
        with patch('sys.argv', ['health-monitor']):
            with patch('sys.exit') as mock_exit:
                mock_exit.side_effect = SystemExit(1)
                
                with pytest.raises(SystemExit):
                    await main()
                
                mock_exit.assert_called_with(1)
    
    @pytest.mark.asyncio
    async def test_main_nonexistent_config(self):
        """测试主函数使用不存在的配置文件"""
        with patch('sys.argv', ['health-monitor', '/nonexistent/config.yaml']):
            with patch('sys.exit') as mock_exit:
                mock_exit.side_effect = SystemExit(1)
                
                with pytest.raises(SystemExit):
                    await main()
                
                mock_exit.assert_called_with(1)
    
    @pytest.mark.asyncio
    async def test_main_with_log_level_override(self, config_file):
        """测试主函数日志级别覆盖"""
        with patch('sys.argv', ['health-monitor', '--log-level', 'DEBUG', config_file]):
            with patch('main.HealthMonitorApp') as mock_app_class:
                mock_app = MagicMock()
                mock_app.initialize = MagicMock(return_value=asyncio.coroutine(lambda: None)())
                mock_app.start = MagicMock(side_effect=KeyboardInterrupt())
                mock_app.stop = MagicMock(return_value=asyncio.coroutine(lambda: None)())
                mock_app._configure_logging = MagicMock()
                mock_app_class.return_value = mock_app
                
                await main()
                
                # 验证日志配置被调用
                mock_app._configure_logging.assert_called()
    
    @pytest.mark.asyncio
    async def test_main_normal_startup(self, config_file):
        """测试主函数正常启动"""
        with patch('sys.argv', ['health-monitor', config_file]):
            with patch('main.HealthMonitorApp') as mock_app_class:
                mock_app = MagicMock()
                mock_app.initialize = MagicMock(return_value=asyncio.coroutine(lambda: None)())
                mock_app.start = MagicMock(side_effect=KeyboardInterrupt())
                mock_app.stop = MagicMock(return_value=asyncio.coroutine(lambda: None)())
                mock_app_class.return_value = mock_app
                
                with patch('builtins.print') as mock_print:
                    await main()
                
                # 验证启动信息
                print_calls = [call[0][0] for call in mock_print.call_args_list]
                assert any(f'健康监控系统 v{__version__} 已启动' in call for call in print_calls)
                assert any(f'配置文件: {config_file}' in call for call in print_calls)
                
                # 验证应用程序被正确初始化和启动
                mock_app.initialize.assert_called_once()
                mock_app.start.assert_called_once()
                mock_app.stop.assert_called_once()