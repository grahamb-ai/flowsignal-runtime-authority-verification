from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from app.engines.authority_usage import reset_authority_usage_reference_state_for_test
from app.engines.public_authority_receipt import (
    build_public_authority_receipt,
    public_authority_receipt_json,
    verify_public_authority_receipt,
)
from app.engines.runtime_authority_payment import final_bind_payment, prepare_payment_execution
from harness.runner import load_scenario


SCENARIO = Path(__file__).parents[1] / "harness" / "scenarios" / "AP-001_allow.json"


@pytest.fixture(autouse=True)
def _isolate_authority_usage_reference_state():
    reset_authority_usage_reference_state_for_test()
    yield
    reset_authority_usage_reference_state_for_test()


def _permitted_receipt():
    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    final = final_bind_payment(req, prepared, bind_at=req.requested_execution_time)
    receipt = build_public_authority_receipt(
        prepared, final, bind_at=req.requested_execution_time
    )
    return req, prepared, final, receipt


def test_receipt_exposes_buyer_readable_who_what_now_match():
    req, prepared, final, receipt = _permitted_receipt()

    assert receipt["who"]["authority_subject_id"] == req.actor_id
    assert receipt["who"]["evidence_anchor"] == prepared.determination.resolution_context_id
    assert receipt["what"]["protected_operation_id"] == prepared.operation.operation_id
    assert receipt["now"]["status"] == "VALID_AT_FINAL_BIND"
    assert receipt["match"]["status"] == "EXACT_CORRESPONDENCE"
    assert receipt["outcome"]["decision"] == "PERMITTED_TO_ACT"
    assert receipt["outcome"]["consequence_formed"] is False
    assert verify_public_authority_receipt(
        receipt, prepared, final, bind_at=req.requested_execution_time
    )


@pytest.mark.parametrize(
    ("section", "field", "hostile_value"),
    [
        ("who", "authority_subject_id", "attacker-controlled-agent"),
        ("what", "action", "redirect-funds"),
        ("now", "status", "VALID_FOREVER"),
        ("match", "status", "APPROXIMATE"),
        ("outcome", "decision", "EXECUTED"),
    ],
)
def test_tampered_public_fields_fail_verification(section, field, hostile_value):
    req, prepared, final, receipt = _permitted_receipt()
    attacked = deepcopy(receipt)
    attacked[section][field] = hostile_value
    assert not verify_public_authority_receipt(
        attacked, prepared, final, bind_at=req.requested_execution_time
    )


def test_recomputed_digest_cannot_make_false_who_correspond_to_runtime_artifacts():
    req, prepared, final, receipt = _permitted_receipt()
    attacked = deepcopy(receipt)
    attacked["who"]["authority_subject_id"] = "attacker-controlled-agent"
    # An attacker can recompute an unkeyed digest. Verification still compares
    # the document with the trusted determination and protected operation.
    from app.engines.public_authority_receipt import _digest
    unsigned = {key: value for key, value in attacked.items() if key != "integrity"}
    attacked["integrity"]["digest"] = _digest(unsigned)
    assert not verify_public_authority_receipt(
        attacked, prepared, final, bind_at=req.requested_execution_time
    )


def test_recomputed_digest_cannot_rewrite_when_the_check_occurred():
    req, prepared, final, receipt = _permitted_receipt()
    attacked = deepcopy(receipt)
    attacked["now"]["checked_at"] = "2099-01-01T00:00:00+00:00"
    from app.engines.public_authority_receipt import _digest
    unsigned = {key: value for key, value in attacked.items() if key != "integrity"}
    attacked["integrity"]["digest"] = _digest(unsigned)
    assert not verify_public_authority_receipt(
        attacked, prepared, final, bind_at=req.requested_execution_time
    )


def test_blocked_final_bind_cannot_be_presented_as_permitted():
    req = load_scenario(SCENARIO, rebase_to_now=False)
    prepared = prepare_payment_execution(
        req,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )
    changed = replace(req, beneficiary="SUBSTITUTED-BENEFICIARY")
    final = final_bind_payment(changed, prepared, bind_at=req.requested_execution_time)
    assert final.status == "BLOCKED"
    with pytest.raises(ValueError, match="successful final-bind"):
        build_public_authority_receipt(
            prepared, final, bind_at=req.requested_execution_time
        )


def test_json_rendering_is_stable():
    _, _, _, receipt = _permitted_receipt()
    assert public_authority_receipt_json(receipt) == public_authority_receipt_json(receipt)
