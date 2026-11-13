"""API integration: real HTTP, on-disk configuration and live monitor components."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from aiohttp.test_utils import TestClient, TestServer

from main import HealthMonitorApp
from health_monitor.web import WebServer
from health_monitor.models.health_check import HealthCheckResult
from health_monitor.services.event_store import EventStore

TOKEN = 'test-management-token-123456'
CONFIG = 'global:\n  check_interval: 30\nservices:\n  cache:\n    type: redis\n    host: localhost\nalerts: []\n'


@pytest_asyncio.fixture
async def console(tmp_path):
    path = tmp_path / 'config.yaml'
    path.write_text(CONFIG)
    monitor = HealthMonitorApp(str(path))
    await monitor.initialize()
    monitor.event_store = EventStore(str(tmp_path / 'events.db'))
    server = WebServer(monitor, TOKEN)
    async with TestClient(TestServer(server.app)) as client:
        client.session.headers['Authorization'] = 'Bearer ' + TOKEN
        yield client, monitor, path
    monitor.event_store.close()


async def test_authentication_and_security_headers(console):
    client, _, _ = console
    for path in ('/api/status', '/api/alerts', '/api/config'):
        response = await client.get(path, headers={'Authorization': ''})
        assert response.status == 401
    assert (await client.get('/health', headers={'Authorization': ''})).status == 200
    response = await client.get('/')
    assert response.status == 200
    assert response.headers['Cache-Control'] == 'no-store'
    assert "frame-ancestors 'none'" in response.headers['Content-Security-Policy']
    for asset in ('style.css', 'app.js'):
        assert (await client.get('/assets/' + asset)).status == 200


async def test_validate_save_reload_conflict_backup(console):
    client, monitor, path = console
    snapshot = await (await client.get('/api/config')).json()
    content = CONFIG.replace('30', '12').replace('cache:', 'new-cache:')
    response = await client.post('/api/config/validate', json={'content': content})
    assert response.status == 200
    assert path.read_text() == CONFIG
    response = await client.put('/api/config', json={**snapshot, 'content': content})
    assert response.status == 200
    assert path.read_text() == content
    assert set(monitor.monitor_scheduler.checkers) == {'new-cache'}
    assert monitor.monitor_scheduler.check_intervals['new-cache'] == 12
    assert path.with_suffix('.yaml.bak').read_text() == CONFIG
    assert path.with_suffix('.yaml.bak').stat().st_mode & 0o077 == 0
    assert (await client.put('/api/config', json=snapshot)).status == 409
    assert path.read_text() == content


@pytest.mark.parametrize('content', [
    'services: [', 'services: []', 'global:\n  max_concurrent_checks: 0',
    'services:\n  x:\n    type: redis\n    port: -1\n    host: localhost',
    'alerts:\n  - name: broken\n    type: email',
    'services:\n  x:\n    type: redis\n    host: localhost\n    check_interval: -1',
])
async def test_invalid_config_preserves_disk_and_runtime(console, content):
    client, monitor, path = console
    snapshot = await (await client.get('/api/config')).json()
    response = await client.put('/api/config', json={**snapshot, 'content': content})
    assert response.status == 400
    assert path.read_text() == CONFIG
    assert set(monitor.monitor_scheduler.checkers) == {'cache'}


async def test_initial_failure_recovery_and_persistence(console, tmp_path):
    client, monitor, _ = console
    for healthy in (False, False, True):
        await monitor._process_health_check_result(HealthCheckResult('cache', 'redis', healthy, .01))
    data = await (await client.get('/api/alerts?status=DOWN')).json()
    assert data['total'] == 1
    assert data['items'][0]['status'] == 'DOWN'
    data = await (await client.get('/api/alerts?limit=1')).json()
    assert data['total'] == 2
    assert data['items'][0]['status'] == 'UP'
    state = await (await client.get('/api/status')).json()
    assert state['services'][0]['healthy'] is True
    other = EventStore(str(tmp_path / 'events.db'))
    assert other.list()['total'] == 2
    other.close()


async def test_cross_origin_and_invalid_query(console):
    client, _, _ = console
    response = await client.put('/api/config', json={}, headers={'Origin': 'https://untrusted.example'})
    assert response.status == 403
    for query in ('limit=-1', 'offset=-2', 'limit=bad', 'status=BAD'):
        assert (await client.get('/api/alerts?' + query)).status == 400


async def test_apply_failure_rolls_back(console):
    client, monitor, path = console
    snapshot = await (await client.get('/api/config')).json()
    original = monitor._on_config_changed_callback
    def apply(old, new):
        if new['global']['check_interval'] == 12:
            raise RuntimeError('injected failure')
        original(old, new)
    with patch.object(monitor, '_on_config_changed_callback', side_effect=apply):
        response = await client.put('/api/config', json={**snapshot, 'content': CONFIG.replace('30', '12')})
    assert response.status == 500
    assert path.read_text() == CONFIG
    assert monitor.config_manager.config['global']['check_interval'] == 30


async def test_mongo_uses_real_async_api_contract():
    from health_monitor.checkers.mongodb_checker import MongoHealthChecker
    checker = MongoHealthChecker('db', {'host': 'localhost', 'username': 'a@b', 'password': 'x:y'})
    client = AsyncMock()
    with patch('health_monitor.checkers.mongodb_checker.AsyncMongoClient', return_value=client) as ctor:
        result = await checker.check_health()
    assert result.is_healthy
    client.admin.command.assert_awaited_once_with('ping')
    client.close.assert_awaited_once()
    assert 'a%40b:x%3Ay@' in ctor.call_args.args[0]


async def test_mqtt_client_signature_and_success():
    import inspect
    from aiomqtt import Client
    from health_monitor.checkers.emqx_checker import EMQXHealthChecker
    checker = EMQXHealthChecker('mqtt', {'host': 'localhost', 'client_id': 'monitor'})
    client = AsyncMock()
    with patch('health_monitor.checkers.emqx_checker.MQTTClient', return_value=client) as ctor:
        healthy, *_ = await checker._check_mqtt_connection()
    assert healthy
    inspect.signature(Client).bind(**ctor.call_args.kwargs)


async def test_stale_check_does_not_publish_after_reload(console):
    _, monitor, _ = console
    scheduler = monitor.monitor_scheduler
    scheduler.semaphore = asyncio.Semaphore(1)
    checker = scheduler.checkers['cache']
    entered, finish = asyncio.Event(), asyncio.Event()
    async def check():
        entered.set()
        await finish.wait()
        return HealthCheckResult('cache', 'redis', False, .01)
    checker.check_health = check
    task = asyncio.create_task(scheduler._check_service('cache'))
    await entered.wait()
    scheduler.configure_services({})
    finish.set()
    await task
    assert monitor.state_manager.get_all_states() == {}


async def test_journal_failure_does_not_block_health_state(console):
    _, monitor, _ = console
    with patch.object(monitor.event_store, 'record', side_effect=OSError('disk full')):
        await monitor._process_health_check_result(HealthCheckResult('cache', 'redis', False, .01))
    assert monitor.state_manager.get_current_state('cache') is False
