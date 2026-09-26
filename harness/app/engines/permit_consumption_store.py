from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path


_DEFAULT_STORE_PATH = Path(".flowsignal-runtime/permit_consumption.sqlite3")
_DEFAULT_OUTCOME_STORE_PATH = Path(".flowsignal-runtime/consequence_outcomes.sqlite3")
_BUSY_RETRY_ATTEMPTS = 100
_BUSY_RETRY_DELAY_SECONDS = 0.05


def _store_path() -> Path:
    configured = os.environ.get("FLOWSIGNAL_PERMIT_CONSUMPTION_STORE")
    return Path(configured) if configured else _DEFAULT_STORE_PATH


def _outcome_store_path() -> Path:
    configured = os.environ.get("FLOWSIGNAL_CONSEQUENCE_OUTCOME_STORE")
    return Path(configured) if configured else _DEFAULT_OUTCOME_STORE_PATH


def _is_busy(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return "locked" in message or "busy" in message


def _execute_with_busy_retry(connection: sqlite3.Connection, statement: str) -> None:
    """Execute store-initialization SQL while tolerating bounded SQLite lock races."""
    for attempt in range(_BUSY_RETRY_ATTEMPTS):
        try:
            connection.execute(statement)
            return
        except sqlite3.OperationalError as exc:
            if not _is_busy(exc):
                raise
            if attempt == _BUSY_RETRY_ATTEMPTS - 1:
                raise
            time.sleep(_BUSY_RETRY_DELAY_SECONDS)


def _connect() -> sqlite3.Connection:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5.0, isolation_level=None)
    connection.execute("PRAGMA busy_timeout=5000")
    _execute_with_busy_retry(connection, "PRAGMA journal_mode=WAL")
    _execute_with_busy_retry(
        connection,
        """
        CREATE TABLE IF NOT EXISTS consumed_execution_permits (
            signature TEXT PRIMARY KEY,
            consumed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )
    return connection


def consume_execution_permit_once(signature: str) -> bool:
    """Atomically record one permit signature in the reference durable store."""
    connection = _connect()
    try:
        cursor = connection.execute(
            "INSERT OR IGNORE INTO consumed_execution_permits(signature) VALUES (?)",
            (signature,),
        )
        return cursor.rowcount == 1
    finally:
        connection.close()


def _consume_and_begin_once_attempt(
    *,
    permit_path: Path,
    outcome_path: Path,
    signature: str,
    action_binding_hash: str,
) -> bool:
    connection = sqlite3.connect(permit_path, timeout=5.0, isolation_level=None)
    try:
        connection.execute("PRAGMA busy_timeout=5000")
        _execute_with_busy_retry(connection, "PRAGMA journal_mode=DELETE")
        connection.execute("ATTACH DATABASE ? AS outcome_db", (str(outcome_path),))
        _execute_with_busy_retry(connection, "PRAGMA outcome_db.journal_mode=DELETE")
        _execute_with_busy_retry(
            connection,
            """
            CREATE TABLE IF NOT EXISTS consumed_execution_permits (
                signature TEXT PRIMARY KEY,
                consumed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
        )
        _execute_with_busy_retry(
            connection,
            """
            CREATE TABLE IF NOT EXISTS outcome_db.consequence_outcomes (
                permit_signature TEXT PRIMARY KEY,
                action_binding_hash TEXT NOT NULL,
                outcome TEXT NOT NULL,
                recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
        )

        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            "INSERT OR IGNORE INTO consumed_execution_permits(signature) VALUES (?)",
            (signature,),
        )
        if cursor.rowcount != 1:
            connection.execute("ROLLBACK")
            return False

        connection.execute(
            """
            INSERT INTO outcome_db.consequence_outcomes(
                permit_signature,
                action_binding_hash,
                outcome
            ) VALUES (?, ?, 'CONSEQUENCE_OUTCOME_UNRESOLVED')
            """,
            (signature, action_binding_hash),
        )
        connection.execute("COMMIT")
        return True
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def consume_execution_permit_and_begin_outcome_once(
    signature: str,
    action_binding_hash: str,
) -> bool:
    """Establish consumption and initial execution state as one SQLite transaction.

    PMQ-002.9 demonstrated that committing permit consumption before creating the
    first consequence-outcome row leaves a crash window with a consumed permit
    and no recoverable execution state. This reference-MVP operation attaches the
    configured outcome database and commits both records in one transaction.

    The bounded retry around the complete attached-database attempt preserves the
    already-qualified PMQ-002.2 two-process race when concurrent processes are
    initializing or entering this local SQLite transaction. A retry starts with a
    fresh connection so partially completed ATTACH/PRAGMA setup is not reused.

    Returns True only for the first successful permit consumption. A duplicate
    signature returns False without replacing the existing execution outcome.

    This is a bounded SQLite reference mechanism. It does not establish
    production distributed transactions, database HA/failover, cross-host
    atomicity, external payment idempotency, fsync/power-loss guarantees or
    infrastructure trust isolation.
    """
    permit_path = _store_path()
    outcome_path = _outcome_store_path()
    permit_path.parent.mkdir(parents=True, exist_ok=True)
    outcome_path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(_BUSY_RETRY_ATTEMPTS):
        try:
            return _consume_and_begin_once_attempt(
                permit_path=permit_path,
                outcome_path=outcome_path,
                signature=signature,
                action_binding_hash=action_binding_hash,
            )
        except sqlite3.OperationalError as exc:
            if not _is_busy(exc):
                raise
            if attempt == _BUSY_RETRY_ATTEMPTS - 1:
                raise
            time.sleep(_BUSY_RETRY_DELAY_SECONDS)

    raise AssertionError("unreachable")
