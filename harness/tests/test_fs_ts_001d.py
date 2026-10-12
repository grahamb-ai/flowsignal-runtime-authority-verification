from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from harness.runner import load_scenario
from app.engines import institutional_authority as authority
from app.engines import protected_consequence as executor
from app.engines.runtime_authority_payment import (
    prepare_payment_execution,
    mint_rai_bound_execution_permit,
)
from app.engines.execution_gateway import (
    ExecutionAttempt,
    action_binding_hash,
)
from app.engines.authority_usage import (
    reset_authority_usage_reference_state_for_test,
)

SCENARIO = (
    Path(__file__).parents[1]
    / "harness" / "scenarios" / "AP-001_allow.json"
)


def test_fs_ts_001d_rejects_inconsistent_snapshot_identity():
    reset_authority_usage_reference_state_for_test()
    req = load_scenario(SCENARIO, rebase_to_now=False)

    prepared = prepare_payment_execution(
        req,
        route_id="R1",
        executor_id="PAYMENT-EXECUTOR-1",
        resolved_at=req.requested_execution_time,
    )

    permit = mint_rai_bound_execution_permit(
        req, prepared, bind_at=req.requested_execution_time
    )
    assert permit is not None, "Initial permit not issued"

    attempt = ExecutionAttempt(
        actor_id=req.actor_id,
        principal_id=req.principal_id,
        action=req.action,
        target=req.target,
        amount=req.amount,
        currency=req.currency,
        source_account=req.source_account,
        beneficiary=req.beneficiary,
        beneficiary_account_reference=req.beneficiary_account_reference,
        purpose=req.purpose,
        mandate_id=req.mandate_id,
        attempted_at=req.requested_execution_time,
    )
    attempted_hash = action_binding_hash(attempt)

    original = authority._MANDATES[req.mandate_id]
    original_snapshot = authority.get_authority_snapshot(req.mandate_id)

    try:
        authority._MANDATES[req.mandate_id] = replace(
            original, status="REVOKED"
        )

        revoked_snapshot = authority.get_authority_snapshot(req.mandate_id)
        assert revoked_snapshot.mandate.status == "REVOKED"
        assert revoked_snapshot.snapshot_id != original_snapshot.snapshot_id

        # Hostile boundary substitution:
        # Preserve the old identity while exposing revoked facts.
        inconsistent_snapshot = replace(
            revoked_snapshot,
            snapshot_id=original_snapshot.snapshot_id,
        )

        with patch.object(
            executor,
            "get_authority_snapshot",
            return_value=inconsistent_snapshot,
        ):
            outcome = executor.execute_protected_consequence(
                permit, attempted_hash
            )

        print(f"FS-TS-001D EXECUTOR OUTCOME: {outcome}")

        assert outcome != "CONSEQUENCE_FORMED", (
            "FS-TS-001D RED: executor accepted revoked "
            "authority with a falsely preserved snapshot identity"
        )

    finally:
        authority._MANDATES[req.mandate_id] = original
