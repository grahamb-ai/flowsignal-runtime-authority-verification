"""FS-RAW-DENIAL-001 dual-store restoration FIRST RED.

Both authority state and its local anchor are replaced with pre-commit copies.
An independent test witness DB retains the previously accepted operation.
This deliberately demonstrates bounded local rollback vulnerability.
"""
from contextlib import closing
import json,shutil,sqlite3
import pytest
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from test_fs_raw_denial_001_surviving_anchor import start_group,stop_group
from test_fs_raw_denial_001_parallel_contention import grant_payload
from test_fs_raw_denial_001_rai_external_actuator import post

@pytest.fixture(autouse=True)
def isolated_usage():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

def record_outside(db,signature,route):
    with closing(sqlite3.connect(db)) as con:
        con.execute("CREATE TABLE IF NOT EXISTS witnessed (id INTEGER PRIMARY KEY, signature TEXT, route TEXT)")
        con.execute("INSERT INTO witnessed(signature,route) VALUES(?,?)",(signature,route))
        con.commit()

def witnessed(db):
    with closing(sqlite3.connect(db)) as con:
        return con.execute("SELECT signature,route FROM witnessed ORDER BY id").fetchall()

def test_restoring_both_local_stores_does_not_erase_prior_exercise_first_red(tmp_path):
    source_db=tmp_path/"source.sqlite3"
    anchor=tmp_path/"anchor.sqlite3"
    witness=tmp_path/"independent-witness.sqlite3"
    source_copy=tmp_path/"source-old.sqlite3"
    anchor_copy=tmp_path/"anchor-old.sqlite3"
    permit,grant_path=grant_payload(tmp_path)
    assertion=json.loads(grant_path.read_text())["envelope"]

    processes,pair=start_group(source_db,anchor)
    try:
        # Both initial snapshots precede the represented consequence.
        shutil.copyfile(source_db,source_copy)
        shutil.copyfile(anchor,anchor_copy)
        result=post(pair,"/execute-a",assertion,permit.action_binding_hash)
        assert result[0]==200,result
        record_outside(witness,permit.signature,"/execute-a")
    finally:
        stop_group(processes)

    shutil.copyfile(source_copy,source_db)
    shutil.copyfile(anchor_copy,anchor)
    processes,pair=start_group(source_db,anchor)
    try:
        replay=post(pair,"/execute-b",assertion,permit.action_binding_hash)
        if replay[0]==200:
            record_outside(witness,permit.signature,"/execute-b")
        rows=witnessed(witness)
        assert len(rows)==1, (
            "FIRST RED: restoring both authority and local anchor lets "
            "previously used permit commit again. Independent witness="
            f"{rows}; HTTP={replay}"
        )
    finally:
        stop_group(processes)
