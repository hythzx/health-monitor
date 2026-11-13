"""Real SQLite + HTTP coverage for configuration migration and history lifecycle."""
import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock

import pytest
import pytest_asyncio
from aiohttp.test_utils import TestClient, TestServer

from main import HealthMonitorApp
from health_monitor.services.event_store import EventStore
from health_monitor.models.health_check import HealthCheckResult, StateChange
from health_monitor.web import WebServer

TOKEN = 'database-console-token-1234'
CONFIG = 'global:\n  check_interval: 30\nservices:\n  cache:\n    type: redis\n    host: localhost\nalerts: []\n'


@pytest_asyncio.fixture
async def database_console(tmp_path):
    path = tmp_path / 'bootstrap.yaml'
    path.write_text(CONFIG)
    database = tmp_path / 'monitor.sqlite3'
    monitor = HealthMonitorApp(str(path), database_path=str(database))
    await monitor.initialize()
    async with TestClient(TestServer(WebServer(monitor, TOKEN).app)) as client:
        client.session.headers['Authorization'] = 'Bearer ' + TOKEN
        yield client, monitor, path, database
    await monitor.stop()


async def test_import_once_restart_without_yaml_and_restore_status(database_console):
    client, monitor, path, database = database_console
    snapshot = await (await client.get('/api/settings')).json()
    snapshot['config']['services']['api'] = {'type': 'restful', 'url': 'http://localhost/health'}
    snapshot['config']['global']['check_interval'] = 12
    assert (await client.put('/api/settings', json=snapshot)).status == 200
    assert path.read_text() == CONFIG
    assert monitor.monitor_scheduler.check_intervals['api'] == 12
    await monitor._process_health_check_result(HealthCheckResult('cache', 'redis', False, .1, 'unavailable'))
    path.unlink()
    other = HealthMonitorApp(str(path), database_path=str(database))
    await other.initialize()
    try:
        assert set(other.config_manager.get_services_config()) == {'cache', 'api'}
        assert other.state_manager.get_current_state('cache') is False
        assert other.state_manager.state_history[0].error_message == 'unavailable'
    finally:
        await other.stop()


async def test_conflict_validation_and_apply_failure_roll_back(database_console):
    client, monitor, _, database = database_console
    snapshot = await (await client.get('/api/settings')).json()
    original_config = monitor.config_manager.config.copy()
    snapshot['config']['global']['check_interval'] = 12
    original = monitor._on_config_changed_callback
    def failing(old, new):
        original(old, new)
        if new['global']['check_interval'] == 12:
            monitor.logger.warning('Log inside failed configuration transaction')
            raise RuntimeError('apply failure')
    with patch.object(monitor, '_on_config_changed_callback', side_effect=failing):
        assert (await client.put('/api/settings', json=snapshot)).status == 500
    assert monitor.config_manager.config == original_config
    assert monitor.event_store.config_snapshot()['config'] == original_config
    assert monitor.monitor_scheduler.check_intervals['cache'] == 30
    assert (await client.put('/api/settings', json=snapshot)).status == 200
    assert (await client.put('/api/settings', json=snapshot)).status == 409
    latest = await (await client.get('/api/settings')).json()
    latest['config']['services']['bad'] = {'type': 'redis', 'host': 'localhost', 'port': -1}
    assert (await client.put('/api/settings', json=latest)).status == 400
    assert 'bad' not in monitor.monitor_scheduler.checkers
    second = EventStore(str(database))
    assert 'bad' not in second.config_snapshot()['config']['services']
    second.close()


async def test_all_checks_errors_logs_and_deliveries_are_persisted(database_console):
    client, monitor, _, database = database_console
    for healthy in (True, False, False, True):
        await monitor._process_health_check_result(HealthCheckResult('cache', 'redis', healthy, .01, None if healthy else 'timeout'))
    assert (await (await client.get('/api/history/checks')).json())['total'] == 4
    assert (await (await client.get('/api/history/errors?service=cache')).json())['total'] == 2
    assert (await (await client.get('/api/history/events')).json())['total'] == 2
    # Record actual per-channel returns (including False without an exception).
    channel = AsyncMock()
    channel.name = 'webhook'
    channel.send_alert.return_value = False
    monitor.alert_integrator.alert_manager.alerters = [channel]
    await monitor.alert_integrator.alert_manager.send_alert(StateChange('cache', 'redis', True, False))
    deliveries = await (await client.get('/api/history/deliveries?status=FAILED')).json()
    assert deliveries['total'] == 1
    assert deliveries['items'][0]['channel'] == 'webhook'
    await asyncio.to_thread(monitor.logger.error, 'thread-side runtime error')
    logs = await (await client.get('/api/history/errors?search=thread-side')).json()
    assert logs['total'] == 1
    other = EventStore(str(database))
    assert other.query('checks')['total'] == 4
    assert other.query('deliveries')['total'] == 1
    other.close()


