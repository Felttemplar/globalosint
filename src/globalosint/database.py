"""Inicialização e conexões SQLite."""

import os
import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('institutional','media','social','research','other')),
    languages_json TEXT NOT NULL,
    axes_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate','approved','rejected')),
    reliability_score INTEGER CHECK (reliability_score BETWEEN 0 AND 100),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT,
    axis TEXT NOT NULL CHECK (axis IN ('energy','conflict','economy','climate','cyber','health')),
    classification TEXT NOT NULL CHECK (classification IN ('fact','report','inference','hypothesis')),
    confidence_score INTEGER CHECK (confidence_score BETWEEN 0 AND 100),
    severity TEXT CHECK (severity IN ('low','moderate','high','critical')),
    location TEXT,
    occurred_at TEXT,
    status TEXT NOT NULL DEFAULT 'investigating' CHECK (status IN ('investigating','confirmed','closed')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES events(id),
    source_id INTEGER NOT NULL REFERENCES sources(id),
    url TEXT NOT NULL,
    published_at TEXT,
    collected_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    content_hash TEXT,
    excerpt TEXT,
    origin_group TEXT,
    assessment TEXT NOT NULL DEFAULT 'unassessed' CHECK (assessment IN ('supporting','contradicting','unassessed')),
    UNIQUE(event_id, url)
);
CREATE TABLE IF NOT EXISTS event_history (
    id INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES events(id),
    changed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    reason TEXT
);
CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','succeeded','partial','failed')),
    collector TEXT NOT NULL,
    records_seen INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT
);
CREATE INDEX IF NOT EXISTS idx_sources_status ON sources(status);
CREATE INDEX IF NOT EXISTS idx_events_axis_status ON events(axis, status);
CREATE INDEX IF NOT EXISTS idx_evidence_event ON evidence(event_id);
CREATE INDEX IF NOT EXISTS idx_evidence_source ON evidence(source_id);
"""


def database_path() -> Path:
    configured = os.environ.get("GLOBALOSINT_DB_PATH")
    if configured:
        return Path(configured).expanduser()
    return Path("data") / "globalosint.sqlite3"


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    target = Path(path) if path is not None else database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize(path: Path | str | None = None) -> Path:
    target = Path(path) if path is not None else database_path()
    connection = connect(target)
    try:
        connection.executescript(SCHEMA)
    finally:
        connection.close()
    return target
