"""Two distinct actuator OS processes, 8 independent client processes.

All effects remain local SQLite reference rows. Each actuator has its own
loopback HTTP port and forwards to a single source-owned commit service.
"""
from contextlib import closing
from pathlib import Path
import json,os,sqlite3,subprocess,sys
import pytest
from app.engines.authority_store import get_authority_state_version
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from app.engines.rai_external_export_reference import export_final_bind
from test_fs_raw_denial_001_online_authority import start,stop,READER,ADMIN
from test_fs_raw_denial_001_rai_external_actuator import KEY,mint,request,post

ROOT=Path(__file__).parents[1]
TOKEN="test-two-actuators-commit"

@pytest.fixture(autouse=True)
def isolate_usage():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

@pytest.fixture
def system(tmp_path):
    db=tmp_path/"authority-effects.sqlite3"
    env=os.environ.copy()
    env.update(FS_RAI_SOURCE_DB=str(db),
        FS_RAI_SOURCE_READ_TOKEN=READER,
        FS_RAI_SOURCE_ADMIN_TOKEN=ADMIN,
        FS_RAI_SOURCE_COMMIT_TOKEN=TOKEN,
        FS_RAI_SOURCE_INITIAL_VERSION=str(get_authority_state_version()),
        FS_RAI_EXTERNAL_LEDGER=str(db),
        FS_RAI_BRIDGE_KEY=KEY.decode(),
        FS_RAI_TEST_DROP_ACK="0")
    source,source_url=start("fs_raw_denial_001_threaded_source.py",env)
    actuator_env=env.copy()
    actuator_env.update(FS_RAI_AUTHORITY_SOURCE_URL=source_url)
    running=[]
    try:
        for _ in range(2):
            p,url=start("fs_raw_denial_001_atomic_actuator.py",actuator_env)
            running.append((p,url))
        yield {"source":source,"source_url":source_url,"actuators":running,
               "db":db,"tmp":tmp_path}
    finally:
        for p,_ in running:
            if p.poll() is None:stop(p)
        if source.poll() is None:stop(source)

def ledger(db):
    with closing(sqlite3.connect(f"file:{db}?mode=ro",uri=True)) as c:
        return c.execute("SELECT permit_signature,action_binding_hash,route "
                         "FROM committed_effects").fetchall()

def signed():
    permit=mint(request())
    assert permit is not None
    assertion=export_final_bind(permit,bridge_key=KEY)
    assert assertion is not None
    return permit,assertion

def clients(system,permit,envelope,quantity):
    directory=system["tmp"]/"clients"
    directory.mkdir(parents=True,exist_ok=True)
    gate=directory/"go"
    children=[]
    for index in range(quantity):
        _,url=system["actuators"][index%2]
        cfg={"gate":str(gate),"actuator_url":url,
             "route":"/execute-a" if index%2==0 else "/execute-b",
             "envelope":envelope,"action_binding_hash":permit.action_binding_hash,
             "output":str(directory/f"out-{index}.json")}
        path=directory/f"cfg-{index}.json"
        path.write_text(json.dumps(cfg))
        p=subprocess.Popen([sys.executable,"fs_raw_denial_001_actuator_client.py",str(path)],
            cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        children.append((p,cfg))
    gate.touch()
    results=[]
    try:
        for p,cfg in children:
            out,err=p.communicate(timeout=15)
            assert p.returncode==0,(out,err)
            results.append(json.loads(Path(cfg["output"]).read_text()))
    finally:
        for p,_ in children:
            if p.poll() is None:
                p.kill()
                p.communicate(timeout=3)
    return results

def test_two_real_actuator_processes_eight_clients_one_reference_commit(system):
    permit,envelope=signed()
    responses=clients(system,permit,envelope,8)
    codes=[response["code"] for response in responses]
    assert codes.count(200)==1,codes
    assert codes.count(409)==7,codes
    rows=ledger(system["db"])
    assert len(rows)==1
    assert rows[0][:2]==(permit.signature,permit.action_binding_hash)
    assert rows[0][2] in ("/execute-a","/execute-b")
    assert system["actuators"][0][0].pid!=system["actuators"][1][0].pid

def test_one_actuator_terminated_after_commit_other_route_replay_refused(system):
    permit,envelope=signed()
    first=system["actuators"][0]
    second=system["actuators"][1]
    status,response=post((first[1],system["db"]),"/execute-a",envelope,
                         permit.action_binding_hash)
    assert status==200 and response["formed"] is True
    stop(first[0])
    retry,response=post((second[1],system["db"]),"/execute-b",envelope,
                        permit.action_binding_hash)
    assert (retry,response["status"])==(409,"REPLAY_REFUSED")
    assert ledger(system["db"])==[
        (permit.signature,permit.action_binding_hash,"/execute-a")]
