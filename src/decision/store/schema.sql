CREATE TABLE IF NOT EXISTS decisions (
    slug TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    date TEXT NOT NULL,
    description TEXT,
    tags TEXT,
    affects TEXT,
    body TEXT NOT NULL,
    excerpt TEXT,
    mtime REAL NOT NULL DEFAULT 0
);

CREATE VIRTUAL TABLE IF NOT EXISTS decisions_fts USING fts5(
    title, body, tags, affects, description,
    content='decisions',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS decisions_ai AFTER INSERT ON decisions BEGIN
    INSERT INTO decisions_fts(rowid, title, body, tags, affects, description)
    VALUES (new.rowid, new.title, new.body, new.tags, new.affects, new.description);
END;

CREATE TRIGGER IF NOT EXISTS decisions_ad AFTER DELETE ON decisions BEGIN
    INSERT INTO decisions_fts(decisions_fts, rowid, title, body, tags, affects, description)
    VALUES ('delete', old.rowid, old.title, old.body, old.tags, old.affects, old.description);
END;

CREATE TRIGGER IF NOT EXISTS decisions_au AFTER UPDATE ON decisions BEGIN
    INSERT INTO decisions_fts(decisions_fts, rowid, title, body, tags, affects, description)
    VALUES ('delete', old.rowid, old.title, old.body, old.tags, old.affects, old.description);
    INSERT INTO decisions_fts(rowid, title, body, tags, affects, description)
    VALUES (new.rowid, new.title, new.body, new.tags, new.affects, new.description);
END;
