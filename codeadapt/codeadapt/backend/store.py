"""Durable raw-evidence and authentication store.

The brief requires that the exact execution outcome be reconstructable. An
in-memory record returned over HTTP does not satisfy that, so every submission
is written to SQLite before the response is built.

Design: the FULL record is kept as JSON, verbatim. The columns beside it exist
only so the research layer can filter without parsing every blob -- they are a
denormalised index, never the source of truth. Nothing is aggregated and no
score is stored; reduction is the research layer's job, not the store's.

Also provides durable storage for users, roles, and active sessions.

stdlib sqlite3 only. No ORM, no migrations server.
"""
import contextlib
import json
import os
import sqlite3
import threading

DB_PATH = os.environ.get(
    "SI_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "evidence.db"))

_lock = threading.Lock()   # global write lock for SQLite consistency

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id       TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK(role IN ('student', 'researcher', 'admin')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_users_username ON users(username);
CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);

CREATE TABLE IF NOT EXISTS sessions (
    session_id    TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token_hash    TEXT NOT NULL UNIQUE,
    csrf_token    TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_sessions_token_hash ON sessions(token_hash);
CREATE INDEX IF NOT EXISTS ix_sessions_user_id ON sessions(user_id);

CREATE TABLE IF NOT EXISTS submissions (
    submission_id        TEXT PRIMARY KEY,
    user_id              TEXT,               -- NULL for anonymous/legacy runs
    parent_submission_id TEXT,               -- links attempt chains
    problem_id           TEXT NOT NULL,
    concept              TEXT,
    compile_status       TEXT NOT NULL,
    fingerprint          TEXT,               -- NULL when compilation failed
    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
    limits_json          TEXT NOT NULL,      -- toolchain + limits actually used
    record_json          TEXT NOT NULL       -- the complete raw record, verbatim
);
CREATE INDEX IF NOT EXISTS ix_sub_problem ON submissions(problem_id);

CREATE TABLE IF NOT EXISTS test_results (
    submission_id     TEXT NOT NULL,
    test_id           TEXT NOT NULL,
    status            TEXT NOT NULL,    -- P | F | R
    execution_status  TEXT NOT NULL,    -- COMPLETED | TIMEOUT | CRASHED | ...
    expected_output   TEXT,
    actual_output     TEXT,
    raw_stdout        TEXT,
    exit_code         INTEGER,
    runtime_ms        REAL,
    memory_bytes      INTEGER,
    error             TEXT,
    PRIMARY KEY (submission_id, test_id)
);
CREATE INDEX IF NOT EXISTS ix_tr_status ON test_results(status);
"""


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextlib.contextmanager
def _session():
    """Context manager that guarantees connection is closed on exit."""
    conn = _connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _migrate(conn):
    """Safely apply schema migrations to existing databases without data loss."""
    info = [row["name"] for row in conn.execute("PRAGMA table_info(submissions)").fetchall()]
    if info:
        if "user_id" not in info:
            conn.execute("ALTER TABLE submissions ADD COLUMN user_id TEXT")
        if "parent_submission_id" not in info:
            conn.execute("ALTER TABLE submissions ADD COLUMN parent_submission_id TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_sub_user ON submissions(user_id)")


def init(path=None):
    global DB_PATH
    if path:
        DB_PATH = path
    with _lock, _session() as conn:
        conn.executescript(_SCHEMA)
        _migrate(conn)


def save(record, fingerprint=None, user_id=None, parent_submission_id=None):
    """Persist one submission and its per-test rows. Returns submission_id."""
    sid = record["submission_id"]
    uid = user_id or record.get("user_id")
    parent_id = parent_submission_id or record.get("parent_submission_id")
    # Keep user metadata on the verbatim record as well
    if uid and "user_id" not in record:
        record["user_id"] = uid
    if parent_id and "parent_submission_id" not in record:
        record["parent_submission_id"] = parent_id

    with _lock, _session() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO submissions "
            "(submission_id, user_id, parent_submission_id, problem_id, concept,"
            " compile_status, fingerprint, limits_json, record_json) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (sid, uid, parent_id, record["problem_id"], record.get("concept"),
             record["compile_status"], fingerprint,
             json.dumps(record["limits"]), json.dumps(record)))
        conn.execute("DELETE FROM test_results WHERE submission_id = ?", (sid,))
        conn.executemany(
            "INSERT INTO test_results (submission_id, test_id, status,"
            " execution_status, expected_output, actual_output, raw_stdout,"
            " exit_code, runtime_ms, memory_bytes, error)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [(sid, t["test_id"], t["status"], t["execution_status"],
              json.dumps(t["expected_output"]), json.dumps(t["actual_output"]),
              t.get("raw_stdout"), t.get("exit_code"), t.get("runtime_ms"),
              t.get("memory_bytes"), t.get("error"))
             for t in record["tests"]])
    return sid


def load(submission_id):
    """Return the complete original record, byte-for-byte as executed."""
    with _session() as conn:
        row = conn.execute(
            "SELECT record_json FROM submissions WHERE submission_id = ?",
            (submission_id,)).fetchone()
    return json.loads(row["record_json"]) if row else None


def get_submission_meta(submission_id):
    """Return denormalized metadata for ownership and authorization checks."""
    with _session() as conn:
        row = conn.execute(
            "SELECT submission_id, user_id, parent_submission_id, problem_id, "
            "compile_status, fingerprint, created_at "
            "FROM submissions WHERE submission_id = ?",
            (submission_id,)).fetchone()
    return dict(row) if row else None


def get_submission_chain(submission_id):
    """Return the chain of related attempts (root attempt + follow-ups) ordered chronologically."""
    with _session() as conn:
        # Step 1: Walk backwards to find root
        curr_id = submission_id
        visited = {curr_id}
        while True:
            row = conn.execute(
                "SELECT submission_id, parent_submission_id FROM submissions WHERE submission_id = ?",
                (curr_id,)).fetchone()
            if not row or not row["parent_submission_id"]:
                break
            parent_id = row["parent_submission_id"]
            if parent_id in visited:
                break
            visited.add(parent_id)
            curr_id = parent_id
        root_id = curr_id

        # Step 2: Walk forwards from root collecting all children
        chain_ids = [root_id]
        queue = [root_id]
        visited = {root_id}
        while queue:
            parent = queue.pop(0)
            children = conn.execute(
                "SELECT submission_id FROM submissions WHERE parent_submission_id = ? ORDER BY created_at ASC",
                (parent,)).fetchall()
            for child in children:
                cid = child["submission_id"]
                if cid not in visited:
                    visited.add(cid)
                    chain_ids.append(cid)
                    queue.append(cid)

        # Step 3: Fetch metadata for all attempts in chain ordered by created_at
        placeholders = ",".join("?" for _ in chain_ids)
        rows = conn.execute(
            f"SELECT submission_id, user_id, parent_submission_id, problem_id, "
            f"compile_status, fingerprint, created_at FROM submissions "
            f"WHERE submission_id IN ({placeholders}) ORDER BY created_at ASC",
            chain_ids).fetchall()
        return [dict(r) for r in rows]


def list_submissions(user_id=None, problem_id=None, compile_status=None, search=None, limit=50, offset=0):
    """Query submissions with optional user, problem, status, or keyword filtering."""
    query = "SELECT s.submission_id, s.user_id, s.problem_id, s.compile_status, s.fingerprint, s.created_at, " \
            "s.parent_submission_id, u.username FROM submissions s " \
            "LEFT JOIN users u ON s.user_id = u.user_id WHERE 1=1"
    params = []
    if user_id:
        query += " AND s.user_id = ?"
        params.append(user_id)
    if problem_id:
        query += " AND s.problem_id = ?"
        params.append(problem_id)
    if compile_status:
        query += " AND s.compile_status = ?"
        params.append(compile_status)
    if search:
        query += " AND (s.submission_id LIKE ? OR s.problem_id LIKE ? OR u.username LIKE ?)"
        s_param = f"%{search}%"
        params.extend([s_param, s_param, s_param])
    query += " ORDER BY s.created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with _session() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def count_submissions(user_id=None, problem_id=None, compile_status=None, search=None):
    """Return total count of submissions matching the filter criteria."""
    query = "SELECT COUNT(*) as count FROM submissions s LEFT JOIN users u ON s.user_id = u.user_id WHERE 1=1"
    params = []
    if user_id:
        query += " AND s.user_id = ?"
        params.append(user_id)
    if problem_id:
        query += " AND s.problem_id = ?"
        params.append(problem_id)
    if compile_status:
        query += " AND s.compile_status = ?"
        params.append(compile_status)
    if search:
        query += " AND (s.submission_id LIKE ? OR s.problem_id LIKE ? OR u.username LIKE ?)"
        s_param = f"%{search}%"
        params.extend([s_param, s_param, s_param])

    with _session() as conn:
        row = conn.execute(query, params).fetchone()
        return row["count"] if row else 0


def fingerprints(problem_id):
    """Every observed P/F/R row for a problem, newest first. Compile failures
    appear with a NULL fingerprint and are NOT silently dropped.
    """
    with _session() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT submission_id, fingerprint, compile_status, created_at, user_id,"
            " json_extract(limits_json, '$.instrument_hash') AS instrument_hash"
            " FROM submissions WHERE problem_id = ? ORDER BY created_at DESC",
            (problem_id,))]
