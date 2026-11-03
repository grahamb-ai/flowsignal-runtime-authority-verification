"""FS-RAW-DENIAL-001 first RED: restoration of the sole authority ledger.

A saved pre-consumption local SQLite image replaces the original source DB
after the first synthetic commit. An independent test-owned witness DB is NOT
restored and records both actual HTTP acceptances. No payments or production.
"""
from contextlib import closing
from pathlib import Path
import json,shutil,sqlite3
import pytest

from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from test_fs_raw_denial_001_single_authority_ledger import start_pair,close,observed
from test_fs_raw_denial_001_parallel_contention import grant_payload
from test_fs_raw_denial_001_rai_external_actuator import post

@pytest.fixture(autouse=True)
def reset_authority():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

def observe(witness_db,signature,route):
    with closing(sqlite3.connect(str(witness_db))) as c:
        c.execute("CREATE TABLE IF NOT EXISTS observations "
                  "(id INTEGER PRIMARY KEY, signature TEXT NOT NULL, route TEXT NOT NULL)")
        c.execute("INSERT INTO observations(signature,route) VALUES(?,?)",(signature,route))
        c.commit()

def observed_outside_rollback(witness_db):
    with closing(sqlite3.connect(str(witness_db))) as c:
        return c.execute("SELECT signature,route FROM observations ORDER BY id").fetchall()

def test_restored_canonical_db_cannot_reissue_consumed_grant_first_red(tmp_path):
    primary=tmp_path/"canonical.sqlite3"
    saved=tmp_path/"pre-commit-backup.sqlite3"
    witness_db=tmp_path/"outside-observer.sqlite3"
    permit,grant_path=grant_payload(tmp_path)
    assertion=json.loads(grant_path.read_text())["envelope"]
    source,url,actuator,actuator_url=start_pair(primary)
    try:
        # Safe snapshot before any consumption, while no transaction is active.
        shutil.copyfile(primary,saved)
        first=post((actuator_url,primary),"/execute-a",assertion,
                   permit.action_binding_hash)
        assert first[0]==200,first
        observe(witness_db,permit.signature,"a")
        assert len(observed(primary))==1
    finally:
        close(source,actuator)
    # Restore ONLY the canonical source state; independent observations survive.
    shutil.copyfile(saved,primary)
    source,url,actuator,actuator_url=start_pair(primary)
    try:
        second=post((actuator_url,primary),"/execute-b",assertion,
                    permit.action_binding_hash)
        if second[0]==200:
            observe(witness_db,permit.signature,"b")
        independent=observed_outside_rollback(witness_db)
        assert len(independent)==1, (
            "FIRST RED: restored source database forgot a prior commitment "
            "and accepted a second reference consequence. Independent witness "
            f"observations={independent}; response={second}."
        )
    finally:
        close(source,actuator)
