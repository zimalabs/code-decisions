-- engram index schema: derived from markdown signal files
-- SQLite 3.35+ required (for FTS5 and datetime functions)
-- This database is DERIVED — delete it anytime, rebuilt from .engram/ files

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK(type IN ('decision','finding','issue')),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL DEFAULT '',
    date TEXT NOT NULL DEFAULT (date('now')),
    file TEXT NOT NULL DEFAULT '',
    private INTEGER NOT NULL DEFAULT 0,
    excerpt TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    supersedes TEXT NOT NULL DEFAULT '',
    file_stem TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS links (
    source_file TEXT NOT NULL,
    target_file TEXT NOT NULL,
    rel_type TEXT NOT NULL CHECK(rel_type IN ('supersedes','related','blocks','blocked-by')),
    PRIMARY KEY (source_file, target_file, rel_type)
);

CREATE VIRTUAL TABLE IF NOT EXISTS signals_fts USING fts5(
    title, content, tags, content=signals, content_rowid=id
);

CREATE TRIGGER IF NOT EXISTS signals_ai AFTER INSERT ON signals BEGIN
    INSERT INTO signals_fts(rowid, title, content, tags)
    VALUES (new.id, new.title, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS signals_au AFTER UPDATE ON signals BEGIN
    INSERT INTO signals_fts(signals_fts, rowid, title, content, tags)
    VALUES ('delete', old.id, old.title, old.content, old.tags);
    INSERT INTO signals_fts(rowid, title, content, tags)
    VALUES (new.id, new.title, new.content, new.tags);
END;

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
