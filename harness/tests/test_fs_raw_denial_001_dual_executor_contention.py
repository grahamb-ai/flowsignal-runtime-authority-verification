"""FS-RAW-DENIAL-001: two independently running actuator processes,
sixteen independent retry-client processes, one source-owned SQLite effect.

No third-party provider, external settlement or distributed deployment.
"""
from pathlib import Path
from urllib.parse import urlsplit
import json,os,subprocess,sys,time
import pytest

from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from test_fs_raw_denial_001_online_authority import start,stop
from test_fs_raw_denial_001_parallel_contention import (
    source_env,actuator_env,grant_payload,witness,ROOT,
)

@pytest.fixture(autouse=True)
def clean_usage():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

def start_all(db,crash=False):
    source,source_url=start("fs_raw_denial_001_contention_server.py",
        source_env(db,crash=crash))
    first,first_url=start("fs_raw_denial_001_contention_server.py",
        actuator_env(db,source_url))
    second,second_url=start("fs_raw_denial_001_contention_server.py",
        actuator_env(db,source_url))
    return (source,source_url),(first,first_url),(second,second_url)

def close_all(*processes):
    for p in processes:
        if p.poll() is None:stop(p)

def concurrent_requests(urls,grant,folder,count=16):
    folder.mkdir(parents=True,exist_ok=True)
    release=folder/"release"
    procs=[]
    for i in range(count):
        base=urls[i%len(urls)]
        route="/execute-a" if i%2==0 else "/execute-b"
        proc=subprocess.Popen(
            [sys.executable,"fs_raw_denial_001_parallel_client.py",
             base,route,str(grant),str(release)],
            cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        procs.append(proc)
    release.touch()
    result=[]
    for proc in procs:
        out,err=proc.communicate(timeout=20)
        assert proc.returncode==0,(out,err)
        result.append(json.loads(out))
    return result

def test_two_executor_processes_sixteen_clients_single_effect(tmp_path):
    db=tmp_path/"one-source.sqlite3"
    (src,src_url),(a,a_url),(b,b_url)=start_all(db)
    try:
        permit,grant=grant_payload(tmp_path)
        replies=concurrent_requests([a_url,b_url],grant,tmp_path/"attempts")
        assert sorted(x["http"] for x in replies)==[200]+[409]*15,replies
        observed=witness(db)
        assert len(observed)==1
        assert observed[0][0]==permit.signature
        assert observed[0][1]==permit.action_binding_hash
    finally:
        close_all(src,a,b)

def test_two_executor_processes_post_commit_source_crash_recovery(tmp_path):
    db=tmp_path/"source-crash.sqlite3"
    (src,src_url),(a,a_url),(b,b_url)=start_all(db,crash=True)
    try:
        permit,grant=grant_payload(tmp_path)
        initial=concurrent_requests([a_url,b_url],grant,tmp_path/"initial")
        deadline=time.monotonic()+5
        while src.poll() is None and time.monotonic()<deadline:
            time.sleep(0.01)
        assert src.poll()==92,initial
        original=witness(db)
        assert len(original)==1
        assert original[0][0]==permit.signature
        env=source_env(db)
        env["FS_RAI_SOURCE_PORT"]=str(urlsplit(src_url).port)
        restarted,restarted_url=start("fs_raw_denial_001_recovery_source.py",env)
        try:
            assert restarted_url==src_url
            replay=concurrent_requests([a_url,b_url],grant,tmp_path/"retry")
            assert all(x["http"]==409 for x in replay),replay
            assert witness(db)==original
        finally:
            close_all(restarted)
    finally:
        close_all(src,a,b)
