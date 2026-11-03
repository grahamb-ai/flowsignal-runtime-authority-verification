"""FS-STRIPE-004: bounded genuine RAI / one-owner / Stripe TEST capture.

Sandbox only: £1.00 test PaymentIntents, manual capture, no real funds.
Each PaymentIntent ID is bound into the genuine RAI operation's purpose.
Provider status is read independently AFTER capture/cancel. Never log secrets.

IMPORTANT: local owner commitment and Stripe capture are separate processes and
NOT an atomic distributed operation. This script does NOT close a revocation
between owner commitment and Stripe's acceptance, a separate Stripe API caller,
or rollback of the owner DB. Production prevention NOT ESTABLISHED.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
import base64,hashlib,json,os,select,sqlite3,subprocess,sys,tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from app.engines.authority_store import advance_authority_state_version
from app.engines.rai_external_export_reference import export_final_bind
from app.engines.runtime_authority_payment import (
    prepare_payment_execution,mint_rai_bound_execution_permit,
)
from harness.runner import load_scenario

ROOT=Path(__file__).resolve().parents[1]
SCENARIO=ROOT/"harness"/"scenarios"/"AP-001_allow.json"
BRIDGE_KEY=b"fs-stripe-004-sandbox-bridge"
AMOUNT_MINOR=100
OWNER_READ="fs-stripe-004-test-reader"
OWNER_ADMIN="fs-stripe-004-test-admin"
OWNER_COMMIT="fs-stripe-004-test-commit"

class SandboxError(RuntimeError):
    pass

def post_json(url,payload,header=None):
    r=Request(url,data=json.dumps(payload).encode(),method="POST",
              headers={"Content-Type":"application/json",**(header or {})})
    try:
        with urlopen(r,timeout=8) as response:
            return response.status,json.loads(response.read())
    except HTTPError as error:
        return error.code,json.loads(error.read())

class StripeTestClient:
    def __init__(self):
        key=os.environ.get("STRIPE_TEST_SECRET_KEY","")
        if not (key.startswith("sk_test_") or key.startswith("rk_test_")):
            raise SandboxError("Only sk_test_/rk_test_ credentials permitted")
        self.authorization="Basic "+base64.b64encode((key+":").encode()).decode()

    def call(self,path,fields=None,*,idempotency=None):
        headers={"Authorization":self.authorization}
        if idempotency:headers["Idempotency-Key"]=idempotency
        if fields is not None:
            headers["Content-Type"]="application/x-www-form-urlencoded"
            data=urlencode(fields).encode()
        else:
            data=None
        request=Request("https://api.stripe.com/v1"+path,data=data,headers=headers,
                        method="POST" if fields is not None else "GET")
        try:
            with urlopen(request,timeout=15) as response:
                obj=json.loads(response.read())
        except HTTPError as error:
            # Stripe errors can contain request-identifying details. Surface
            # only error type/status without exposing secret credentials.
            try:
                problem=json.loads(error.read()).get("error",{})
                diagnostic={k:problem.get(k) for k in ("type","code","param","message") if problem.get(k)}
            except (ValueError,TypeError):
                diagnostic={}
            raise SandboxError(f"Stripe request failed HTTP {error.code}; diagnostic={diagnostic}") from None
        except (URLError,OSError,ValueError):
            raise SandboxError("Stripe outcome unresolved; retrieve PaymentIntent before retry") from None
        if obj.get("livemode") is not False:
            raise SandboxError("Stripe returned non-test-mode object; stop")
        return obj

    def authorize(self,case_id):
        return self.call("/payment_intents",{
            "amount":AMOUNT_MINOR,"currency":"gbp","capture_method":"manual",
            "confirm":"true","payment_method":"pm_card_visa",
            "automatic_payment_methods[enabled]":"true",
            "automatic_payment_methods[allow_redirects]":"never",
            "description":"FS-STRIPE-004 isolated £1 reference authority test",
            "metadata[experiment]":"FS-STRIPE-004",
            "metadata[case]":case_id,
        },idempotency="fs-stripe-004-create-"+case_id)

    def bind(self,payment_id,binding):
        return self.call(f"/payment_intents/{payment_id}",{
            "metadata[rai_action_binding_hash]":binding,
        })

    def retrieve(self,payment_id):
        return self.call(f"/payment_intents/{payment_id}")

    def capture(self,payment_id,signature):
        key="fs-stripe-004-cap-"+hashlib.sha256(
            (payment_id+":"+signature).encode()).hexdigest()
        return self.call(f"/payment_intents/{payment_id}/capture",{},
                         idempotency=key)

    def cancel(self,payment_id):
        return self.call(f"/payment_intents/{payment_id}/cancel",{},
                         idempotency="fs-stripe-004-cancel-"+payment_id)

class AuthorityOwner:
    def __init__(self,root):
        self.root=Path(root)
        self.process=None
        self.url=None

    def __enter__(self):
        env=os.environ.copy()
        env.pop("FLOWSIGNAL_AUTHORITY_OWNER_URL",None)
        env.update(FS_RAI_SOURCE_DB=str(self.root/"owner.sqlite3"),
            FS_RAI_SOURCE_INITIAL_VERSION="1",
            FS_RAI_SOURCE_READ_TOKEN=OWNER_READ,
            FS_RAI_SOURCE_ADMIN_TOKEN=OWNER_ADMIN,
            FS_RAI_WITNESS_COMMIT_TOKEN=OWNER_COMMIT,
            FS_RAI_EXTERNAL_LEDGER=str(self.root/"owner.sqlite3"),
            FS_RAI_BRIDGE_KEY=BRIDGE_KEY.decode())
        self.process=subprocess.Popen(
            [sys.executable,"-u","fs_raw_denial_001_authority_owner.py"],
            cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        assert select.select([self.process.stdout],[],[],10)[0], "owner startup timeout"
        self.url="http://127.0.0.1:"+self.process.stdout.readline().strip()
        self.previous={k:os.environ.get(k) for k in (
            "FLOWSIGNAL_AUTHORITY_OWNER_URL","FLOWSIGNAL_AUTHORITY_OWNER_READ_TOKEN",
            "FLOWSIGNAL_AUTHORITY_OWNER_ADMIN_TOKEN")}
        os.environ.update(FLOWSIGNAL_AUTHORITY_OWNER_URL=self.url,
            FLOWSIGNAL_AUTHORITY_OWNER_READ_TOKEN=OWNER_READ,
            FLOWSIGNAL_AUTHORITY_OWNER_ADMIN_TOKEN=OWNER_ADMIN)
        return self

    def __exit__(self,*_):
        for k,v in self.previous.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v
        if self.process:
            self.process.terminate()
            try:self.process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill();self.process.communicate(timeout=3)

    def commit(self,grant,hash_value):
        return post_json(self.url+"/commit",{
            "envelope":grant,"action_binding_hash":hash_value,
            "route":"/execute-a"},
            {"X-Witness-Commit-Token":OWNER_COMMIT})

    def count(self):
        with closing(sqlite3.connect(self.root/"owner.sqlite3")) as conn:
            return conn.execute("SELECT COUNT(*) FROM committed_effects").fetchone()[0]

def rai_permit_for_payment(payment_id,*,return_request=False):
    scenario=load_scenario(SCENARIO,rebase_to_now=False)
    now=datetime.now(timezone.utc)
    req=replace(scenario,amount=Decimal("1.00"),
        purpose=f"FS-STRIPE-004 PaymentIntent {payment_id}",
        requested_execution_time=now,screening_captured_at=now,
        mandate_valid_until=now+timedelta(hours=1))
    prepared=prepare_payment_execution(req,route_id="STRIPE_TEST_CAPTURE",
        executor_id="FS-STRIPE-004-TEST-EXECUTOR",resolved_at=now)
    permit=mint_rai_bound_execution_permit(req,prepared,bind_at=now)
    if permit is None:raise SandboxError("Genuine RAI final bind refused")
    grant=export_final_bind(permit,bridge_key=BRIDGE_KEY)
    if grant is None:raise SandboxError("RAI provenance bridge refused")
    return (permit,grant,req) if return_request else (permit,grant)

def run_case(stripe,case_id,*,revoke):
    reset_authority_usage_reference_state_for_test()
    with tempfile.TemporaryDirectory(prefix="fs-stripe-004-") as directory:
        with AuthorityOwner(directory) as owner:
            pi=stripe.authorize(case_id)
            payment_id=pi["id"]
            if (pi["status"]!="requires_capture" or pi["amount"]!=AMOUNT_MINOR
                    or pi["currency"]!="gbp" or pi.get("capture_method")!="manual"):
                raise SandboxError("Unexpected test authorisation state")
            try:
                permit,grant=rai_permit_for_payment(payment_id)
                bound=stripe.bind(payment_id,permit.action_binding_hash)
                observed=stripe.retrieve(payment_id)
                if (bound.get("metadata",{}).get("rai_action_binding_hash")!=permit.action_binding_hash
                        or observed.get("metadata",{}).get("rai_action_binding_hash")!=permit.action_binding_hash
                        or observed["amount"]!=AMOUNT_MINOR
                        or observed["status"]!="requires_capture"):
                    raise SandboxError("Stripe PaymentIntent binding mismatch")
                if revoke:
                    updated=advance_authority_state_version()
                    if updated<=permit.authority_state_version:
                        raise SandboxError("Revocation not persisted in owner")
                owner_http,result=owner.commit(grant,permit.action_binding_hash)
                if revoke:
                    if owner_http!=403 or result.get("status")!="AUTHORITY_STATE_STALE":
                        raise SandboxError("Revoked permit was not refused by owner")
                    final=stripe.cancel(payment_id)
                    final=stripe.retrieve(payment_id)
                    if final["status"]!="canceled" or owner.count()!=0:
                        raise SandboxError("Revocation case failed provider/owner checks")
                else:
                    if owner_http!=200 or result.get("status")!="WITNESSED_CONSEQUENCE_FORMED":
                        raise SandboxError("Owner refused valid test execution")
                    final=stripe.capture(payment_id,permit.signature)
                    final=stripe.retrieve(payment_id)
                    if (final["status"]!="succeeded" or final["amount_received"]!=AMOUNT_MINOR
                            or owner.count()!=1):
                        raise SandboxError("Payment outcome unresolved or mismatched")
                return {
                    "case":case_id,"payment_intent_id":payment_id,
                    "owner_http":owner_http,"owner_status":result.get("status"),
                    "stripe_status":final["status"],"stripe_amount_received":final["amount_received"],
                    "livemode":final["livemode"],"authority_version":permit.authority_state_version,
                    "action_binding_hash":permit.action_binding_hash,
                    "owner_effect_count":owner.count(),
                }
            except Exception:
                # Best-effort cancellation; never retry capture on uncertainty.
                try:
                    state=stripe.retrieve(payment_id)
                    if state["status"]=="requires_capture":stripe.cancel(payment_id)
                except Exception:pass
                raise

def main():
    client=StripeTestClient()
    now=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    import uuid
    evidence_id=now+"-"+uuid.uuid4().hex[:8]
    results=[]
    for case,revoke in [("refuse-"+evidence_id,True),("allow-"+evidence_id,False)]:
        result=run_case(client,case,revoke=revoke)
        results.append(result)
        print(json.dumps(result,sort_keys=True),flush=True)
    output=Path(os.environ.get("FS_STRIPE_004_EVIDENCE_FILE","fs-stripe-004-evidence.json"))
    output.write_text(json.dumps({"experiment":"FS-STRIPE-004",
       "limits":"Reference owner is not atomic with Stripe provider capture; prevention NOT ESTABLISHED",
       "results":results},indent=2))
    assert len(results)==2
    assert results[0]["stripe_status"]=="canceled"
    assert results[1]["stripe_status"]=="succeeded"

if __name__=="__main__":
    main()
