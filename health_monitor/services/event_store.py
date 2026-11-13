"""SQLite configuration and operational history, shared safely with log threads."""

import json
import logging
import os
import re
import sqlite3
import sys
import threading
import traceback
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote


class RevisionConflict(ValueError):
    pass


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class EventStore:
    TABLES = {'events', 'checks', 'logs', 'deliveries'}

    def __init__(self, path):
        if path != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            # Configurations can contain credentials; create before connecting.
            fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(fd)
            os.chmod(path, 0o600)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, timeout=5, check_same_thread=False)
        if self.db.execute('PRAGMA user_version').fetchone()[0] > 1:
            self.db.close()
            raise ValueError('数据库版本高于当前程序支持版本，请升级程序')
        self.db.row_factory = sqlite3.Row
        self.secrets = set()
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, service TEXT NOT NULL, type TEXT NOT NULL,
                status TEXT NOT NULL, timestamp TEXT NOT NULL, message TEXT,
                response_time REAL);
            CREATE TABLE IF NOT EXISTS checks (
                id INTEGER PRIMARY KEY, service TEXT NOT NULL, type TEXT NOT NULL,
                status TEXT NOT NULL, timestamp TEXT NOT NULL, message TEXT,
                response_time REAL);
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, level TEXT NOT NULL,
                logger TEXT NOT NULL, service TEXT NOT NULL DEFAULT '', message TEXT);
            CREATE TABLE IF NOT EXISTS deliveries (
                id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, service TEXT NOT NULL,
                channel TEXT NOT NULL, status TEXT NOT NULL, message TEXT);
            CREATE TABLE IF NOT EXISTS latest_checks (
                service TEXT PRIMARY KEY, type TEXT NOT NULL, status TEXT NOT NULL,
                timestamp TEXT NOT NULL, message TEXT, response_time REAL);
            CREATE TABLE IF NOT EXISTS configuration (
                id INTEGER PRIMARY KEY CHECK(id=1), document TEXT NOT NULL,
                revision INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT OR IGNORE INTO settings VALUES ('retention_days', '30');
            INSERT OR IGNORE INTO settings VALUES ('max_rows', '10000');
            PRAGMA user_version=1;
        ''')
        for table in self.TABLES:
            self.db.execute(f'CREATE INDEX IF NOT EXISTS {table}_timestamp ON {table}(timestamp)')
            if table != 'logs':
                self.db.execute(f'CREATE INDEX IF NOT EXISTS {table}_service ON {table}(service, id DESC)')
        self.db.commit()
        snapshot = self.config_snapshot()
        if snapshot:
            self.update_secrets(snapshot['config'])

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise

    @contextmanager
    def write(self):
        with self.lock:
            if self.db.in_transaction:
                yield
            else:
                with self.db:
                    yield

    def config_snapshot(self):
        with self.lock:
            row = self.db.execute('SELECT * FROM configuration WHERE id=1').fetchone()
            return {'config': json.loads(row['document']), 'revision': str(row['revision'])} if row else None

    def save_config(self, config, revision=None):
        # Can be called within a larger transaction that also applies runtime changes.
        current = self.config_snapshot()
        if current and current['revision'] != revision:
            raise RevisionConflict('配置已被其他人修改，请重新加载后再保存')
        number = int(current['revision']) + 1 if current else 1
        document = json.dumps(config, ensure_ascii=False, allow_nan=False)
        self.db.execute('INSERT OR REPLACE INTO configuration VALUES (1, ?, ?)', (document, number))

    def update_secrets(self, config):
        def walk(value, key=''):
            if isinstance(value, dict):
                for k, v in value.items():
                    walk(v, 'secret' if key in ('headers', 'params') else k)
            elif isinstance(value, list):
                for v in value:
                    walk(v, key)
            elif isinstance(value, str) and value and re.search(r'password|secret|token|authorization|api.?key|access_key', key, re.I):
                self.secrets.update((value, quote(value, safe='')))
        # Keep old secrets redacted after credentials are rotated.
        walk(config)

    def redact(self, message):
        message = str(message or '')
        for secret in sorted(self.secrets, key=len, reverse=True):
            message = message.replace(secret, '***')
        message = re.sub(r'(://)[^/@\s]+:[^/@\s]+@', r'\1***@', message)
        message = re.sub(r'(?i)([?&](?:access_token|token|api_key|key|password|secret)=)[^&\s]+', r'\1***', message)
        message = re.sub(r'(?i)(Bearer\s+)[^\s,]+', r'\1***', message)
        return message[:16000]

    def _trim(self, table):
        maximum = self.retention()['max_rows']
        self.db.execute(f'DELETE FROM {table} WHERE id <= '
                        f'(SELECT id FROM {table} ORDER BY id DESC LIMIT 1 OFFSET ?)', (maximum,))

    def _result(self, table, result):
        with self.write():
            self.db.execute(f'INSERT INTO {table}(service,type,status,timestamp,message,response_time) VALUES (?,?,?,?,?,?)',
                            (result.service_name, result.service_type, 'UP' if result.is_healthy else 'DOWN',
                             result.timestamp.astimezone(timezone.utc).isoformat(),
                             self.redact(result.error_message), result.response_time))
            if table == 'checks':
                self.db.execute('INSERT OR REPLACE INTO latest_checks VALUES (?,?,?,?,?,?)',
                                (result.service_name, result.service_type,
                                 'UP' if result.is_healthy else 'DOWN',
                                 result.timestamp.astimezone(timezone.utc).isoformat(),
                                 self.redact(result.error_message), result.response_time))
            self._trim(table)

    def latest_checks(self):
        with self.lock:
            return [dict(row) for row in self.db.execute('SELECT * FROM latest_checks')]

    def record(self, result):
        self._result('events', result)

    def record_check(self, result):
        self._result('checks', result)
        if not result.is_healthy:
            self.record_log('ERROR', 'health_check', result.error_message or '健康检查失败', result.service_name)

    def record_log(self, level, logger, message, service='', timestamp=None):
        with self.write():
            self.db.execute('INSERT INTO logs(timestamp,level,logger,service,message) VALUES (?,?,?,?,?)',
                            (timestamp or utcnow(), level, logger, service, self.redact(message)))
            self._trim('logs')

    def record_delivery(self, service, channel, success, message):
        with self.write():
            self.db.execute('INSERT INTO deliveries(timestamp,service,channel,status,message) VALUES (?,?,?,?,?)',
                            (utcnow(), service, channel, 'SENT' if success else 'FAILED', self.redact(message)))
            self._trim('deliveries')

    def query(self, kind, *, service='', status='', level='', search='', since='', until='', limit=50, offset=0):
        table = 'logs' if kind == 'errors' else kind
        if table not in self.TABLES:
            raise ValueError('不支持的历史类型')
        conditions, args = [], []
        if kind == 'errors':
            conditions.append("level IN ('ERROR','CRITICAL')")
        for column, value in [('service', service), ('status', status), ('level', level)]:
            if value:
                if (column == 'status' and table == 'logs') or (column == 'level' and table != 'logs'):
                    raise ValueError('该历史类型不支持此筛选条件')
                conditions.append(f'{column}=?')
                args.append(value)
        if search:
            conditions.append('message LIKE ?')
            args.append('%' + search + '%')
        for operator, value in [('>=', since), ('<=', until)]:
            if value:
                conditions.append(f'julianday(timestamp) {operator} julianday(?)')
                args.append(value)
        clause = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
        with self.lock:
            total = self.db.execute(f'SELECT COUNT(*) FROM {table}' + clause, args).fetchone()[0]
            rows = self.db.execute(f'SELECT * FROM {table}' + clause + ' ORDER BY id DESC LIMIT ? OFFSET ?',
                                   [*args, limit, offset]).fetchall()
        return {'total': total, 'items': [dict(row) for row in rows]}

    def list(self, service='', status='', limit=50, offset=0):
        return self.query('events', service=service, status=status, limit=limit, offset=offset)

    def retention(self):
        with self.lock:
            return {row['key']: int(row['value']) for row in self.db.execute('SELECT * FROM settings')}

    def set_retention(self, days, max_rows):
        if type(days) is not int or not 1 <= days <= 3650 or type(max_rows) is not int or not 100 <= max_rows <= 1000000:
            raise ValueError('保留天数须为 1–3650，单类记录上限须为 100–1000000')
        with self.write():
            self.db.executemany('UPDATE settings SET value=? WHERE key=?',
                                [(str(days), 'retention_days'), (str(max_rows), 'max_rows')])

    def cleanup(self, kind='all', before=None):
        kinds = sorted(self.TABLES) if kind == 'all' else [kind]
        if any(item not in self.TABLES | {'errors'} for item in kinds):
            raise ValueError('不支持的历史类型')
        before = before or (datetime.now(timezone.utc) - timedelta(days=self.retention()['retention_days'])).isoformat()
        counts = {}
        with self.write():
            for item in kinds:
                table = 'logs' if item == 'errors' else item
                extra = " AND level IN ('ERROR','CRITICAL')" if item == 'errors' else ''
                cursor = self.db.execute(f'DELETE FROM {table} WHERE julianday(timestamp) < julianday(?)' + extra, (before,))
                counts[item] = cursor.rowcount
                if kind == 'all':
                    self._trim(table)
        return counts

    def close(self):
        with self.lock:
            self.db.close()


class DatabaseLogHandler(logging.Handler):
    def __init__(self, store):
        super().__init__(logging.INFO)
        self.store = store

    def emit(self, record):
        try:
            message = record.getMessage()
            if record.exc_info:
                message += '\n' + ''.join(traceback.format_exception(*record.exc_info))
            self.store.record_log(record.levelname, record.name, message, getattr(record, 'service', ''),
                                  timestamp=datetime.fromtimestamp(record.created, timezone.utc).isoformat())
        except Exception:
            # Never re-enter logging when the disk is full or the database is locked.
            sys.stderr.write('SQLite 日志写入失败，请检查磁盘或数据库权限\n')
