"""Authenticated management API and bundled UI on the monitor's event loop."""

import asyncio
import hashlib
import hmac
import json
import os
import stat
import tempfile
from dataclasses import asdict
from pathlib import Path

import yaml
from aiohttp import web

from .checkers.factory import health_checker_factory
from .utils.exceptions import ConfigError, CheckerError, AlertConfigError


class WebServer:
    def __init__(self, monitor, token, host='127.0.0.1', port=8080):
        if not token or len(token) < 16:
            raise ConfigError('启用 Web 管理需要设置至少 16 位的 HEALTH_MONITOR_WEB_TOKEN')
        self.monitor, self.token, self.host, self.port = monitor, token, host, port
        self.lock = asyncio.Lock()
        self.runner = None
        self.app = web.Application(middlewares=[self.guard], client_max_size=1024 * 1024)
        self.app.add_routes([
            web.get('/', self.index), web.get('/health', self.health),
            web.get('/assets/{name}', self.asset),
            web.get('/api/status', self.status), web.get('/api/alerts', self.alerts),
            web.get('/api/config', self.get_config),
            web.post('/api/config/validate', self.validate),
            web.put('/api/config', self.save_config),
        ])

    @web.middleware
    async def guard(self, request, handler):
        try:
            if request.path.startswith('/api/'):
                supplied = request.headers.get('Authorization', '')
                if not hmac.compare_digest(supplied.encode(), ('Bearer ' + self.token).encode()):
                    raise web.HTTPUnauthorized(text='请登录后访问')
                if request.method not in ('GET', 'HEAD'):
                    if request.content_type != 'application/json':
                        raise web.HTTPUnsupportedMediaType()
                    origin = request.headers.get('Origin')
                    if origin and origin != f'{request.scheme}://{request.host}':
                        raise web.HTTPForbidden(text='不允许跨站修改配置')
            response = await handler(request)
        except (ConfigError, CheckerError, AlertConfigError, yaml.YAMLError, ValueError, TypeError, KeyError) as exc:
            # Validator messages only; YAML parser errors can contain credentials.
            message = 'YAML 格式错误，请检查缩进与字段类型' if isinstance(exc, yaml.YAMLError) else str(exc)
            response = web.json_response({'error': message}, status=400)
        except web.HTTPException as exc:
            response = web.json_response({'error': exc.text or exc.reason}, status=exc.status)
        except Exception:
            self.monitor.logger.error('管理接口执行失败，请检查服务日志')
            response = web.json_response({'error': '操作失败，请检查目录写入权限或服务日志'}, status=500)
        response.headers.update({
            'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'no-referrer',
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'",
        })
        return response

    async def index(self, request):
        return web.FileResponse(Path(__file__).parent / 'static' / 'index.html')

    async def asset(self, request):
        name = request.match_info['name']
        if name not in ('app.js', 'style.css'):
            raise web.HTTPNotFound()
        return web.FileResponse(Path(__file__).parent / 'static' / name)

    async def health(self, request):
        return web.json_response({'status': 'ok'})

    async def status(self, request):
        m = self.monitor
        latest = {}
        for result in reversed(m.state_manager.state_history):
            latest.setdefault(result.service_name, result)
        services = []
        for name, config in m.config_manager.get_services_config().items():
            result = latest.get(name)
            services.append({'name': name, 'type': config['type'],
                             'healthy': m.state_manager.get_current_state(name),
                             'last_check': {**asdict(result), 'timestamp': result.timestamp.astimezone().isoformat()} if result else None})
        return web.json_response({'running': m.is_running, 'services': services,
                                  'alert_stats': m.alert_integrator.get_alert_stats()},
                                 dumps=lambda data: json.dumps(data, default=str))

    async def alerts(self, request):
        q = request.query
        limit, offset = int(q.get('limit', 50)), int(q.get('offset', 0))
        if not 1 <= limit <= 100 or offset < 0 or q.get('status', '') not in ('', 'UP', 'DOWN'):
            raise ValueError('预警筛选参数不正确')
        return web.json_response(self.monitor.event_store.list(q.get('service', ''), q.get('status', ''), limit, offset))

    def snapshot(self):
        content = Path(self.monitor.config_path).read_text(encoding='utf-8')
        return {'content': content, 'revision': hashlib.sha256(content.encode()).hexdigest()}

    async def get_config(self, request):
        return web.json_response(self.snapshot())

    def parse(self, content):
        if not isinstance(content, str):
            raise ValueError('配置内容必须是 YAML 文本')
        config = yaml.safe_load(content)
        self.monitor.config_manager._validate_config(config)
        global_config = config.get('global', {})
        for key in ('state_file', 'enable_performance_monitoring'):
            if global_config.get(key) != self.monitor.config_manager.get_global_config().get(key):
                raise ValueError(f'{key} 需要修改文件并重启，不能在线变更')
        for name, item in config.get('services', {}).items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError('服务名称必须是非空文本')
            timeout = item.get('timeout', 10)
            if type(timeout) not in (int, float) or timeout <= 0:
                raise ValueError(f'服务 {name} 的超时必须是正数')
            health_checker_factory.create_checker(name, item)
            interval = item.get('check_interval', global_config.get('check_interval', 30))
            if type(interval) is not int or interval <= 0:
                raise ValueError(f'服务 {name} 的检查间隔必须是正整数')
        from .alerts.http_alerter import HTTPAlerter
        from .alerts.email_alerter import EmailAlerter
        from .alerts.aliyun_sms_alerter import AliyunSMSAlerter
        classes = {'http': HTTPAlerter, 'email': EmailAlerter, 'aliyun_sms': AliyunSMSAlerter}
        names = set()
        for alert in config.get('alerts', []):
            if alert['name'] in names:
                raise ValueError('通知渠道名称不能重复')
            names.add(alert['name'])
            classes[alert['type']](alert['name'], alert)
        return config

    async def validate(self, request):
        self.parse((await request.json())['content'])
        return web.json_response({'valid': True})

    def atomic_write(self, path, content):
        fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.config-', suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as out:
                out.write(content)
                out.flush()
                os.fsync(out.fileno())
            os.chmod(temp, stat.S_IMODE(path.stat().st_mode) & 0o600)
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    async def save_config(self, request):
        data = await request.json()
        async with self.lock:
            snapshot = self.snapshot()
            if data.get('revision') != snapshot['revision']:
                raise web.HTTPConflict(text='配置已被其他人修改，请重新加载后再保存')
            config = self.parse(data['content'])
            path = Path(self.monitor.config_path).resolve()
            # Rotating single backup; only the owner can read credentials.
            backup = path.with_suffix(path.suffix + '.bak')
            backup.touch(mode=0o600, exist_ok=True)
            backup.chmod(0o600)
            backup.write_text(snapshot['content'], encoding='utf-8')
            self.atomic_write(path, data['content'])
            manager = self.monitor.config_manager
            old = manager.config
            try:
                self.monitor._on_config_changed_callback(old, config)
                manager.config = config
                manager.last_modified = path.stat().st_mtime
            except Exception:
                self.atomic_write(path, snapshot['content'])
                self.monitor._on_config_changed_callback(config, old)
                manager.config = old
                manager.last_modified = path.stat().st_mtime
                raise
            return web.json_response({**self.snapshot(), 'saved': True})

    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        try:
            await web.TCPSite(self.runner, self.host, self.port).start()
        except Exception:
            await self.runner.cleanup()
            raise

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()
