import sqlite3
from pathlib import Path

from flask import current_app, g


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS media (
    id TEXT PRIMARY KEY,
    original_path TEXT NOT NULL,
    normalized_path TEXT,
    type TEXT NOT NULL CHECK(type IN ('photo', 'video')),
    created_at TEXT NOT NULL,
    duration_seconds REAL,
    width INTEGER,
    height INTEGER,
    thumb_path TEXT,
    status TEXT NOT NULL CHECK(status IN ('ready', 'processing', 'failed')),
    error TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_media_original_path ON media(original_path);
CREATE INDEX IF NOT EXISTS idx_media_status ON media(status);

CREATE TABLE IF NOT EXISTS albums (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS album_items (
    album_id TEXT NOT NULL,
    media_id TEXT NOT NULL,
    sort_index INTEGER NOT NULL,
    PRIMARY KEY (album_id, media_id),
    FOREIGN KEY (album_id) REFERENCES albums(id) ON DELETE CASCADE,
    FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_album_items_order ON album_items(album_id, sort_index);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS player_state (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    active_album_id TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (active_album_id) REFERENCES albums(id)
);

INSERT OR IGNORE INTO player_state (id, active_album_id, updated_at)
VALUES (1, NULL, datetime('now'));
"""


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        db_path = Path(current_app.config["DB_PATH"])
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(_error=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    db.executescript(SCHEMA_SQL)
    db.commit()


def init_app(app) -> None:
    app.teardown_appcontext(close_db)

    @app.cli.command("init-db")
    def init_db_command() -> None:
        init_db()
        print("Initialized database")
