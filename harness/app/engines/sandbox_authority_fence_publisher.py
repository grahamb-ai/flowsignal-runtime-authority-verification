"""Reference authoritative-state publisher for the sandbox actuator ledger.

A *trusted test harness* publishes versions observed from FlowSignal's source
state. Publication is intentionally explicit, not automatic or production-
authenticated. This cannot attest cross-host source freshness or resist admin
rollback. The actuator fails closed if no publication exists.
"""
import sqlite3
import time
from pathlib import Path

def publish_authority_version(db_path, version):
    path=Path(db_path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(path,timeout=5,isolation_level=None) as con:
        con.execute("BEGIN IMMEDIATE")
        con.execute("CREATE TABLE IF NOT EXISTS authority_fence ("
                    "singleton INTEGER PRIMARY KEY CHECK(singleton=1),"
                    "version INTEGER NOT NULL, observed_at REAL NOT NULL)")
        row=con.execute("SELECT version,observed_at FROM authority_fence WHERE singleton=1").fetchone()
        if row is not None and version < row[0]:
            con.execute("ROLLBACK")
            return False
        con.execute("INSERT INTO authority_fence(singleton,version,observed_at) VALUES(1,?,?) "
                    "ON CONFLICT(singleton) DO UPDATE SET "
                    "version=excluded.version,observed_at=excluded.observed_at",
                    (version,time.time()))
        con.execute("COMMIT")
    return True
