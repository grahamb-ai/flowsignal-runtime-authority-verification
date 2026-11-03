"""FS-RAW-DENIAL-001: FIRST RED for check-to-commit authority race.

Genuine RAI final-bind permit is checked online, then the test pauses the
actuator before its SQLite write. Separate authority service advances during
the pause. Expected: no effect. Current reference: stale check can commit.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os,time,pytest
from app.engines.authority_store import get_authority_state_version,advance_authority_state_version
from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from app.engines.rai_external_export_reference import export_final_bind
from app.engines.sandbox_authority_fence_publisher import publish_authority_version
from test_fs_raw_denial_001_online_authority import (
    start,stop,advance_online,READER,ADMIN,
)
from test_fs_raw_denial_001_rai_external_actuator import (
    KEY,mint,request,post,rows,
)

@pytest.fixture(autouse=True)
def fresh_usage():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()

@pytest.fixture
def services(tmp_path):
    db=tmp_path/"source.sqlite3"
    effectdb=tmp_path/"effects.sqlite3"
    barrier=tmp_path/"barrier"
    source_env=os.environ.copy()
    source_env.update(FS_RAI_SOURCE_DB=str(db),
        FS_RAI_SOURCE_READ_TOKEN=READER,
        FS_RAI_SOURCE_ADMIN_TOKEN=ADMIN,
        FS_RAI_SOURCE_INITIAL_VERSION=str(get_authority_state_version()))
    source,source_url=start("fs_raw_denial_001_authority_source.py",source_env)
    actuator_env=os.environ.copy()
    actuator_env.update(FS_RAI_EXTERNAL_LEDGER=str(effectdb),
        FS_RAI_BRIDGE_KEY=KEY.decode(),
        FS_RAI_AUTHORITY_SOURCE_URL=source_url,
        FS_RAI_SOURCE_READ_TOKEN=READER,
        FS_RAI_TEST_BARRIER=str(barrier),
        FS_RAI_AUTHORITY_MAX_AGE_SECONDS="20")
    actuator,actuator_url=start("fs_raw_denial_001_online_commit_barrier.py",actuator_env)
    assert publish_authority_version(effectdb,get_authority_state_version())
    instance={"source":source,"source_url":source_url,"actuator":actuator,
              "pair":(actuator_url,effectdb),"barrier":barrier}
    try:yield instance
    finally:
        barrier.mkdir(exist_ok=True)
        (barrier/"continue").touch()
        stop(actuator)
        stop(source)

def test_revocation_between_online_check_and_commit_must_refuse(services):
    permit=mint(request())
    exported=export_final_bind(permit,bridge_key=KEY)
    assert exported is not None
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(post,services["pair"],"/execute-b",exported,
                           permit.action_binding_hash)
        deadline=time.monotonic()+6
        while not (services["barrier"]/"looked-up").exists():
            assert time.monotonic()<deadline, "actuator did not reach post-lookup barrier"
            time.sleep(0.01)
        new_version=advance_authority_state_version()
        assert new_version>permit.authority_state_version
        assert advance_online(services,new_version)[0]==200
        # No pushed update to actuator; it has already queried authority.
        (services["barrier"]/"continue").touch()
        code,result=future.result(timeout=6)
    observed=rows(services["pair"])
    assert (code,result["formed"],observed)==(403,False,[]), (
        "FIRST RED: authority changed after online verification but before "
        f"commit; actuator returned {code}/{result}, external ledger={observed}"
    )
