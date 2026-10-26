"""Async SQLite connections and idempotent schema initialization."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS resources (
    resource_key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS access_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    resource_key TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('READ', 'WRITE')),
    version INTEGER NOT NULL,
    timestamp TEXT
);
CREATE TABLE IF NOT EXISTS dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    resource_key TEXT NOT NULL,
    read_version INTEGER NOT NULL,
    timestamp TEXT
);
CREATE TABLE IF NOT EXISTS conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    node_id TEXT,
    resource_key TEXT NOT NULL,
    expected_version INTEGER NOT NULL,
    actual_version INTEGER NOT NULL,
    semantic_result TEXT,
    confidence REAL,
    timestamp TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    scenario_id TEXT,
    protocol TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    success INTEGER,
    latency_ms REAL,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    auditor_tokens INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0,
    tool_call_count INTEGER DEFAULT 0,
    conflict_count INTEGER DEFAULT 0,
    semantic_conflict_count INTEGER DEFAULT 0,
    rerun_node_count INTEGER DEFAULT 0,
    preserved_node_count INTEGER DEFAULT 0,
    wasted_tokens INTEGER DEFAULT 0,
    recovery_latency_ms REAL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS access_logs_run ON access_logs(run_id);
CREATE INDEX IF NOT EXISTS dependencies_run ON dependencies(run_id);
CREATE INDEX IF NOT EXISTS conflicts_run ON conflicts(run_id);
"""


class Database:
    """Open short-lived connections; no shared connection or in-memory lock."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        async with aiosqlite.connect(self.path, timeout=10) as connection:
            connection.row_factory = aiosqlite.Row
            await connection.execute("PRAGMA foreign_keys = ON")
            yield connection

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        """Reserve SQLite's writer for a tool operation and its provenance.

        The reservation lasts only through database I/O, never through worker
        reasoning. It also avoids read-to-write lock upgrade races when logging
        the exact snapshot returned by a read.
        """
        async with self.connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise


async def init_db(database_path: str | Path | None = None) -> None:
    """Create the parent directory and every table without altering existing rows."""
    if database_path is None:
        from app.config import Settings

        database_path = Settings().database_path
    database = Database(database_path)
    database.path.parent.mkdir(parents=True, exist_ok=True)
    async with database.connect() as connection:
        await connection.execute("PRAGMA journal_mode = WAL")
        await connection.executescript(SCHEMA)
        await connection.commit()