async def test_cleanup_retention_filters_and_config_isolation(database_console):
    client, monitor, _, _ = database_console
    store = monitor.event_store
    old = datetime.now(timezone.utc) - timedelta(days=90)
    await monitor._process_health_check_result(HealthCheckResult('cache', 'redis', False, .01, 'old error', old.replace(tzinfo=None)))
    await monitor._process_health_check_result(HealthCheckResult('cache', 'redis', True, .01))
    store.record_log('ERROR', 'old', 'old runtime error', timestamp=old.isoformat())
    snapshot = store.config_snapshot()
    assert (await client.put('/api/retention', json={'retention_days': 7, 'max_rows': 100})).status == 200
    assert (await client.put('/api/retention', json={'retention_days': 0, 'max_rows': 100})).status == 400
    cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert (await client.post('/api/history/cleanup', json={'kind': 'all', 'before': cutoff})).status == 400
    response = await client.post('/api/history/cleanup', json={'kind': 'all', 'before': cutoff, 'confirm': True})
    assert response.status == 200
    assert (await response.json())['deleted']['checks'] == 1
    assert store.config_snapshot() == snapshot
    assert store.latest_checks()[0]['status'] == 'UP'
    data = await (await client.get('/api/history/checks?status=UP&limit=1&offset=0')).json()
    assert data['total'] == 1
    assert data['items'][0]['status'] == 'UP'
    for i in range(102):
        store.record_check(HealthCheckResult('cache', 'redis', True, .01))
    assert store.query('checks')['total'] == 100
    store.cleanup()
    assert store.config_snapshot() == snapshot


@pytest.mark.parametrize('path', [
    '/api/settings', '/api/history/checks', '/api/history/errors', '/api/retention',
])
async def test_new_endpoints_are_authenticated(database_console, path):
    client, _, _, _ = database_console
    assert (await client.get(path, headers={'Authorization': ''})).status == 401


@pytest.mark.parametrize('query', ['limit=101', 'offset=-1', 'status=bad', 'since=bad', 'since=2026-01-01', 'level=BAD'])
async def test_history_rejects_invalid_query(database_console, query):
    client, _, _, _ = database_console
    assert (await client.get('/api/history/checks?' + query)).status == 400


async def test_yaml_api_updates_database_and_blank_bootstrap(tmp_path, database_console):
    client, monitor, _, _ = database_console
    data = await (await client.get('/api/config')).json()
    data['content'] = data['content'].replace('check_interval: 30', 'check_interval: 15')
    assert (await client.put('/api/config', json=data)).status == 200
    assert monitor.event_store.config_snapshot()['config']['global']['check_interval'] == 15
    blank = HealthMonitorApp(None, database_path=str(tmp_path / 'blank.db'))
    await blank.initialize()
    assert blank.config_manager.get_services_config() == {}
    await blank.stop()


def test_migrates_old_events_database_and_redacts_secrets(tmp_path):
    path = tmp_path / 'events.db'
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE events (id INTEGER PRIMARY KEY, service TEXT NOT NULL, type TEXT NOT NULL, status TEXT NOT NULL, timestamp TEXT NOT NULL, message TEXT, response_time REAL)')
    db.execute("INSERT INTO events VALUES (1, 'legacy', 'redis', 'DOWN', '2026-11-01T00:00:00+08:00', 'old', 0)")
    db.commit()
    db.close()
    store = EventStore(str(path))
    assert store.list()['items'][0]['service'] == 'legacy'
    store.update_secrets({'password': 'private-secret', 'headers': {'X-Custom-Key': 'private-header'}})
    store.record_log('ERROR', 'test', 'private-secret private-header https://example.test/?access_token=private-token')
    message = store.query('errors')['items'][0]['message']
    assert 'private-' not in message
    assert path.stat().st_mode & 0o077 == 0
    store.close()
