from __future__ import annotations

import os
import sqlite3
from pathlib import Path


_DEFAULT_STORE_PATH = Path(".flowsignal-runtime/consequence_outcomes.sqlite3")


def _store_path() -> Path:
    configured = os.environ.get("FLOWSIGNAL_CONSEQUENCE_OUTCOME_STORE")
    return Path(configured) if configured else _DEFAULT_STORE_PATH


def _connect() -> sqlite3.Connection:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5.0, isolation_level=None)
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS consequence_outcomes (
            permit_signature TEXT PRIMARY KEY,
            action_binding_hash TEXT NOT NULL,
            outcome TEXT NOT NULL,
            recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return connection


def record_consequence_outcome(
    *,
    permit_signature: str,
    action_binding_hash: str,
    outcome: str,
) -> None:
    """Persist the represented consequence outcome before returning formation.

    The permit signature is the durable idempotency key for the represented
    execution. This is an MVP/reference persistence mechanism only; it does not
    establish production HA, replication, write-once storage or external
    settlement evidence.
    """
    connection = _connect()
    try:
        connection.execute(
            """
            INSERT INTO consequence_outcomes(
                permit_signature,
                action_binding_hash,
                outcome
            ) VALUES (?, ?, ?)
            ON CONFLICT(permit_signature) DO UPDATE SET
                action_binding_hash = excluded.action_binding_hash,
                outcome = excluded.outcome
            """,
            (permit_signature, action_binding_hash, outcome),
        )
    finally:
        connection.close()


def get_consequence_outcome(
    permit_signature: str,
    action_binding_hash: str,
):
    """Read the currently represented outcome for one exact execution."""
    connection = _connect()
    try:
        row = connection.execute(
            """
            SELECT outcome
            FROM consequence_outcomes
            WHERE permit_signature = ? AND action_binding_hash = ?
            """,
            (permit_signature, action_binding_hash),
        ).fetchone()
        if row is None:
            return None
        from types import SimpleNamespace
        return SimpleNamespace(outcome=row[0])
    finally:
        connection.close()
