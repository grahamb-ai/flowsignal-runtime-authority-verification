"""Surviving source-owned reference commitment anchor qualification.

Two distinct authority database copies use one surviving anchor. The anchor
is not restored in the test. Simulates local rollback and split-source use;
does not show survivability against rollback of the anchor or external effects.
"""
from contextlib import closing
import json,os,shutil,sqlite3
import pytest

from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from test_fs_raw_denial_001_online_authority import start,stop
from test_fs_raw_denial_001_parallel_contention import source_env,actuator_env,grant_payload
from test_fs_raw_denial_001_rai_external_actuator import post

@pytest.fixture(autouse=True)
def reset_usage():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

def start_group(authority_db,anchor_db):
    env=source_env(authority_db)
    env["FS_RAI_SURVIVING_ANCHOR_DB"]=str(anchor_db)
    source,url=start("fs_raw_denial_001_surviving_anchor_source.py",env)
    executor,executor_url=start("fs_raw_denial_001_contention_server.py",
        actuator_env(authority_db,url))
    return (source,executor),(executor_url,authority_db)

def stop_group(group):
    for p in group:
        if p.poll() is None:stop(p)

def commitments(anchor):
    with closing(sqlite3.connect(f"file:{anchor}?mode=ro",uri=True)) as c:
        return c.execute("SELECT permit_signature,action_binding_hash,route "
                         "FROM committed_effects").fetchall()

def exported_grant(tmp_path):
    permit,grantfile=grant_payload(tmp_path)
    return permit,json.loads(grantfile.read_text())["envelope"]

def test_source_database_rollback_cannot_reconsume_anchored_grant(tmp_path):
    main=tmp_path/"authority.sqlite3"
    anchor=tmp_path/"surviving-anchor.sqlite3"
    snapshot=tmp_path/"old-authority.sqlite3"
    permit,envelope=exported_grant(tmp_path)
    processes,pair=start_group(main,anchor)
    try:
        shutil.copyfile(main,snapshot)
        code,response=post(pair,"/execute-a",envelope,permit.action_binding_hash)
        assert (code,response["status"])==(200,"CONSEQUENCE_FORMED")
        before=commitments(anchor)
        assert before==[(permit.signature,permit.action_binding_hash,"/execute-a")]
    finally:
        stop_group(processes)
    shutil.copyfile(snapshot,main)
    processes,pair=start_group(main,anchor)
    try:
        code,response=post(pair,"/execute-b",envelope,permit.action_binding_hash)
        assert (code,response["status"])==(409,"REPLAY_REFUSED")
        assert commitments(anchor)==before
    finally:
        stop_group(processes)

def test_two_independent_source_dbs_sharing_anchor_commit_once(tmp_path):
    db1=tmp_path/"instance-a.sqlite3"
    db2=tmp_path/"instance-b.sqlite3"
    anchor=tmp_path/"surviving-anchor.sqlite3"
    permit,envelope=exported_grant(tmp_path)
    group1,pair1=start_group(db1,anchor)
    group2,pair2=start_group(db2,anchor)
    try:
        first=post(pair1,"/execute-a",envelope,permit.action_binding_hash)
        second=post(pair2,"/execute-b",envelope,permit.action_binding_hash)
        assert (first[0],second[0])==(200,409),(first,second)
        assert commitments(anchor)==[
            (permit.signature,permit.action_binding_hash,"/execute-a")]
    finally:
        stop_group(group1)
        stop_group(group2)

def test_anchor_restoration_remains_an_explicit_unresolved_gap(tmp_path):
    db=tmp_path/"authority.sqlite3"
    anchor=tmp_path/"surviving-anchor.sqlite3"
    saved=tmp_path/"pre-consumption-anchor.sqlite3"
    permit,envelope=exported_grant(tmp_path)
    group,pair=start_group(db,anchor)
    try:
        shutil.copyfile(anchor,saved)
        assert post(pair,"/execute-a",envelope,permit.action_binding_hash)[0]==200
        assert len(commitments(anchor))==1
    finally:
        stop_group(group)
    shutil.copyfile(saved,anchor)
    group,pair=start_group(db,anchor)
    try:
        code,response=post(pair,"/execute-b",envelope,permit.action_binding_hash)
        assert (code,response["status"])==(200,"CONSEQUENCE_FORMED")
        assert len(commitments(anchor))==1
        # Passing characterization of remaining ALL-STORES rollback exposure.
    finally:
        stop_group(group)
