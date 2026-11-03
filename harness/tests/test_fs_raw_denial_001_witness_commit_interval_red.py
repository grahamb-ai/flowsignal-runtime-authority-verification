"""FIRST RED: authority revoked after witness-side online verification,
before its separate SQLite effect write. No actual financial consequence.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from pathlib import Path
import json,os,sqlite3,time
import pytest

from app.engines.authority_store import advance_authority_state_version
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from test_fs_raw_denial_001_online_authority import (
    setup,issued,advance_online,start,stop
)
from test_fs_raw_denial_001_rai_external_actuator import KEY
from test_fs_raw_denial_001_independent_witness import TOKEN

@pytest.fixture(autouse=True)
def isolate_usage():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

def post_witness(url,permit,grant):
    body=json.dumps({"envelope":grant,
        "action_binding_hash":permit.action_binding_hash,
        "route":"/execute-b"}).encode()
    req=Request(url+"/commit",data=body,method="POST",
        headers={"Content-Type":"application/json",
                 "X-Witness-Commit-Token":TOKEN})
    try:
        with urlopen(req,timeout=7) as r:
            return r.status,json.loads(r.read())
    except HTTPError as r:
        return r.code,json.loads(r.read())

def count(db):
    with closing(sqlite3.connect(f"file:{db}?mode=ro",uri=True)) as c:
        return c.execute("SELECT count(*) FROM external_effects").fetchone()[0]

def test_revocation_between_witness_check_and_effect_must_refuse(setup,tmp_path):
    permit,grant=issued()
    db=tmp_path/"independent-effect.sqlite3"
    barrier=tmp_path/"pause"
    env=os.environ.copy()
    env.update(FS_RAI_WITNESS_DB=str(db),
        FS_RAI_WITNESS_COMMIT_TOKEN=TOKEN,
        FS_RAI_EXTERNAL_LEDGER=str(db),
        FS_RAI_BRIDGE_KEY=KEY.decode(),
        FS_RAI_WITNESS_AUTHORITY_URL=setup["source_url"],
        FS_RAI_WITNESS_AUTHORITY_READ_TOKEN="source-read-test-key",
        FS_RAI_WITNESS_COMMIT_BARRIER=str(barrier))
    process,url=start("fs_raw_denial_001_witness_commit_barrier.py",env)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(post_witness,url,permit,grant)
            deadline=time.monotonic()+6
            while not (barrier/"authority-checked").exists():
                assert time.monotonic()<deadline,"witness check barrier not reached"
                time.sleep(0.01)
            updated=advance_authority_state_version()
            assert updated>permit.authority_state_version
            assert advance_online(setup,updated)[0]==200
            (barrier/"continue").touch()
            code,response=pending.result(timeout=7)
        assert (code,response.get("formed"),count(db))==(403,False,0),(
            "FIRST RED: the witness checked authority, then revocation occurred "
            "before its separate commitment; a synthetic consequence formed. "
            f"HTTP={code}, response={response}, ledger-count={count(db)}"
        )
    finally:
        barrier.mkdir(exist_ok=True)
        (barrier/"continue").touch()
        if process.poll() is None:stop(process)
