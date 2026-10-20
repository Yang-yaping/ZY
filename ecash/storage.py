import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .crypto import canonical

class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
    def connect(self):
        c = sqlite3.connect(self.path, timeout=20, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        c.execute('PRAGMA busy_timeout=20000')
        return c
    @contextmanager
    def tx(self):
        c = self.connect()
        try:
            c.execute('BEGIN IMMEDIATE')
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()
    def setup(self, sql):
        with self.connect() as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.executescript(sql)
        c.close()
    def rows(self, sql, args=()):
        c = self.connect()
        try:
            return [dict(x) for x in c.execute(sql, args)]
        finally:
            c.close()
    def put(self, key, obj):
        with self.tx() as c:
            c.execute('INSERT INTO objects(id,data) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data', (key, canonical(obj)))
    def get(self, key):
        r = self.rows('SELECT data FROM objects WHERE id=?', (key,))
        return json.loads(r[0]['data']) if r else None
