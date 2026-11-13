"""Durable incident timeline; records detection, not notification delivery."""

import sqlite3
from pathlib import Path


class EventStore:
    def __init__(self, path):
        if path != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute('''CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY, service TEXT NOT NULL, type TEXT NOT NULL,
            status TEXT NOT NULL, timestamp TEXT NOT NULL, message TEXT,
            response_time REAL)''')
        self.db.commit()

    def record(self, result):
        with self.db:
            self.db.execute('INSERT INTO events(service,type,status,timestamp,message,response_time) '
                            'VALUES (?,?,?,?,?,?)',
                            (result.service_name, result.service_type,
                             'UP' if result.is_healthy else 'DOWN',
                             result.timestamp.astimezone().isoformat(), result.error_message,
                             result.response_time))
            # Bounded retention, including across restarts.
            self.db.execute('DELETE FROM events WHERE id <= '
                            '(SELECT COALESCE(MAX(id),0)-10000 FROM events)')

    def list(self, service='', status='', limit=50, offset=0):
        where, args = [], []
        for column, value in [('service', service), ('status', status)]:
            if value:
                where.append(f'{column} = ?')
                args.append(value)
        clause = ' WHERE ' + ' AND '.join(where) if where else ''
        total = self.db.execute('SELECT COUNT(*) FROM events' + clause, args).fetchone()[0]
        rows = self.db.execute('SELECT * FROM events' + clause + ' ORDER BY id DESC LIMIT ? OFFSET ?',
                               [*args, limit, offset]).fetchall()
        return {'total': total, 'items': [dict(row) for row in rows]}

    def close(self):
        self.db.close()
