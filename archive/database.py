import sqlite3
from contextlib import contextmanager

SCHEMA_VERSION = 1


class Database:
    def __init__(self, path):
        self.path = str(path)
        self._connection = sqlite3.connect(self.path, isolation_level=None)
        self._connection.execute('PRAGMA foreign_keys=ON')
        try:
            self.initialize()
        except BaseException:
            self._connection.close()
            raise

    def connect(self):
        return self._connection

    def initialize(self):
        c = self.connect()
        version = c.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            raise ValueError('unsupported database schema')
        statements = [
            'CREATE TABLE IF NOT EXISTS revisions (measurement_id TEXT NOT NULL, rev INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(measurement_id,rev))',
            'CREATE TABLE IF NOT EXISTS heads (measurement_id TEXT PRIMARY KEY, rev INTEGER NOT NULL, FOREIGN KEY(measurement_id,rev) REFERENCES revisions(measurement_id,rev))',
            'CREATE TABLE IF NOT EXISTS blobs (id TEXT PRIMARY KEY, body TEXT NOT NULL, digest TEXT NOT NULL)',
            'CREATE TABLE IF NOT EXISTS catalog (id TEXT PRIMARY KEY REFERENCES blobs(id), kind TEXT NOT NULL)',
            'CREATE TABLE IF NOT EXISTS edges (child TEXT NOT NULL REFERENCES blobs(id), position INTEGER NOT NULL, parent TEXT NOT NULL REFERENCES catalog(id), PRIMARY KEY(child,position))',
            'CREATE TABLE IF NOT EXISTS models (name TEXT NOT NULL, rev INTEGER NOT NULL, artifact TEXT NOT NULL REFERENCES catalog(id), PRIMARY KEY(name,rev))',
        ]
        with self.transaction():
            for statement in statements:
                c.execute(statement)
            c.execute('PRAGMA user_version=1')

    @contextmanager
    def transaction(self):
        c = self.connect()
        if c.in_transaction:
            raise RuntimeError('nested transaction is not supported')
        c.execute('BEGIN IMMEDIATE')
        try:
            yield c
            c.execute('COMMIT')
        except BaseException:
            if c.in_transaction:
                c.execute('ROLLBACK')
            raise

    def close(self):
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
