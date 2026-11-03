"""FS-RAW-DENIAL-001 hostile independent-process retry contention.

Two threaded LOCAL HTTP servers, eight separate Python client processes, one
genuine FlowSignal RAI final-bind assertion, one source-owned SQLite ledger.
Second test uses os._exit after commit and real source restart. Neither test
proves cross-host HA, external payments, power-loss durability or source
authenticity beyond the test fixture.
"""
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit
import json,os,sqlite3,subprocess,sys,time
import pytest

from app.engines.authority_store import get_authority_state_version
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from app.engines.rai_external_export_reference import export_final_bind
from test_fs_raw_denial_001_online_authority import start,stop,READER,ADMIN
from test_fs_raw_denial_001_rai_external_actuator import KEY,mint,request

ROOT=Path(__file__).parents[1]
TOKEN="parallel-source-test-key"

@pytest.fixture(autouse=True)
def isolate_usage():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

def source_env(db,*,crash=False):
    env=os.environ.copy()
    env.update(FS_RAI_SOURCE_DB=str(db),FS_RAI_SOURCE_READ_TOKEN=READER,
        FS_RAI_SOURCE_ADMIN_TOKEN=ADMIN,
        FS_RAI_SOURCE_COMMIT_TOKEN=TOKEN,
        FS_RAI_SOURCE_INITIAL_VERSION=str(get_authority_state_version()),
        FS_RAI_EXTERNAL_LEDGER=str(db),FS_RAI_BRIDGE_KEY=KEY.decode(),
        FS_RAI_AUTHORITY_SOURCE_URL="http://127.0.0.1:1",
        FS_RAI_CONTENTION_ROLE="crash-source" if crash else "source")
    if crash:env["FS_RAI_TEST_CRASH_POINT"]="after"
    return env

def actuator_env(db,url):
    env=source_env(db)
    env.update(FS_RAI_AUTHORITY_SOURCE_URL=url,
        FS_RAI_CONTENTION_ROLE="actuator")
    return env

def witness(db):
    with closing(sqlite3.connect(f"file:{db}?mode=ro",uri=True)) as c:
        return c.execute("SELECT permit_signature,action_binding_hash,route "
                         "FROM committed_effects").fetchall()

def start_pair(db,*,crash=False):
    src,src_url=start("fs_raw_denial_001_contention_server.py",
                       source_env(db,crash=crash))
    exe,exe_url=start("fs_raw_denial_001_contention_server.py",
                       actuator_env(db,src_url))
    return src,src_url,exe,exe_url

def stop_pair(src,exe):
    if exe.poll() is None:stop(exe)
    if src.poll() is None:stop(src)

def grant_payload(tmp_path):
    permit=mint(request())
    assert permit is not None
    grant=export_final_bind(permit,bridge_key=KEY)
    assert grant is not None
    path=tmp_path/"signed-execution.json"
    path.write_text(json.dumps({"envelope":grant,
                       "action_binding_hash":permit.action_binding_hash}))
    return permit,path

def parallel_clients(url,grant,folder,n=8):
    folder.mkdir(parents=True,exist_ok=True)
    release=folder/"release"
    clients=[]
    for i in range(n):
        route="/execute-a" if i%2==0 else "/execute-b"
        p=subprocess.Popen([sys.executable,"fs_raw_denial_001_parallel_client.py",
            url,route,str(grant),str(release)],cwd=ROOT,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        clients.append(p)
    release.touch()
    responses=[]
    for p in clients:
        stdout,stderr=p.communicate(timeout=18)
        assert p.returncode==0,(stdout,stderr)
        responses.append(json.loads(stdout))
    return responses

def test_eight_independent_clients_contend_same_execution(tmp_path):
    db=tmp_path/"authority.sqlite3"
    src,src_url,exe,exe_url=start_pair(db)
    try:
        permit,grant=grant_payload(tmp_path)
        replies=parallel_clients(exe_url,grant,tmp_path/"clients")
        assert sorted(r["http"] for r in replies)==[200]+[409]*7,replies
        assert len(witness(db))==1
        assert witness(db)[0][:2]==(permit.signature,permit.action_binding_hash)
    finally:
        stop_pair(src,exe)

def test_crash_during_multi_client_contention_and_retry(tmp_path):
    db=tmp_path/"crashing-authority.sqlite3"
    src,src_url,exe,exe_url=start_pair(db,crash=True)
    try:
        permit,grant=grant_payload(tmp_path)
        original=parallel_clients(exe_url,grant,tmp_path/"first-clients")
        deadline=time.monotonic()+4
        while src.poll() is None and time.monotonic()<deadline:
            time.sleep(0.01)
        assert src.poll()==92,original
        assert len(witness(db))==1,original
        # Restore source on SAME port so original actuator and grant remain valid.
        restart_env=source_env(db)
        restart_env["FS_RAI_SOURCE_PORT"]=str(urlsplit(src_url).port)
        restored,restored_url=start("fs_raw_denial_001_recovery_source.py",
                                    restart_env)
        assert restored_url==src_url
        try:
            retried=parallel_clients(exe_url,grant,tmp_path/"retry-clients")
            assert all(r["http"]==409 for r in retried),retried
            assert witness(db)==[(permit.signature,permit.action_binding_hash,
                                 witness(db)[0][2])]
        finally:
            stop(restored)
    finally:
        stop_pair(src,exe)
