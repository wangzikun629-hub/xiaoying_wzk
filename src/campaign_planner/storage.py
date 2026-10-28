"""One authoritative SQLite snapshot, with atomic final-plan commits."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .schemas import canonical, digest


class BusyRequest(Exception):
    pass


class Storage:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # LangGraph dispatches tools to worker threads; Engine serializes access.
        self.conn = sqlite3.connect(self.path, timeout=5, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY, state TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL,
                                           content TEXT NOT NULL);
        """)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def get(self, request_id):
        row = self.conn.execute("SELECT state FROM requests WHERE id=?", (request_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, state):
        with self.conn:
            self.conn.execute(
                "INSERT INTO requests VALUES(?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state",
                (state["request"]["request_id"], canonical(state)),
            )

    def save_plan(self, state, plan):
        # Plan and completed state are one transaction, never a file-exists heuristic.
        with self.conn:
            self.conn.execute(
                "INSERT INTO plans VALUES(?,?,?)",
                (plan["plan_id"], state["request"]["request_id"], canonical(plan)),
            )
            self.conn.execute(
                "UPDATE requests SET state=? WHERE id=?", (canonical(state), state["request"]["request_id"])
            )

    def plan(self, request_id):
        row = self.conn.execute("SELECT content FROM plans WHERE request_id=?", (request_id,)).fetchone()
        return json.loads(row[0]) if row else None

    @contextmanager
    def request_lock(self, request_id):
        # OS locks are released on process exit, unlike a permanent 'running' DB flag.
        lock_dir = self.path.parent / ".locks"
        lock_dir.mkdir(exist_ok=True)
        name = digest([str(self.path), request_id]) + ".lock"
        with (lock_dir / name).open("a+b") as handle:
            handle.seek(0)
            handle.write(b"0")
            handle.flush()
            handle.seek(0)
            try:
                if __import__("os").name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise BusyRequest(request_id) from exc
            try:
                yield
            finally:
                handle.seek(0)
                if __import__("os").name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle, fcntl.LOCK_UN)
